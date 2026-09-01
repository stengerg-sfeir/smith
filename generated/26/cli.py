import click
from database import Database
from loan_service import LoanService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('member-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def member_add(name, email, phone):
    """member/add"""
    svc = LoanService(Database(DB_PATH))
    result = svc.add_member(name=name, email=email, phone=phone)

@cli.command('book-close')
@click.option('--id', type=int, required=True)
def book_close(id):
    """book/close"""
    svc = LoanService(Database(DB_PATH))
    result = svc.close_book(id=id)

@cli.command('book-check')
@click.option('--id', type=int, required=True)
def book_check(id):
    """book/check"""
    svc = LoanService(Database(DB_PATH))
    result = svc.check_book(id=id)


if __name__ == "__main__":
    cli()

