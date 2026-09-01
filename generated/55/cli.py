import click
from database import Database
from sale_service import SaleService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
def product_add(name, description, price, stock_quantity):
    """product/add"""
    svc = SaleService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price, stock_quantity=stock_quantity)

@cli.command('product-sell')
@click.option('--id', type=int, required=True)
def product_sell(id):
    """product/sell"""
    svc = SaleService(Database(DB_PATH))
    result = svc.sell_product(id=id)

@cli.command('product-check')
@click.option('--id', type=int, required=True)
def product_check(id):
    """product/check"""
    svc = SaleService(Database(DB_PATH))
    result = svc.check_product(id=id)


if __name__ == "__main__":
    cli()

