import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
@click.option('--category')
def product_add(name, description, price, stock_quantity, category):
    """product/add"""
    svc = ProductService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price, stock_quantity=stock_quantity, category=category)

@cli.command('product-list')
@click.option('--name')
@click.option('--category')
@click.option('--price-min')
@click.option('--price-max')
@click.option('--stock-min')
@click.option('--stock-max')
def product_list(name, category, price_min, price_max, stock_min, stock_max):
    """product/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(name=name, category=category, price_min=price_min, price_max=price_max, stock_min=stock_min, stock_max=stock_max)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--price')
@click.option('--stock-quantity', type=int)
@click.option('--category')
def product_update(id, name, description, price, stock_quantity, category):
    """product/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, description=description, price=price, stock_quantity=stock_quantity, category=category)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('product-bulk-update')
@click.option('--ids', required=True)
@click.option('--name')
@click.option('--description')
@click.option('--price')
@click.option('--stock-quantity', type=int)
@click.option('--category')
def product_bulk_update(ids, name, description, price, stock_quantity, category):
    """product/bulk-update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.bulk_update_product(ids=ids, name=name, description=description, price=price, stock_quantity=stock_quantity, category=category)


if __name__ == "__main__":
    cli()

