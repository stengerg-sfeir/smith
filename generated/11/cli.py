import click
from book_service import BookService
from database import Database

DB_PATH = "library.db"

@click.group()
def cli():
    """Application root."""

@cli.command('book-add')
@click.option('--title', required=True)
@click.option('--author', required=True)
@click.option('--isbn', required=True)
@click.option('--publication-year', type=int, required=True)
def book_add(title, author, isbn, publication_year):
    """book/add"""
    svc = BookService(Database(DB_PATH))
    result = svc.add_book(title=title, author=author, isbn=isbn, publication_year=publication_year)

@cli.command('book-list')
@click.option('--title')
@click.option('--author')
@click.option('--publication-year')
@click.option('--publication-year-end')
def book_list(title, author, publication_year, publication_year_end):
    """book/list"""
    svc = BookService(Database(DB_PATH))
    result = svc.list_book(title=title, author=author, publication_year=publication_year, publication_year_end=publication_year_end)

@cli.command('book-update')
@click.option('--id', type=int, required=True)
@click.option('--title')
@click.option('--author')
@click.option('--isbn')
@click.option('--publication-year', type=int)
def book_update(id, title, author, isbn, publication_year):
    """book/update"""
    svc = BookService(Database(DB_PATH))
    result = svc.update_book(id=id, title=title, author=author, isbn=isbn, publication_year=publication_year)

@cli.command('book-search')
@click.option('--term', required=True)
def book_search(term):
    """book/search"""
    svc = BookService(Database(DB_PATH))
    result = svc.search_book(term=term)

@cli.command('book-delete')
@click.option('--id', type=int, required=True)
def book_delete(id):
    """book/delete"""
    svc = BookService(Database(DB_PATH))
    result = svc.delete_book(id=id)


if __name__ == "__main__":
    cli()

