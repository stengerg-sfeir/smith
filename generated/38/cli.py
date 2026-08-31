import click
from auth_service import AuthService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('documents-add')
@click.option('--title', required=True)
@click.option('--content', required=True)
@click.option('--user-id', type=int, required=True)
def documents_add(title, content, user_id):
    """user/documents/add"""
    svc = AuthService(Database(DB_PATH))
    result = svc.add_document(title=title, content=content, user_id=user_id)

@cli.command('documents-update')
@click.option('--id', type=int, required=True)
@click.option('--title')
@click.option('--content')
@click.option('--user-id', type=int, required=True)
def documents_update(id, title, content, user_id):
    """user/documents/update"""
    svc = AuthService(Database(DB_PATH))
    result = svc.update_document(id=id, title=title, content=content, user_id=user_id)

@cli.command('documents-delete')
@click.option('--id', type=int, required=True)
def documents_delete(id):
    """user/documents/delete"""
    svc = AuthService(Database(DB_PATH))
    result = svc.delete_user(id=id)

@cli.command('documents-list')
@click.option('--title')
@click.option('--created-at')
@click.option('--created-at-end')
def documents_list(title, created_at, created_at_end):
    """user/documents/list"""
    svc = AuthService(Database(DB_PATH))
    result = svc.list_document(title=title, created_at=created_at, created_at_end=created_at_end)


if __name__ == "__main__":
    cli()

