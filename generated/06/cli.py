import click
from database import Database
from product_service import ProductService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
@click.option('--quantity', type=int, required=True)
def product_add(name, description, price, quantity):
    """product/add"""
    svc = ProductService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price, quantity=quantity)

@cli.command('product-list')
@click.option('--name')
@click.option('--price')
@click.option('--price-max')
@click.option('--quantity')
@click.option('--quantity-max')
def product_list(name, price, price_max, quantity, quantity_max):
    """product/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(name=name, price=price, price_max=price_max, quantity=quantity, quantity_max=quantity_max)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--price')
@click.option('--quantity', type=int)
def product_update(id, name, description, price, quantity):
    """product/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, description=description, price=price, quantity=quantity)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('product-persist')
@click.option('--id', type=int, required=True)
def product_persist(id):
    """product/persist"""
    svc = ProductService(Database(DB_PATH))
    result = svc.persist_product(id=id)


if __name__ == "__main__":
    cli()

