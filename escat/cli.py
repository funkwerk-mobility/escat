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
                output = event_data['body']
                if with_metadata:
                    metadata = json.loads(event.metadata or '{}')
                    output = {
                        "data": output,
                        "metadata": {
                            "id": str(event.id),
                            "type": event.type,
                            "stream": event.stream_name,
                            "timestamp": metadata.get('timestamp'),
                            "$correlationId": metadata.get('$correlationId'),
                            "$causationId": metadata.get('$causationId')
                        }
                    }
                click.echo(json.dumps(output))
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()

if __name__ == '__main__':
    main()
