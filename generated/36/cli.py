import click
from database import Database
from product_service import ProductService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('category-add')
@click.option('--name', required=True)
def category_add(name):
    """category/add"""
    svc = ProductService(Database(DB_PATH))
    result = svc.add_category(name=name)

@cli.command('category-list')
def category_list():
    """category/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_category()

@cli.command('product-list')
@click.option('--name')
@click.option('--price')
@click.option('--category-id')
def product_list(name, price, category_id):
    """product/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(name=name, price=price, category_id=category_id)

@cli.command('category-delete')
@click.option('--id', type=int, required=True)
def category_delete(id):
    """category/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_category(id=id)

@cli.command('category-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
def category_update(id, name):
    """category/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_category(id=id, name=name)


if __name__ == "__main__":
    cli()

