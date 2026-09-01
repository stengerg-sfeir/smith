import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--category', required=True)
@click.option('--price', required=True)
@click.option('--quantity', type=int, required=True)
def product_add(name, category, price, quantity):
    """product/add"""
    svc = ProductService(Database(DB_PATH))
    result = svc.add_product(name=name, category=category, price=price, quantity=quantity)

@cli.command('product-list')
@click.option('--category')
@click.option('--threshold')
def product_list(category, threshold):
    """product/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(category=category, threshold=threshold)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--category')
@click.option('--price')
@click.option('--quantity', type=int)
def product_update(id, name, category, price, quantity):
    """product/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, category=category, price=price, quantity=quantity)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('product-filter')
@click.option('--id', type=int, required=True)
def product_filter(id):
    """product/filter"""
    svc = ProductService(Database(DB_PATH))
    result = svc.filter_product(id=id)


if __name__ == "__main__":
    cli()

