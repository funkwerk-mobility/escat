import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional

import pytest
from esdbclient import EventStoreDBClient, NewEvent, StreamState
from testcontainers.core.container import DockerContainer


@dataclass
class StreamContext:
    eventstore_host: str
    stream_name: str
    client: EventStoreDBClient


class EventStoreContainer(DockerContainer):
    def __init__(self) -> None:
        """Initialize EventStore container with required configuration."""
        super().__init__("eventstore/eventstore:21.10.11-bionic")
        self.with_bind_ports(2113, 2113)
        self.with_env("EVENTSTORE_INSECURE", "true")
        self.with_env("EVENTSTORE_EXT_TCP_PORT", "1113")
        self.with_env("EVENTSTORE_HTTP_PORT", "2113")
        self.with_env("EVENTSTORE_ENABLE_ATOM_PUB_OVER_HTTP", "true")


@pytest.fixture(scope="session")
def eventstore() -> Generator[str, None, None]:
    print("\nPulling EventStore container image (this may take a while)...")
    container = EventStoreContainer()

    def print_logs() -> None:
        print("\nContainer logs:")
        print(container.get_logs())

    with container:
        try:
            container_id = container.get_wrapped_container().id
            print(f"Container started with ID: {container_id}")
            print("Waiting for EventStore to initialize...")

            # Get connection details
            host = "localhost"
            print(f"EventStore container ready at {host}")

            # Wait up to 30 seconds for successful connection
            start_time = time.time()
            timeout = 30
            last_error = None

            while time.time() - start_time < timeout:
                try:
                    client = EventStoreDBClient(uri=f"esdb://{host}?tls=false")
                    client.append_to_stream(
                        "test",
                        current_version=StreamState.ANY,
                        events=[NewEvent(type="TestEvent", data=b"")],
                    )
                    print("Connection test successful")
                    break
                except Exception as e:
                    last_error = e
                    print(f"Connection attempt failed, retrying... ({e})")
                    time.sleep(1)
            else:
                print("\nTimeout waiting for EventStore to be ready")
                print_logs()
                raise Exception("EventStore failed to start properly") from last_error

            yield host

        except Exception as e:
            error_msg = f"Error during container setup: {e}"
            print(error_msg)
            print_logs()
            raise


TEST_EVENT_COUNT = 3


def test_basic_stream_reading(test_context: StreamContext) -> None:
    print("\nSetting up test_basic_stream_reading...")

    # Write test events
    write_test_events(test_context.client, test_context.stream_name, 3)

    # Run esdbcat to read the events
    result = run_esdbcat(test_context.eventstore_host, "-q", test_context.stream_name)

    # Parse the output
    output_events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]

    # Verify we got all events in order
    assert len(output_events) == TEST_EVENT_COUNT
    for i, event in enumerate(output_events):
        assert event["data"]["message"] == f"Test event {i}"


@pytest.fixture
def test_context(eventstore: str) -> StreamContext:
    stream_name = f"test-stream-{uuid.uuid4()}"
    client = EventStoreDBClient(uri=f"esdb://{eventstore}?tls=false")
    return StreamContext(eventstore, stream_name, client)


def get_subprocess_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return env


def run_esdbcat(
    host: str, *args: str, env: Optional[Dict[str, str]] = None
) -> subprocess.CompletedProcess[str]:
    if env is None:
        env = get_subprocess_env()
    return subprocess.run(
        ["python", "-m", "esdbcat.cli", "--host", host, *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def write_test_events(
    client: EventStoreDBClient, stream_name: str, count: int, prefix: str = "Test"
) -> None:
    """Write a series of test events to the stream."""
    print(f"Writing {count} test events to {stream_name}...")
    for i in range(count):
        data = json.dumps({"message": f"{prefix} event {i}"}).encode()
        client.append_to_stream(
            stream_name,
            current_version=StreamState.ANY,
            events=[NewEvent(type="TestEvent", data=data)],
        )
    print("Test events written successfully")


def read_process_output(
    process: subprocess.Popen[str], expected_count: int, timeout_seconds: int = 10
) -> List[Dict[str, Any]]:
    """Read output from a process until expected count or timeout."""
    print("Reading output from esdbcat...")
    output: List[Dict[str, Any]] = []
    timeout = time.time() + timeout_seconds
    while len(output) < expected_count and time.time() < timeout:
        if process.stdout is None:
            break
        line = process.stdout.readline()
        if not line:
            print("No more output from esdbcat")
            break
        print(f"Got line from esdbcat: {line.strip()}")
        output.append(json.loads(line))
    return output


def test_follow_and_count(test_context: StreamContext) -> None:
    print("\nSetting up test_follow_and_count...")
    expected_events = 2

    print(f"Starting esdbcat process to follow {test_context.stream_name}...")
    env = get_subprocess_env()
    process = subprocess.Popen(
        [
            "python",
            "-m",
            "esdbcat.cli",
            "--host",
            test_context.eventstore_host,
            "-f",
            "-c",
            str(expected_events),
            "-q",
            test_context.stream_name,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    try:
        print("Waiting for esdbcat to initialize...")
        time.sleep(1)

        write_test_events(test_context.client, test_context.stream_name, 3, prefix="Follow")
        output = read_process_output(process, expected_events)

    finally:
        process.terminate()
        process.wait()

    assert len(output) == expected_events
    assert all("Follow event" in event["data"]["message"] for event in output)


def test_link_resolution(test_context: StreamContext) -> None:
    """Test that links to events in other streams are properly resolved."""
    print("\nSetting up test_link_resolution...")

    # Create source stream with events
    source_stream = f"source-{test_context.stream_name}"
    write_test_events(test_context.client, source_stream, 1, prefix="Source")

    # Read the source event to get its ID
    source_events = list(test_context.client.read_stream(source_stream))
    assert len(source_events) == 1

    # Create a link to the source event
    test_context.client.append_to_stream(
        test_context.stream_name,
        current_version=StreamState.ANY,
        events=[NewEvent(
            type="$>",  # EventStore link event type
            data=f"0@{source_stream}".encode()
        )]
    )
    print(f"Appended link to {test_context.stream_name}")

    # Read the linked stream with esdbcat
    result = run_esdbcat(test_context.eventstore_host, "-q", test_context.stream_name)
    output_events = [json.loads(line) for line in result.stdout.strip().split("\n") if line.strip()]

    # Verify we got the resolved event
    assert len(output_events) == 1
    assert output_events[0]["data"]["message"] == "Source event 0"


def test_offset_options(test_context: StreamContext) -> None:
    # Write some test events
    write_test_events(test_context.client, test_context.stream_name, 5)

    # Test reading from end (should be empty)
    result = run_esdbcat(test_context.eventstore_host, "-o", "end", "-q", test_context.stream_name)
    assert result.stdout.strip() == ""

    # Test reading from numeric offset
    result = run_esdbcat(test_context.eventstore_host, "-o", "2", "-q", test_context.stream_name)
    events = [json.loads(line) for line in result.stdout.strip().split("\n")]
    assert len(events) == 3  # Should get events 2, 3, and 4
    assert events[0]["data"]["message"] == "Test event 2"


def test_event_type_filtering(test_context: StreamContext) -> None:
    """Test filtering events by type."""
    # Write events with different types
    client = test_context.client
    stream = test_context.stream_name
    
    # Event with type "TypeA"
    data = json.dumps({"message": "Event A"}).encode()
    client.append_to_stream(
        stream,
        current_version=StreamState.ANY,
        events=[NewEvent(type="TypeA", data=data)]
    )
    
    # Event with type "TypeB"
    data = json.dumps({"message": "Event B"}).encode()
    client.append_to_stream(
        stream,
        current_version=StreamState.ANY,
        events=[NewEvent(type="TypeB", data=data)]
    )

    # Test filtering for TypeA
    result = run_esdbcat(test_context.eventstore_host, "-t", "TypeA", "-q", test_context.stream_name)
    events = [json.loads(line) for line in result.stdout.strip().split("\n")]
    assert len(events) == 1
    assert events[0]["metadata"]["type"] == "TypeA"
    assert events[0]["data"]["message"] == "Event A"
