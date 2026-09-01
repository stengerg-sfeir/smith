import click
from database import Database
from event_service import EventService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('event-add')
@click.option('--title', required=True)
@click.option('--description')
@click.option('--max-participants', type=int, required=True)
@click.option('--current-participants', type=int, required=True)
@click.option('--start-time', required=True)
@click.option('--end-time', required=True)
def event_add(title, description, max_participants, current_participants, start_time, end_time):
    """event/add"""
    svc = EventService(Database(DB_PATH))
    result = svc.add_event(title=title, description=description, max_participants=max_participants, current_participants=current_participants, start_time=start_time, end_time=end_time)

@cli.command('event-register')
@click.option('--id', type=int, required=True)
def event_register(id):
    """event/register"""
    svc = EventService(Database(DB_PATH))
    result = svc.register_event(id=id)


if __name__ == "__main__":
    cli()

