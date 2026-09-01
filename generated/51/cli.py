import click
from database import Database
from product_service import ProductService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--sku', required=True)
@click.option('--name', required=True)
@click.option('--category', required=True)
@click.option('--price', required=True)
def product_add(sku, name, category, price):
    """product/add"""
    svc = ProductService(Database(DB_PATH))
    result = svc.add_product(sku=sku, name=name, category=category, price=price)

@cli.command('product-check')
@click.option('--id', type=int, required=True)
def product_check(id):
    """product/check"""
    svc = ProductService(Database(DB_PATH))
    result = svc.check_product(id=id)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--sku')
@click.option('--name')
@click.option('--category')
@click.option('--price')
def product_update(id, sku, name, category, price):
    """product/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(id=id, sku=sku, name=name, category=category, price=price)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('product-list')
@click.option('--sku')
@click.option('--category')
@click.option('--price')
def product_list(sku, category, price):
    """product/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(sku=sku, category=category, price=price)


if __name__ == "__main__":
    cli()

