import click
import json
from esdbclient import CaughtUp, EventStoreDBClient

@click.command()
@click.option('--host', default='localhost', help='EventStore host')
@click.option('--port', default=2113, help='EventStore port')
@click.option('--follow/--no-follow', default=False, help='Follow stream for new events')
@click.option('--with-metadata/--no-metadata', default=False, help='Include event metadata in output')
@click.argument('stream_name')
def main(host, port, follow, with_metadata, stream_name):
    """Read events from an EventStore stream"""
    client = EventStoreDBClient(
        uri=f"esdb://{host}:{port}?tls=false"
    )

    if follow:
        click.echo(f"Following {stream_name}...", err=True)
    
    if stream_name == "$all":
        events = client.read_all() if not follow else client.subscribe_to_all(include_caught_up=True)
    else:
        events = client.read_stream(stream_name) if not follow else client.subscribe_to_stream(stream_name, include_caught_up=True)

    try:
        for event in events:
            if follow and isinstance(event, CaughtUp):
                click.echo("# caught up - waiting for new events...", err=True)
                continue
            try:
                event_data = json.loads(event.data)
            except json.JSONDecodeError as e:
                click.echo(f"Error: Cannot JSON decode {event}: {str(e)}")
                continue
            if isinstance(event_data, dict) and 'body' in event_data:
                output = event_data['body']
                if with_metadata:
                    metadata = json.loads(event.metadata or '{}')
                    metadata.update({
                        "id": str(event.id),
                        "type": event.type,
                        "stream": event.stream_name,
                    })
                    output = {
                        "data": output,
                        "metadata": metadata
                    }
                click.echo(json.dumps(output))
    except KeyboardInterrupt:
        click.echo("\nStopped following stream.", err=True)

if __name__ == '__main__':
    main()
