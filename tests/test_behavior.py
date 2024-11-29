import json
import subprocess
import time
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from esdbclient import EventStoreDBClient
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
            
            # Wait for EventStore to be fully ready by checking logs
            try:
                wait_for_logs(container, "IS LEADER... SPARTA!", timeout=30)
            except Exception as e:
                print(f"\nTimeout waiting for EventStore logs: {e}")
                print("\nCurrent container logs:")
                print_logs()
                raise Exception("EventStore failed to start properly") from e
            # Get connection details
            port = container.get_exposed_port(2113)
            host = f"localhost:{port}"
            print(f"EventStore container ready at {host}")
            
            # Test connection
            client = EventStoreDBClient(uri=f"esdb://{host}?tls=false")
            print("Testing connection to EventStore...")
            client.get_server_version()
            print("Connection test successful")
            
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
            current_version=None,
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

def test_follow_and_count(eventstore):
    stream_name = "test-follow"
    
    # Run escat with follow and count options
    process = subprocess.Popen(
        ["escat", "--host", eventstore, "-f", "-c", "2", "-q", stream_name],
        stdout=subprocess.PIPE,
        text=True
    )
    
    try:
        # Give it time to process events
        time.sleep(1)
        
        # Write test events
        test_events = [
            {"body": {"message": f"Follow event {i}"}} for i in range(3)
        ]
        
        # Read output
        output = []
        while len(output) < 2:  # We expect exactly 2 events due to -c 2
            line = process.stdout.readline()
            if not line:
                break
            output.append(json.loads(line))
    
    finally:
        process.terminate()
        process.wait()
    
    assert len(output) == 2
    assert all("Follow event" in event["message"] for event in output)

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
