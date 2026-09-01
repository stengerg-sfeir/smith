import click
from database import Database
from loan_service import LoanService

DB_PATH = "library.db"

@click.group()
def cli():
    """Application root."""

@cli.command('book-add')
@click.option('--title', required=True)
@click.option('--author', required=True)
@click.option('--isbn', required=True)
@click.option('--available-copies', type=int, required=True)
def book_add(title, author, isbn, available_copies):
    """book/add"""
    svc = LoanService(Database(DB_PATH))
    result = svc.add_book(title=title, author=author, isbn=isbn, available_copies=available_copies)

@cli.command('book-delete')
@click.option('--id', type=int, required=True)
def book_delete(id):
    """book/delete"""
    svc = LoanService(Database(DB_PATH))
    result = svc.delete_book(id=id)

@cli.command('book-list')
@click.option('--title')
@click.option('--author')
@click.option('--isbn')
@click.option('--available-copies')
def book_list(title, author, isbn, available_copies):
    """book/list"""
    svc = LoanService(Database(DB_PATH))
    result = svc.list_book(title=title, author=author, isbn=isbn, available_copies=available_copies)

@cli.command('member-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
@click.option('--membership-since')
def member_add(name, email, phone, membership_since):
    """member/add"""
    svc = LoanService(Database(DB_PATH))
    result = svc.add_member(name=name, email=email, phone=phone, membership_since=membership_since)

@cli.command('member-list')
@click.option('--name')
@click.option('--email')
@click.option('--membership-since')
def member_list(name, email, membership_since):
    """member/list"""
    svc = LoanService(Database(DB_PATH))
    result = svc.list_member(name=name, email=email, membership_since=membership_since)

@cli.command('member-loan')
@click.option('--id', type=int, required=True)
def member_loan(id):
    """member/loan"""
    svc = LoanService(Database(DB_PATH))
    result = svc.loan_member(id=id)

@cli.command('book-return')
@click.option('--id', type=int, required=True)
def book_return(id):
    """book/return"""
    svc = LoanService(Database(DB_PATH))
    result = svc.return_book(id=id)

@cli.command('book-check')
@click.option('--id', type=int, required=True)
def book_check(id):
    """book/check"""
    svc = LoanService(Database(DB_PATH))
    result = svc.check_book(id=id)


if __name__ == "__main__":
    cli()

