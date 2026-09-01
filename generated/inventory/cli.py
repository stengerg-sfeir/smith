import click
from category_service import CategoryService
from database import Database

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--sku', required=True)
@click.option('--name', required=True)
@click.option('--category', type=int, required=True)
@click.option('--price', type=int, required=True)
@click.option('--stock', type=int, required=True)
def product_add(sku, name, category, price, stock):
    """product/add"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.add_product(sku=sku, name=name, category_id=category, price_cents=price, stock_qty=stock)

@cli.command('product-list')
@click.option('--category', type=int)
@click.option('--low-only', is_flag=True, default=False)
def product_list(category, low_only):
    """product/list"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.list_product(category_id=category, low_only=low_only)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--price', type=int)
@click.option('--category', type=int)
def product_update(id, name, price, category):
    """product/update"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, price_cents=price, category_id=category)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.delete(id=id)

@cli.command('product-report')
def product_report():
    """product/report"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.report()

@cli.command('category-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--threshold', type=int)
def category_add(name, description, threshold):
    """category/add"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.add(name=name, description=description, reorder_threshold=threshold)

@cli.command('category-list')
def category_list():
    """category/list"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.list()

@cli.command('category-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--threshold', type=int)
def category_update(id, name, description, threshold):
    """category/update"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.update(id=id, name=name, description=description, reorder_threshold=threshold)

@cli.command('category-delete')
@click.option('--id', type=int, required=True)
def category_delete(id):
    """category/delete"""
    svc = CategoryService(Database(DB_PATH))
    result = svc.delete(id=id)


if __name__ == "__main__":
    cli()

