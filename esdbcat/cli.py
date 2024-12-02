import click
import json
from esdbclient import CaughtUp, EventStoreDBClient

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option('--url', help='EventStore connection URL (overrides --host if provided)')
@click.option('--host', default='localhost', help='EventStore host:port (default: localhost)')
@click.option('-f', '--follow/--no-follow', default=False, help='Follow stream for new events (default: no-follow)')
@click.option('--metadata/--no-metadata', default=True, help='Include event metadata in output (default: metadata)')
@click.option('-o', '--offset', type=click.Choice(['start', 'end', 'last']), default='start',
              help='Offset to start reading from (default: start)')
@click.option('-c', '--count', type=int, help='Exit after consuming N events')
@click.option('-q', '--quiet', is_flag=True, help='Suppress informational messages')
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
@click.argument('stream_name')
def main(url, host, follow, metadata, offset, count, quiet, verbose, stream_name):
    """Read events from an EventStore stream"""
    connection_url = url if url else f"esdb://{host}:2113?tls=false"
    client = EventStoreDBClient(uri=connection_url)

    if follow and not quiet:
        click.echo(f"Following {stream_name}...", err=True)
    
    if verbose:
        click.echo(f"Connection URL: {connection_url}", err=True)
        click.echo(f"Stream: {stream_name}", err=True)
        click.echo(f"Offset: {offset}", err=True)
    
    if stream_name == "$all":
        if offset == 'end':
            events = client.subscribe_to_all(from_end=True) if follow else []
        else:
            events = client.read_all() if not follow else client.subscribe_to_all(include_caught_up=True)
    else:
        if offset == 'end':
            events = client.subscribe_to_stream(stream_name, from_end=True) if follow else []
        elif offset == 'last':
            events = [client.get_last_stream_event(stream_name)]
        else:  # start
            events = client.read_stream(stream_name) if not follow else client.subscribe_to_stream(stream_name, include_caught_up=True)

    try:
        processed = 0
        for event in events:
            if follow and isinstance(event, CaughtUp):
                if not quiet:
                    click.echo("# caught up - waiting for new events...", err=True)
                continue
            
            if verbose:
                click.echo(f"Processing event: {event.id} ({event.type})", err=True)
            try:
                event_data = json.loads(event.data)
            except json.JSONDecodeError as e:
                click.echo(f"Error: Cannot JSON decode {event}: {str(e)}")
                continue
            if isinstance(event_data, dict) and 'body' in event_data:
                output = event_data['body']
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
                click.echo(json.dumps(output))
                
                processed += 1
                if count and processed >= count:
                    if not quiet:
                        click.echo(f"\nReached count limit ({count} events)", err=True)
                    break
                    
    except KeyboardInterrupt:
        if not quiet:
            click.echo("\nStopped following stream.", err=True)

if __name__ == '__main__':
    main()
