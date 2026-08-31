import click
from database import Database
from loan_service import LoanService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('loan-create')
@click.option('--member-id', type=int, required=True)
@click.option('--book-id', type=int, required=True)
@click.option('--loan-date', required=True)
@click.option('--due-date', required=True)
def loan_create(member_id, book_id, loan_date, due_date):
    """loan/create"""
    svc = LoanService(Database(DB_PATH))
    result = svc.create_loan(member_id=member_id, book_id=book_id, loan_date=loan_date, due_date=due_date)

@cli.command('loan-close')
@click.option('--loan-id', type=int, required=True)
def loan_close(loan_id):
    """loan/close"""
    svc = LoanService(Database(DB_PATH))
    result = svc.close_loan(loan_id=loan_id)

@cli.command('loan-available_books')
def loan_available_books():
    """loan/available_books"""
    svc = LoanService(Database(DB_PATH))
    result = svc.get_available_books()

@cli.command('loan-by_member')
@click.option('--member-id', type=int, required=True)
def loan_by_member(member_id):
    """loan/by_member"""
    svc = LoanService(Database(DB_PATH))
    result = svc.get_loans_by_member(member_id=member_id)

@cli.command('loan-overdue')
def loan_overdue():
    """loan/overdue"""
    svc = LoanService(Database(DB_PATH))
    result = svc.get_overdue_loans()

@cli.command('loan-total_by_member')
def loan_total_by_member():
    """loan/total_by_member"""
    svc = LoanService(Database(DB_PATH))
    result = svc.get_total_loans_by_member()

@cli.command('loan-active_count')
def loan_active_count():
    """loan/active_count"""
    svc = LoanService(Database(DB_PATH))
    result = svc.get_active_loans_count()

@cli.command('loan-after_return_date')
@click.option('--return-date', required=True)
def loan_after_return_date(return_date):
    """loan/after_return_date"""
    svc = LoanService(Database(DB_PATH))
    result = svc.get_loans_with_return_date_after(return_date=return_date)


if __name__ == "__main__":
    cli()

