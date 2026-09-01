import click
from database import Database
from document_service import DocumentService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('manage-add')
@click.option('--title', required=True)
@click.option('--content', required=True)
@click.option('--file-path', required=True)
@click.option('--author-id', type=int, required=True)
def manage_add(title, content, file_path, author_id):
    """document/manage/add"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.add(title=title, content=content, file_path=file_path, author_id=author_id)

@cli.command('manage-update')
@click.option('--title', required=True)
@click.option('--content', required=True)
@click.option('--file-path', required=True)
def manage_update(title, content, file_path):
    """document/manage/update"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.update(title=title, content=content, file_path=file_path)

@cli.command('manage-delete')
@click.option('--title', required=True)
@click.option('--author-id', type=int, required=True)
def manage_delete(title, author_id):
    """document/manage/delete"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.delete(title=title, author_id=author_id)

@cli.command('document-list')
@click.option('--author-id', type=int)
@click.option('--start-date')
@click.option('--end-date')
@click.option('--keywords')
def document_list(author_id, start_date, end_date, keywords):
    """document/list"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.list(author_id=author_id, start_date=start_date, end_date=end_date, keywords=keywords)


if __name__ == "__main__":
    cli()

