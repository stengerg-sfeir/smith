import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--sku', required=True)
@click.option('--name', required=True)
@click.option('--category', required=True)
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
def product_add(sku, name, category, price, stock_quantity):
    """product/add"""
    svc = ProductService(Database(DB_PATH))
    result = svc.add_product(sku=sku, name=name, category=category, price=price, stock_quantity=stock_quantity)

@cli.command('product-list')
@click.option('--sku')
@click.option('--name')
@click.option('--category')
@click.option('--min-price')
@click.option('--max-price')
@click.option('--min-stock')
@click.option('--max-stock')
def product_list(sku, name, category, min_price, max_price, min_stock, max_stock):
    """product/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.list_product(sku=sku, name=name, category=category, min_price=min_price, max_price=max_price, min_stock=min_stock, max_stock=max_stock)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--sku')
@click.option('--name')
@click.option('--category')
@click.option('--price')
@click.option('--stock-quantity', type=int)
def product_update(id, sku, name, category, price, stock_quantity):
    """product/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(id=id, sku=sku, name=name, category=category, price=price, stock_quantity=stock_quantity)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('product-search')
@click.option('--term', required=True)
def product_search(term):
    """product/search"""
    svc = ProductService(Database(DB_PATH))
    result = svc.search_product(term=term)

@cli.command('product-filter')
@click.option('--id', type=int, required=True)
def product_filter(id):
    """product/filter"""
    svc = ProductService(Database(DB_PATH))
    result = svc.filter_product(id=id)


if __name__ == "__main__":
    cli()

