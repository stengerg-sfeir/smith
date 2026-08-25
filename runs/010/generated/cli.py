import click
from database import Database
from note_service import NoteService

DB_PATH = "notes.db"

@click.group()
def cli():
    """Application root."""

@cli.command('notes-create')
@click.option('--title', required=True)
@click.option('--content', required=True)
def notes_create(title, content):
    """notes/create"""
    svc = NoteService(Database(DB_PATH))
    result = svc.create_note(title=title, content=content)

@cli.command('notes-list')
@click.option('--title-filter')
@click.option('--created-after')
@click.option('--created-before')
def notes_list(title_filter, created_after, created_before):
    """notes/list"""
    svc = NoteService(Database(DB_PATH))
    result = svc.list_notes(title_filter=title_filter, created_after=created_after, created_before=created_before)

@cli.command('notes-update')
@click.option('--note-id', type=int, required=True)
@click.option('--title')
@click.option('--content')
def notes_update(note_id, title, content):
    """notes/update"""
    svc = NoteService(Database(DB_PATH))
    result = svc.update_note(note_id=note_id, title=title, content=content)

@cli.command('notes-delete')
@click.option('--note-id', type=int, required=True)
def notes_delete(note_id):
    """notes/delete"""
    svc = NoteService(Database(DB_PATH))
    result = svc.delete_note(note_id=note_id)

@cli.command('notes-search')
@click.option('--query', required=True)
def notes_search(query):
    """notes/search"""
    svc = NoteService(Database(DB_PATH))
    result = svc.search_notes(query=query)

@cli.command('notes-monthly')
@click.option('--year-month', required=True)
def notes_monthly(year_month):
    """notes/monthly"""
    svc = NoteService(Database(DB_PATH))
    result = svc.get_notes_by_month(year_month=year_month)


if __name__ == "__main__":
    cli()

