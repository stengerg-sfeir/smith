import click
from author_service import AuthorService
from database import Database

DB_PATH = "library.db"

@click.group()
def cli():
    """Application root."""

@cli.command('book-add')
@click.option('--title', required=True)
@click.option('--isbn', required=True)
@click.option('--author-id', type=int, required=True)
@click.option('--published-year', type=int, required=True)
@click.option('--copies', type=int, required=True)
def book_add(title, isbn, author_id, published_year, copies):
    """library/book/add"""
    svc = AuthorService(Database(DB_PATH))
    result = svc.add_book(title=title, isbn=isbn, author_id=author_id, published_year=published_year, available_copies=copies)

@cli.command('book-list')
@click.option('--author', type=int)
@click.option('--available-only', is_flag=True, default=False)
def book_list(author, available_only):
    """library/book/list"""
    svc = AuthorService(Database(DB_PATH))
    result = svc.list_book(author_id=author, available_only=available_only)

@cli.command('book-search')
@click.option('--query', required=True)
def book_search(query):
    """library/book/search"""
    svc = AuthorService(Database(DB_PATH))
    result = svc.search(query=query)

@cli.command('member-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
def member_add(name, email):
    """library/member/add"""
    svc = AuthorService(Database(DB_PATH))
    result = svc.add(name=name, email=email)

@cli.command('member-list')
@click.option('--active-only', is_flag=True, default=False)
def member_list(active_only):
    """library/member/list"""
    svc = AuthorService(Database(DB_PATH))
    result = svc.list(active_only=active_only)

@cli.command('member-history')
@click.option('--member-id', type=int, required=True)
def member_history(member_id):
    """library/member/history"""
    svc = AuthorService(Database(DB_PATH))
    result = svc.get_member_history(member_id=member_id)


if __name__ == "__main__":
    cli()

