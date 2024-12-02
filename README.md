# esdbcat

[![PyPI version](https://badge.fury.io/py/esdbcat.svg)](https://badge.fury.io/py/esdbcat)
[![License](https://img.shields.io/badge/License-BSL--1.0-blue.svg)](https://opensource.org/licenses/BSL-1.0)
[![Python Versions](https://img.shields.io/pypi/pyversions/esdbcat.svg)](https://pypi.org/project/esdbcat/)

A command-line tool for reading EventStore streams, inspired by kafkacat.

## AI Code Notice

This repository was near-entirely created by Claude 3.5 Sonnet. Good job Sonnet!

## Installation

```bash
pip install esdbcat
```

## Usage

Read all events from a stream:
```bash
esdbcat my-stream
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

Follow a stream for new events:
```bash
esdbcat -f my-stream
```

Start reading from the end of the stream:
```bash
esdbcat -o end -f my-stream
```

Read only the last event:
```bash
esdbcat -o last my-stream
```

Exit after consuming 10 events:
```bash
esdbcat -c 10 my-stream
```

Read the special $all stream:
```bash
esdbcat $all
```

Quiet mode (suppress informational messages):
```bash
esdbcat -q my-stream
```

Verbose mode for debugging:
```bash
esdbcat -v my-stream
```

Connect to a specific EventStore instance:
```bash
esdbcat --host eventstore.example.com:2113 my-stream
```

Or use a full connection URL:
```bash
esdbcat --url "esdb://eventstore.example.com:2113?tls=false" my-stream
```

Read events without metadata:
```bash
esdbcat --no-metadata my-stream
```

Connect with authentication:
```bash
esdbcat --url "esdb://admin:changeit@localhost:2113?tls=false" my-stream
```
