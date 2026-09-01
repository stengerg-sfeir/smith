import click
from database import Database
from product_service import ProductService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--price', required=True)
@click.option('--quantity', type=int, required=True)
def product_add(name, price, quantity):
    """product/add"""
    svc = ProductService(Database(DB_PATH))
    result = svc.add_product(name=name, price=price, quantity=quantity)

@cli.command('product-list')
@click.option('--name')
@click.option('--price')
@click.option('--price-gte')
@click.option('--price-lte')
@click.option('--quantity')
@click.option('--quantity-gte')
@click.option('--quantity-lte')
def product_list(name, price, price_gte, price_lte, quantity, quantity_gte, quantity_lte):
    """product/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(name=name, price=price, price_gte=price_gte, price_lte=price_lte, quantity=quantity, quantity_gte=quantity_gte, quantity_lte=quantity_lte)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--price')
@click.option('--quantity', type=int)
def product_update(id, name, price, quantity):
    """product/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, price=price, quantity=quantity)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(id=id)


if __name__ == "__main__":
    cli()

