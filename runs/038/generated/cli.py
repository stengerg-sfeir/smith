import click
from auth_service import AuthService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('authenticate-login')
@click.option('--email', required=True)
@click.option('--password', required=True)
def authenticate_login(email, password):
    """user/authenticate/login"""
    svc = AuthService(Database(DB_PATH))
    result = svc.authenticate_user(email=email, password=password)

@cli.command('documents-list')
@click.option('--user-id', type=int, required=True)
@click.option('--title-filter')
@click.option('--created-after')
@click.option('--created-before')
def documents_list(user_id, title_filter, created_after, created_before):
    """user/documents/list"""
    svc = AuthService(Database(DB_PATH))
    result = svc.get_user_documents(user_id=user_id, title_filter=title_filter, created_after=created_after, created_before=created_before)

@cli.command('documents-search')
@click.option('--user-id', type=int, required=True)
@click.option('--query', required=True)
def documents_search(user_id, query):
    """user/documents/search"""
    svc = AuthService(Database(DB_PATH))
    result = svc.search_documents_by_user(user_id=user_id, query=query)

@cli.command('documents-check_access')
@click.option('--user-id', type=int, required=True)
@click.option('--document-id', type=int, required=True)
def documents_check_access(user_id, document_id):
    """user/documents/check_access"""
    svc = AuthService(Database(DB_PATH))
    result = svc.check_document_access(user_id=user_id, document_id=document_id)


if __name__ == "__main__":
    cli()

