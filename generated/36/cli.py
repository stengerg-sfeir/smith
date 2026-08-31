import click
from database import Database
from product_service import ProductService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('category-summary')
def category_summary():
    """category/summary"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_category_product_summary()

@cli.command('product-count')
def product_count():
    """product/count"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_count_by_category()

@cli.command('product-by_category')
@click.option('--category-name', required=True)
def product_by_category(category_name):
    """product/by_category"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_by_category_name(category_name=category_name)

@cli.command('product-price_range')
@click.option('--min-price', type=int, required=True)
@click.option('--max-price', type=int, required=True)
def product_price_range(min_price, max_price):
    """product/price_range"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_in_price_range(min_price=min_price, max_price=max_price)

@cli.command('product-details')
def product_details():
    """product/details"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_with_category_details()

@cli.command('product-search')
@click.option('--query', required=True)
def product_search(query):
    """product/search"""
    svc = ProductService(Database(DB_PATH))
    result = svc.search_products_by_name(query=query)


if __name__ == "__main__":
    cli()

