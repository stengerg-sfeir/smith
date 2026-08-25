import click
from book_service import BookService
from database import Database

DB_PATH = "books.db"

@click.group()
def cli():
    """Application root."""

@cli.command('manage-create')
@click.option('--title', required=True)
@click.option('--author', required=True)
@click.option('--isbn')
@click.option('--publication-year', type=int)
@click.option('--genre')
@click.option('--pages', type=int)
def manage_create(title, author, isbn, publication_year, genre, pages):
    """book/manage/create"""
    svc = BookService(Database(DB_PATH))
    result = svc.add_book(title=title, author=author, isbn=isbn, publication_year=publication_year, genre=genre, pages=pages)

@cli.command('book-list')
def book_list():
    """book/list"""
    svc = BookService(Database(DB_PATH))
    result = svc.list_books()

@cli.command('book-report')
def book_report():
    """book/report"""
    svc = BookService(Database(DB_PATH))
    result = svc.generate_genre_distribution_report()


if __name__ == "__main__":
    cli()

