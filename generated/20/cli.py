import click
from database import Database
from sale_service import SaleService

DB_PATH = "sales.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--price', required=True)
def product_add(name, price):
    """product/add"""
    svc = SaleService(Database(DB_PATH))
    result = svc.add_product(name=name, price=price)

@cli.command('product-list')
def product_list():
    """product/list"""
    svc = SaleService(Database(DB_PATH))
    result = svc.list_product()

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--price')
def product_update(id, name, price):
    """product/update"""
    svc = SaleService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, price=price)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = SaleService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('sale-add')
@click.option('--product-id', type=int, required=True)
@click.option('--quantity', type=int, required=True)
def sale_add(product_id, quantity):
    """sale/add"""
    svc = SaleService(Database(DB_PATH))
    result = svc.add_sale(product_id=product_id, quantity=quantity)

@cli.command('sale-list')
@click.option('--product-id')
@click.option('--sale-date-from')
@click.option('--sale-date-to')
def sale_list(product_id, sale_date_from, sale_date_to):
    """sale/list"""
    svc = SaleService(Database(DB_PATH))
    result = svc.list_sale(product_id=product_id, sale_date_from=sale_date_from, sale_date_to=sale_date_to)

@cli.command('product-report')
@click.option('--id', type=int, required=True)
def product_report(id):
    """product/report"""
    svc = SaleService(Database(DB_PATH))
    result = svc.get_product_report(id=id)


if __name__ == "__main__":
    cli()

