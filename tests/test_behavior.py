import json
import subprocess
import time
import uuid
from typing import List, Dict, Any
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from esdbclient import EventStoreDBClient, StreamState, NewEvent
import pytest

class EventStoreContainer(DockerContainer):
    def __init__(self):
        super().__init__("eventstore/eventstore:20.10.2-buster-slim")
        self.with_exposed_ports(2114)
        self.with_env("EVENTSTORE_INSECURE", "true")
        self.with_env("EVENTSTORE_EXT_TCP_PORT", "1114")
        self.with_env("EVENTSTORE_EXT_HTTP_PORT", "2114")

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
            port = container.get_exposed_port(2114)
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

def test_basic_stream_reading(eventstore):
    print("\nSetting up test_basic_stream_reading...")
    stream_name = "test-stream"
    
    # Create EventStore client to write test events
    client = EventStoreDBClient(uri=f"esdb://{eventstore}?tls=false")
    print(f"Writing test events to {stream_name}...")
    
    # Write test events
    for i in range(3):
        client.append_to_stream(
            stream_name,
            current_version=StreamState.NO_STREAM,
            events=[{
                'type': 'TestEvent',
                'data': json.dumps({"body": {"message": f"Test event {i}"}}),
            }]
        )
    print("Test events written successfully")
    
    # Run escat to read the events
    result = subprocess.run(
        ["escat", "--host", eventstore, "-q", stream_name],
        capture_output=True,
        text=True
    )
    
    # Parse the output
    output_events = [
        json.loads(line) for line in result.stdout.strip().split('\n')
        if line.strip()
    ]
    
    # Verify we got all events in order
    assert len(output_events) == 3
    for i, event in enumerate(output_events):
        assert event["message"] == f"Test event {i}"


def write_test_events(client: EventStoreDBClient, stream_name: str, count: int) -> None:
    """Write a series of test events to the stream."""
    print(f"Writing {count} test events to {stream_name}...")
    for i in range(count):
        data = json.dumps({"body": {"message": f"Follow event {i}"}}).encode()
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
    print("Reading output from escat...")
    output = []
    timeout = time.time() + timeout_seconds
    while len(output) < expected_count and time.time() < timeout:
        line = process.stdout.readline()
        if not line:
            print("No more output from escat")
            break
        print(f"Got line from escat: {line.strip()}")
        output.append(json.loads(line))
    return output

def test_follow_and_count(eventstore):
    print("\nSetting up test_follow_and_count...")
    stream_name = "test-follow"
    expected_events = 2
    
    print(f"Starting escat process to follow {stream_name}...")
    process = subprocess.Popen(
        ["escat", "--host", eventstore, "-f", "-c", str(expected_events), "-q", stream_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        print("Waiting for escat to initialize...")
        time.sleep(1)
        
        print("Creating EventStore client...")
        client = EventStoreDBClient(uri=f"esdb://{eventstore}?tls=false")
        
        write_test_events(client, stream_name, 3)
        output = read_process_output(process, expected_events)
    
    finally:
        process.terminate()
        process.wait()
    
    assert len(output) == expected_events
    assert all("Follow event" in event["data"]["message"] for event in output)

def test_offset_options(eventstore):
    stream_name = "test-offset"
    
    # Test reading from end
    result = subprocess.run(
        ["escat", "--host", eventstore, "-o", "end", "-q", stream_name],
        capture_output=True,
        text=True
    )
    assert result.stdout.strip() == ""  # Should be empty when reading from end
    
    # Test reading last event
    result = subprocess.run(
        ["escat", "--host", eventstore, "-o", "last", "-q", stream_name],
        capture_output=True,
        text=True
    )
    assert len(result.stdout.strip().split('\n')) == 1  # Should only get one event
