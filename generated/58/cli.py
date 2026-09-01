import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-list')
@click.option('--name')
@click.option('--email')
@click.option('--created-at')
@click.option('--created-at-end')
def customer_list(name, email, created_at, created_at_end):
    """customer/list"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.list_customer(name=name, email=email, created_at=created_at, created_at_end=created_at_end)


if __name__ == "__main__":
    cli()

