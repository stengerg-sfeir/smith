import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-create')
@click.option('--name', required=True)
@click.option('--category', required=True)
@click.option('--price', type=int, required=True)
@click.option('--quantity', type=int, required=True)
def product_create(name, category, price, quantity):
    """product/create"""
    svc = ProductService(Database(DB_PATH))
    result = svc.create_product(name=name, category=category, price=price, quantity=quantity)

@cli.command('read-list')
@click.option('--category')
@click.option('--threshold', type=int)
def read_list(category, threshold):
    """product/read/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(category=category, threshold=threshold)

@cli.command('read-low_stock')
def read_low_stock():
    """product/read/low_stock"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_low_stock_products()

@cli.command('read-by_category')
@click.option('--category', required=True)
def read_by_category(category):
    """product/read/by_category"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_by_category(category=category)

@cli.command('read-by_price_range')
@click.option('--min-price', type=int, required=True)
@click.option('--max-price', type=int, required=True)
def read_by_price_range(min_price, max_price):
    """product/read/by_price_range"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_with_price_range(min_price=min_price, max_price=max_price)

@cli.command('product-update')
@click.option('--product-id', type=int, required=True)
@click.option('--name')
@click.option('--category')
@click.option('--price', type=int)
@click.option('--quantity', type=int)
def product_update(product_id, name, category, price, quantity):
    """product/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(product_id=product_id, name=name, category=category, price=price, quantity=quantity)

@cli.command('product-delete')
@click.option('--product-id', type=int, required=True)
def product_delete(product_id):
    """product/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(product_id=product_id)

@cli.command('stats-count_by_category')
@click.option('--category', required=True)
def stats_count_by_category(category):
    """product/stats/count_by_category"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_count_by_category(category=category)


if __name__ == "__main__":
    cli()

