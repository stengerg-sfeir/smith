import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-place')
@click.option('--id', type=int, required=True)
def product_place(id):
    """product/place"""
    svc = OrderService(Database(DB_PATH))
    result = svc.place_product(id=id)


if __name__ == "__main__":
    cli()

