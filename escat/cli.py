import click
import json
from esdbclient import EventStoreDBClient

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
    
    try:
        if stream_name == "$all":
            events = client.read_all()
        else:
            events = client.read_stream(stream_name)
            
        for event in events:
            # Parse bytes data as JSON
            event_data = json.loads(event.data)
            if isinstance(event_data, dict) and 'body' in event_data:
                if with_metadata:
                    output = {
                        "data": event_data['body'],
                        "metadata": {
                            "id": str(event.id),
                            "timestamp": event.created.isoformat(),
                            "type": event.type,
                            "stream": event.stream_name,
                            "revision": event.revision,
                        }
                    }
                    # Add correlation/causation IDs if present in custom metadata
                    if event.custom_metadata:
                        metadata = json.loads(event.custom_metadata)
                        if 'correlation-id' in metadata:
                            output["metadata"]["correlation_id"] = metadata['correlation-id']
                        if 'causation-id' in metadata:
                            output["metadata"]["causation_id"] = metadata['causation-id']
                    click.echo(json.dumps(output))
                else:
                    click.echo(json.dumps(event_data['body']))
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()

if __name__ == '__main__':
    main()
