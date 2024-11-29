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

Read events without metadata (metadata included by default):
```bash
escat --no-metadata my-stream
```

Connect with authentication:
```bash
escat --url "esdb://admin:changeit@localhost:2113?tls=false" my-stream
```
