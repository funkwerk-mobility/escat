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
        super().__init__("eventstore/eventstore:20.10.2-buster-slim")
        self.with_exposed_ports(2113)
        self.with_env("EVENTSTORE_INSECURE", "true")
        self.with_env("EVENTSTORE_EXT_TCP_PORT", "1113")
        self.with_env("EVENTSTORE_EXT_HTTP_PORT", "2113")


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
            host = container.get_container_host_ip()
            print(f"EventStore container ready at {host}")

            # Wait up to 30 seconds for successful connection
            start_time = time.time()
            timeout = 30
            last_error = None

            while time.time() - start_time < timeout:
                try:
                    client = EventStoreDBClient(uri=f"esdb://{host}?tls=false")
                    next(client.read_all())
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

    # Run escat to read the events
    result = run_escat(test_context.eventstore_host, "-q", test_context.stream_name)

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


def run_escat(
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
        data = json.dumps({"body": {"message": f"{prefix} event {i}"}}).encode()
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

    print(f"Starting escat process to follow {test_context.stream_name}...")
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
        print("Waiting for escat to initialize...")
        time.sleep(1)

        write_test_events(test_context.client, test_context.stream_name, 3, prefix="Follow")
        output = read_process_output(process, expected_events)

    finally:
        process.terminate()
        process.wait()

    assert len(output) == expected_events
    assert all("Follow event" in event["data"]["message"] for event in output)


def test_offset_options(test_context: StreamContext) -> None:
    # Test reading from end
    result = run_escat(test_context.eventstore_host, "-o", "end", "-q", test_context.stream_name)
    assert result.stdout.strip() == ""  # Should be empty when reading from end

    # Test reading last event
    result = run_escat(test_context.eventstore_host, "-o", "last", "-q", test_context.stream_name)
    assert len(result.stdout.strip().split("\n")) == 1  # Should only get one event
