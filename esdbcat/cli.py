import json
import sys
import time
from typing import Any, Dict, Iterator, Optional, Union

import click
from esdbclient import CaughtUp, EventStoreDBClient, RecordedEvent
from esdbclient.exceptions import ConsumerTooSlow


def get_event_stream(
    client: EventStoreDBClient,
    stream_name: str,
    offset: str,
    follow: bool
) -> Iterator[Union[RecordedEvent, CaughtUp]]:
    """Get event stream based on parameters."""
    if offset.isdigit():
        position = int(offset)
        if stream_name == "$all":
            return (client.read_all(commit_position=position, resolve_links=True) if not follow
                    else client.subscribe_to_all(commit_position=position, include_caught_up=True, resolve_links=True))
        return (client.read_stream(stream_name, stream_position=position, resolve_links=True) if not follow
                else client.subscribe_to_stream(
                    stream_name,
                    stream_position=position,
                    include_caught_up=True,
                    resolve_links=True))

    # Handle string-based offsets
    if stream_name == "$all":
        if offset == 'end':
            return client.subscribe_to_all(from_end=True, resolve_links=True) if follow else iter([])
        return (client.read_all(resolve_links=True) if not follow
                else client.subscribe_to_all(include_caught_up=True, resolve_links=True))

    if offset == 'end':
        return client.subscribe_to_stream(stream_name, from_end=True, resolve_links=True) if follow else iter([])
    if offset == 'start':
        return (client.read_stream(stream_name, resolve_links=True) if not follow
                else client.subscribe_to_stream(stream_name, include_caught_up=True, resolve_links=True))
    raise click.BadParameter(f'Invalid offset value: {offset}')


def process_event(
    event: RecordedEvent,
    metadata: bool,
    verbose: bool
) -> Optional[Dict[str, Any]]:
    """Process a single event and return the output dictionary."""
    if verbose:
        click.echo(f"# Processing event: {event.id} ({event.type})", err=True)

    try:
        event_data: Dict[str, Any] = json.loads(event.data)
    except json.JSONDecodeError as e:
        click.echo(f"# Error: Cannot JSON decode {event}: {e!s}")
        return None

    output: Dict[str, Any] = event_data
    if metadata:
        event_metadata = json.loads(event.metadata or '{}')
        event_metadata.update({
            "id": str(event.id),
            "type": event.type,
            "stream": event.stream_name,
        })
        output = {
            "data": output,
            "metadata": event_metadata
        }
    return output


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option('--url', help='EventStore connection URL (overrides --host if provided)')
@click.option('--host', default='localhost', help='EventStore host:port (default: localhost)')
@click.option('-f', '--follow/--no-follow', default=False,
              help='Follow stream for new events (default: no-follow)')
@click.option('--metadata/--no-metadata', default=True,
              help='Include event metadata in output (default: metadata)')
@click.option('-o', '--offset', default='start',
              help='Offset to start reading from (default: start, can be: start/end or a numeric position)')
@click.option('-c', '--count', type=int, help='Exit after consuming N events')
@click.option('-q', '--quiet', is_flag=True, help='Suppress informational messages')
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
@click.option('-t', '--type', 'event_type', help='Filter events by type')
@click.argument('stream_name')
def main(url: Optional[str], host: str, follow: bool, metadata: bool,  # noqa: PLR0913, PLR0912
         offset: str, count: Optional[int], quiet: bool, verbose: bool,
         event_type: Optional[str], stream_name: str) -> None:
    """Read events from an EventStore stream"""
    connection_url = url if url else f"esdb://{host}:2113?tls=false"
    client = EventStoreDBClient(uri=connection_url)

    if follow and not quiet:
        click.echo(f"# Following {stream_name}...", err=True)

    if verbose:
        click.echo(f"# Connection URL: {connection_url}", err=True)
        click.echo(f"# Stream: {stream_name}", err=True)
        click.echo(f"# Offset: {offset}", err=True)

    events = get_event_stream(client, stream_name, offset, follow)

    processed = 0
    last_position: Optional[int] = None

    while True:
        try:
            if last_position:
                if not quiet:
                    click.echo(f"# Resuming from last position {last_position}", err=True)
                events = get_event_stream(client, stream_name, str(last_position), follow)

            for event in events:
                if follow and isinstance(event, CaughtUp):
                    if not quiet:
                        click.echo("# caught up - waiting for new events...", err=True)
                    continue

                if isinstance(event, RecordedEvent):
                    last_position = event.commit_position

                    if event_type and event.type != event_type:
                        continue

                    output = process_event(event, metadata, verbose)
                    if output:
                        click.echo(json.dumps(output))

                    processed += 1
                    if count and processed >= count:
                        if not quiet:
                            click.echo(f"# Reached count limit ({count} events)", err=True)
                        sys.exit(0)

        except ConsumerTooSlow:
            if last_position:
                if not quiet:
                    click.echo("# Consumed too slow! Connection lost.", err=True)
                time.sleep(1)  # Brief pause before retrying
                continue
            raise  # Re-raise if we have no position to resume from

        except KeyboardInterrupt:
            if not quiet:
                click.echo("# Stopped following stream.", err=True)

        break

if __name__ == '__main__':
    main()
