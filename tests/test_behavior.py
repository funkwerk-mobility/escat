import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import List, Dict, Any
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from esdbclient import EventStoreDBClient, StreamState, NewEvent
import pytest

class EventStoreContainer(DockerContainer):
    def __init__(self):
        super().__init__("eventstore/eventstore:20.10.2-buster-slim")
        self.with_exposed_ports(2113)
        self.with_env("EVENTSTORE_INSECURE", "true")
        self.with_env("EVENTSTORE_EXT_TCP_PORT", "1113")
        self.with_env("EVENTSTORE_EXT_HTTP_PORT", "2113")

@pytest.fixture(scope="session")
def eventstore():
    print("\nPulling EventStore container image (this may take a while)...")
    container = EventStoreContainer()
    
    def print_logs():
        print("\nContainer logs:")
        print(container.get_logs())
        
    with container:
        try:
            print(f"Container started with ID: {container.get_wrapped_container().id}")
            print("Waiting for EventStore to initialize...")
            
            # Get connection details
            port = container.get_exposed_port(2113)
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
            print(f"Error during container setup: {e}")
            print_logs()
            raise

def test_basic_stream_reading(test_context):
    print("\nSetting up test_basic_stream_reading...")
    
    # Write test events
    write_test_events(test_context.client, test_context.stream_name, 3)
    
    # Run escat to read the events
    result = run_escat(test_context.eventstore_host, "-q", test_context.stream_name)
    
    # Parse the output
    output_events = [
        json.loads(line) for line in result.stdout.strip().split('\n')
        if line.strip()
    ]
    
    # Verify we got all events in order
    assert len(output_events) == 3
    for i, event in enumerate(output_events):
        assert event["data"]["message"] == f"Test event {i}"


@dataclass
class StreamContext:
    eventstore_host: str
    stream_name: str
    client: EventStoreDBClient

@pytest.fixture
def test_context(eventstore):
    stream_name = f"test-stream-{uuid.uuid4()}"
    client = EventStoreDBClient(uri=f"esdb://{eventstore}?tls=false")
    return StreamContext(eventstore, stream_name, client)

def get_subprocess_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return env

def run_escat(host: str, *args, env=None):
    if env is None:
        env = get_subprocess_env()
    return subprocess.run(
        ["python", "-m", "esdbcat.cli", "--host", host, *args],
        capture_output=True,
        text=True,
        env=env
    )

def write_test_events(client: EventStoreDBClient, stream_name: str, count: int, prefix: str = "Test") -> None:
    """Write a series of test events to the stream."""
    print(f"Writing {count} test events to {stream_name}...")
    for i in range(count):
        data = json.dumps({"body": {"message": f"{prefix} event {i}"}}).encode()
        client.append_to_stream(
            stream_name,
            current_version=StreamState.ANY,
            events=[NewEvent(
                type="TestEvent",
                data=data
            )]
        )
    print("Test events written successfully")

def read_process_output(process: subprocess.Popen, expected_count: int, timeout_seconds: int = 10) -> List[Dict[str, Any]]:
    """Read output from a process until expected count or timeout."""
    print("Reading output from esdbcat...")
    output = []
    timeout = time.time() + timeout_seconds
    while len(output) < expected_count and time.time() < timeout:
        line = process.stdout.readline()
        if not line:
            print("No more output from esdbcat")
            break
        print(f"Got line from esdbcat: {line.strip()}")
        output.append(json.loads(line))
    return output

def test_follow_and_count(test_context):
    print("\nSetting up test_follow_and_count...")
    expected_events = 2
    
    print(f"Starting escat process to follow {test_context.stream_name}...")
    env = get_subprocess_env()
    process = subprocess.Popen(
        ["python", "-m", "esdbcat.cli", "--host", test_context.eventstore_host, 
         "-f", "-c", str(expected_events), "-q", test_context.stream_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
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

def test_offset_options(test_context):
    # Test reading from end
    result = run_escat(test_context.eventstore_host, "-o", "end", "-q", test_context.stream_name)
    assert result.stdout.strip() == ""  # Should be empty when reading from end
    
    # Test reading last event
    result = run_escat(test_context.eventstore_host, "-o", "last", "-q", test_context.stream_name)
    assert len(result.stdout.strip().split('\n')) == 1  # Should only get one event
