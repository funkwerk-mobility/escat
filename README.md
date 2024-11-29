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
escat --follow my-stream
```

Connect to a specific EventStore instance:
```bash
escat --host eventstore.example.com --port 2113 my-stream
```
