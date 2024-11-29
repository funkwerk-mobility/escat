import json
import subprocess
import time
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
import pytest

class EventStoreContainer(DockerContainer):
    def __init__(self):
        super().__init__("eventstore/eventstore:latest")
        self.with_exposed_ports(2113)
        self.with_env("EVENTSTORE_INSECURE", "true")
        self.with_env("EVENTSTORE_ENABLE_EXTERNAL_TCP", "true")
        self.with_env("EVENTSTORE_ENABLE_ATOM_PUB_OVER_HTTP", "true")

@pytest.fixture(scope="session")
def eventstore():
    container = EventStoreContainer()
    with container:
        # Wait for EventStore to be ready
        wait_for_logs(container, "EventStoreDB started")
        time.sleep(2)  # Give it a moment to fully initialize
        port = container.get_exposed_port(2113)
        yield f"localhost:{port}"

def test_basic_stream_reading(eventstore):
    # First, write some test events using the HTTP API
    stream_name = "test-stream"
    test_events = [
        {"body": {"message": f"Test event {i}"}} for i in range(3)
    ]
    
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
