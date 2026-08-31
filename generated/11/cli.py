import click
from book_service import BookService
from database import Database

DB_PATH = "library.db"

@click.group()
def cli():
    """Application root."""

@cli.command('book-create')
@click.option('--title', required=True)
@click.option('--author', required=True)
@click.option('--isbn', required=True)
@click.option('--publication-year', type=int, required=True)
def book_create(title, author, isbn, publication_year):
    """book/create"""
    svc = BookService(Database(DB_PATH))
    result = svc.add_book(title=title, author=author, isbn=isbn, publication_year=publication_year)

@cli.command('book-list')
def book_list():
    """book/list"""
    svc = BookService(Database(DB_PATH))
    result = svc.list_all_books()

@cli.command('book-search')
@click.option('--term', required=True)
def book_search(term):
    """book/search"""
    svc = BookService(Database(DB_PATH))
    result = svc.search_books_by_title_or_isbn(search_term=term)

@cli.command('book-delete')
@click.option('--isbn', required=True)
def book_delete(isbn):
    """book/delete"""
    svc = BookService(Database(DB_PATH))
    result = svc.delete_book(isbn=isbn)

@cli.command('book-stats')
@click.option('--top-n', type=int)
def book_stats(top_n):
    """book/stats"""
    svc = BookService(Database(DB_PATH))
    result = svc.get_books_with_most_popular_authors(top_n=top_n)

@cli.command('book-count')
def book_count():
    """book/count"""
    svc = BookService(Database(DB_PATH))
    result = svc.get_total_books_count()


if __name__ == "__main__":
    cli()

