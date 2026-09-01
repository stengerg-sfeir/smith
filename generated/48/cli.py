import click
from book_service import BookService
from database import Database

DB_PATH = "books.db"

@click.group()
def cli():
    """Application root."""

@cli.command('book-add')
@click.option('--title', required=True)
@click.option('--author', required=True)
@click.option('--isbn', required=True)
@click.option('--publication-year', type=int)
@click.option('--genre')
@click.option('--pages', type=int)
def book_add(title, author, isbn, publication_year, genre, pages):
    """book/add"""
    svc = BookService(Database(DB_PATH))
    result = svc.add_book(title=title, author=author, isbn=isbn, publication_year=publication_year, genre=genre, pages=pages)

@cli.command('book-search')
@click.option('--term', required=True)
def book_search(term):
    """book/search"""
    svc = BookService(Database(DB_PATH))
    result = svc.search_book(term=term)

@cli.command('book-organize')
@click.option('--id', type=int, required=True)
def book_organize(id):
    """book/organize"""
    svc = BookService(Database(DB_PATH))
    result = svc.organize_book(id=id)


if __name__ == "__main__":
    cli()

