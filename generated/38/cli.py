import click
from database import Database
from document_service import DocumentService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('document-create')
@click.option('--title', required=True)
@click.option('--content', required=True)
@click.option('--user-id', type=int, required=True)
def document_create(title, content, user_id):
    """document/create"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.add_document(title=title, content=content, user_id=user_id)

@cli.command('document-update')
@click.option('--id', type=int, required=True)
@click.option('--title')
@click.option('--content')
@click.option('--user-id', type=int, required=True)
def document_update(id, title, content, user_id):
    """document/update"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.update_document(id=id, title=title, content=content, user_id=user_id)

@cli.command('document-list')
@click.option('--title')
@click.option('--created-after')
@click.option('--created-before')
def document_list(title, created_after, created_before):
    """document/list"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.list_document(title=title, created_at=created_after, created_at_end=created_before)

@cli.command('user-add')
@click.option('--email', required=True)
@click.option('--password', required=True)
def user_add(email, password):
    """user/add"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.add_user(email=email, password_hash=password)

@cli.command('document-delete')
@click.option('--id', type=int, required=True)
def document_delete(id):
    """document/delete"""
    svc = DocumentService(Database(DB_PATH))
    result = svc.delete_document(id=id)


if __name__ == "__main__":
    cli()

