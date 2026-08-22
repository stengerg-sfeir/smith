import click
from database import Database
from library_service import LibraryService

DB_PATH = "library.db"

@click.group()
def cli():
    """Application root."""

@cli.command('book-add')
@click.option('--title', required=True)
@click.option('--isbn', required=True)
@click.option('--author-id', type=int, required=True)
@click.option('--published-year', type=int, required=True)
@click.option('--copies', type=int)
def book_add(title, isbn, author_id, published_year, copies):
    """library/book/add"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.borrow_book()

@cli.command('book-list')
@click.option('--author', is_flag=True, default=False)
@click.option('--available-only', is_flag=True, default=False)
def book_list(author, available_only):
    """library/book/list"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.search_books()

@cli.command('book-search')
@click.option('--query', required=True)
def book_search(query):
    """library/book/search"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.search_books(query=query)

@cli.command('member-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
def member_add(name, email):
    """library/member/add"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.search_books()

@cli.command('member-list')
@click.option('--active-only', is_flag=True, default=False)
def member_list(active_only):
    """library/member/list"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.search_books()

@cli.command('library-borrow')
@click.option('--member-id', type=int, required=True)
@click.option('--book-id', type=int, required=True)
def library_borrow(member_id, book_id):
    """library/borrow"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.borrow_book(member_id=member_id, book_id=book_id)

@cli.command('library-return')
@click.option('--loan-id', type=int, required=True)
def library_return(loan_id):
    """library/return"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.return_book(loan_id=loan_id)

@cli.command('library-overdue')
def library_overdue():
    """library/overdue"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.get_overdue_loans()

@cli.command('member-history')
@click.option('--member-id', type=int, required=True)
def member_history(member_id):
    """library/member/history"""
    svc = LibraryService(Database(DB_PATH))
    result = svc.search_books()


if __name__ == "__main__":
    cli()

