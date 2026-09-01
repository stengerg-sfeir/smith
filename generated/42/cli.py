import click
from database import Database
from purchase_service import PurchaseService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-search')
@click.option('--term', required=True)
def customer_search(term):
    """customer/search"""
    svc = PurchaseService(Database(DB_PATH))
    result = svc.search_customer(term=term)

@cli.command('customer-report')
@click.option('--id', type=int, required=True)
def customer_report(id):
    """customer/report"""
    svc = PurchaseService(Database(DB_PATH))
    result = svc.get_customer_report(id=id)


if __name__ == "__main__":
    cli()

