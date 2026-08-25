import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('read-list')
@click.option('--query')
@click.option('--category')
def read_list(query, category):
    """product/read/list"""
    svc = ProductService(Database(DB_PATH))
    result = svc.search_products(query=query, category=category)

@cli.command('read-by_sku')
@click.option('--sku', required=True)
def read_by_sku(sku):
    """product/read/by_sku"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_by_sku(sku=sku)

@cli.command('read-by_category')
@click.option('--category', required=True)
def read_by_category(category):
    """product/read/by_category"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_by_category(category=category)

@cli.command('read-low_stock')
def read_low_stock():
    """product/read/low_stock"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_low_stock_products()

@cli.command('read-count_by_category')
def read_count_by_category():
    """product/read/count_by_category"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_count_by_category()

@cli.command('write-create')
@click.option('--sku', required=True)
@click.option('--name', required=True)
@click.option('--category', required=True)
@click.option('--price', type=int, required=True)
@click.option('--stock-quantity', type=int, required=True)
def write_create(sku, name, category, price, stock_quantity):
    """product/write/create"""
    svc = ProductService(Database(DB_PATH))
    result = svc.create_product(sku=sku, name=name, category=category, price=price, stock_quantity=stock_quantity)

@cli.command('write-update_stock')
@click.option('--sku', required=True)
@click.option('--new-stock', type=int, required=True)
def write_update_stock(sku, new_stock):
    """product/write/update_stock"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product_stock(sku=sku, new_stock=new_stock)

@cli.command('write-delete')
@click.option('--sku', required=True)
def write_delete(sku):
    """product/write/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(sku=sku)

@cli.command('product-export')
@click.option('--file-path', required=True)
def product_export(file_path):
    """product/export"""
    svc = ProductService(Database(DB_PATH))
    result = svc.export_products_to_csv(file_path=file_path)


if __name__ == "__main__":
    cli()

