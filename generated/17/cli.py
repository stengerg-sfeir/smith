import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-search')
@click.option('--term', required=True)
def product_search(term):
    """product/search"""
    svc = ProductService(Database(DB_PATH))
    result = svc.search_product(term=term)

@cli.command('product-filter')
@click.option('--id', type=int, required=True)
def product_filter(id):
    """product/filter"""
    svc = ProductService(Database(DB_PATH))
    result = svc.filter_product(id=id)

@cli.command('product-specify')
@click.option('--id', type=int, required=True)
def product_specify(id):
    """product/specify"""
    svc = ProductService(Database(DB_PATH))
    result = svc.specify_product(id=id)


if __name__ == "__main__":
    cli()

