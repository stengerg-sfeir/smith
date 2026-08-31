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


if __name__ == "__main__":
    cli()

