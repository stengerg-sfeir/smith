import click
from database import Database
from product_service import ProductService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('list-name')
@click.option('--sort-order', is_flag=True, default=False)
@click.option('--filter-name')
def list_name(sort_order, filter_name):
    """products/list/name"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_products_by_name(sort_order=sort_order, filter_name=filter_name)

@cli.command('list-price')
@click.option('--sort-order', is_flag=True, default=False)
@click.option('--min-price', type=int)
@click.option('--max-price', type=int)
def list_price(sort_order, min_price, max_price):
    """products/list/price"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_products_by_price(sort_order=sort_order, min_price=min_price, max_price=max_price)

@cli.command('list-quantity')
@click.option('--sort-order', is_flag=True, default=False)
@click.option('--min-quantity', type=int)
@click.option('--max-quantity', type=int)
def list_quantity(sort_order, min_quantity, max_quantity):
    """products/list/quantity"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_products_by_quantity(sort_order=sort_order, min_quantity=min_quantity, max_quantity=max_quantity)

@cli.command('list-pagination')
@click.option('--page', type=int, required=True)
@click.option('--page-size', type=int, required=True)
@click.option('--sort-field', required=True)
@click.option('--sort-order', is_flag=True, default=False)
def list_pagination(page, page_size, sort_field, sort_order):
    """products/list/pagination"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_products_with_pagination(page=page, page_size=page_size, sort_field=sort_field, sort_order=sort_order)

@cli.command('stats-count')
def stats_count():
    """products/stats/count"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_count()

@cli.command('report-category')
@click.option('--category', required=True)
def report_category(category):
    """products/report/category"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_report_by_category(category=category)


if __name__ == "__main__":
    cli()

