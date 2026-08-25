import click
from database import Database
from product_service import ProductService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-create')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', type=int, required=True)
@click.option('--quantity', type=int, required=True)
def product_create(name, description, price, quantity):
    """product/create"""
    svc = ProductService(Database(DB_PATH))
    result = svc.create_product(name=name, description=description, price=price, quantity=quantity)

@cli.command('get-by_name')
@click.option('--name', required=True)
def get_by_name(name):
    """product/get/by_name"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_by_name(name=name)

@cli.command('get-count')
def get_count():
    """product/get/count"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_count()

@cli.command('get-highest_price')
def get_highest_price():
    """product/get/highest_price"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_with_highest_price()

@cli.command('get-lowest_price')
def get_lowest_price():
    """product/get/lowest_price"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_with_lowest_price()

@cli.command('get-by_category')
@click.option('--category', required=True)
def get_by_category(category):
    """product/get/by_category"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_by_category(category=category)

@cli.command('get-by_price_range')
@click.option('--min-price', type=int, required=True)
@click.option('--max-price', type=int, required=True)
def get_by_price_range(min_price, max_price):
    """product/get/by_price_range"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_by_price_range(min_price=min_price, max_price=max_price)

@cli.command('get-low_stock')
def get_low_stock():
    """product/get/low_stock"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_with_low_stock()

@cli.command('get-total_value')
def get_total_value():
    """product/get/total_value"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_total_value_of_inventory()

@cli.command('search-query')
@click.option('--query', required=True)
def search_query(query):
    """product/search/query"""
    svc = ProductService(Database(DB_PATH))
    result = svc.search_products(query=query)


if __name__ == "__main__":
    cli()

