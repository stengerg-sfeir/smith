import click
from database import Database
from note_service import NoteService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('notes-create')
@click.option('--title', required=True)
@click.option('--content', required=True)
def notes_create(title, content):
    """notes/create"""
    svc = NoteService(Database(DB_PATH))
    result = svc.add(title=title, content=content)

@cli.command('notes-list')
@click.option('--title')
@click.option('--start-date')
@click.option('--end-date')
def notes_list(title, start_date, end_date):
    """notes/list"""
    svc = NoteService(Database(DB_PATH))
    result = svc.list(title=title, start_date=start_date, end_date=end_date)

@cli.command('notes-update')
@click.option('--note-id', type=int, required=True)
@click.option('--title')
@click.option('--content')
def notes_update(note_id, title, content):
    """notes/update"""
    svc = NoteService(Database(DB_PATH))
    result = svc.update(note_id=note_id, new_title=title, new_content=content)

@cli.command('notes-delete')
@click.option('--note-id', type=int, required=True)
def notes_delete(note_id):
    """notes/delete"""
    svc = NoteService(Database(DB_PATH))
    result = svc.delete(note_id=note_id)


if __name__ == "__main__":
    cli()

