import click
from book_service import BookService
from database import Database

DB_PATH = "library.db"

@click.group()
def cli():
    """Application root."""

@cli.command('member-borrow')
@click.option('--id', type=int, required=True)
def member_borrow(id):
    """member/borrow"""
    svc = BookService(Database(DB_PATH))
    result = svc.borrow_member(id=id)

@cli.command('book-return')
@click.option('--id', type=int, required=True)
def book_return(id):
    """book/return"""
    svc = BookService(Database(DB_PATH))
    result = svc.return_book(id=id)


if __name__ == "__main__":
    cli()

