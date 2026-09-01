import click
from database import Database
from sale_service import SaleService

DB_PATH = "shop.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
def product_add(name, price, stock_quantity):
    """product/add"""
    svc = SaleService(Database(DB_PATH))
    result = svc.add_product(name=name, price=price, stock_quantity=stock_quantity)

@cli.command('product-list')
def product_list():
    """product/list"""
    svc = SaleService(Database(DB_PATH))
    result = svc.list_product()

@cli.command('product-record')
@click.option('--id', type=int, required=True)
def product_record(id):
    """product/record"""
    svc = SaleService(Database(DB_PATH))
    result = svc.record_product(id=id)

@cli.command('product-check')
@click.option('--id', type=int, required=True)
def product_check(id):
    """product/check"""
    svc = SaleService(Database(DB_PATH))
    result = svc.check_product(id=id)


if __name__ == "__main__":
    cli()

