# escat

A command-line tool for reading EventStore streams, inspired by kafkacat.

## Installation

```bash
pip install escat
```

## Usage

Read all events from a stream:
```bash
escat my-stream
```

The output will be JSON lines with event data and metadata (by default):
```json
{
  "data": {
    "message": "Hello World"
  },
  "metadata": {
    "id": "1234-5678-90ab-cdef",
    "type": "TestEvent",
    "stream": "my-stream"
  }
}
```

Note: Your event data should be wrapped in a "body" field when writing events:
```json
{
  "body": {
    "message": "Hello World"
  }
}
```

Follow a stream for new events:
```bash
escat -f my-stream
```

Start reading from the end of the stream:
```bash
escat -o end -f my-stream
```

Read only the last event:
```bash
escat -o last my-stream
```

Exit after consuming 10 events:
```bash
escat -c 10 my-stream
```

Read the special $all stream:
```bash
escat $all
```

Quiet mode (suppress informational messages):
```bash
escat -q my-stream
```

Verbose mode for debugging:
```bash
escat -v my-stream
```

Connect to a specific EventStore instance:
```bash
escat --host eventstore.example.com:2113 my-stream
```

Or use a full connection URL:
```bash
escat --url "esdb://eventstore.example.com:2113?tls=false" my-stream
```

Read events without metadata:
```bash
escat --no-metadata my-stream
```

Connect with authentication:
```bash
escat --url "esdb://admin:changeit@localhost:2113?tls=false" my-stream
```
