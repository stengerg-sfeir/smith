import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('crud-create')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', type=int, required=True)
@click.option('--stock-quantity', type=int, required=True)
@click.option('--category')
def crud_create(name, description, price, stock_quantity, category):
    """product/crud/create"""
    svc = ProductService(Database(DB_PATH))
    result = svc.create_product(name=name, description=description, price=price, stock_quantity=stock_quantity, category=category)

@cli.command('crud-update')
@click.option('--product-id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--price', type=int)
@click.option('--stock-quantity', type=int)
@click.option('--category')
def crud_update(product_id, name, description, price, stock_quantity, category):
    """product/crud/update"""
    svc = ProductService(Database(DB_PATH))
    result = svc.update_product(product_id=product_id, name=name, description=description, price=price, stock_quantity=stock_quantity, category=category)

@cli.command('crud-delete')
@click.option('--product-id', type=int, required=True)
def crud_delete(product_id):
    """product/crud/delete"""
    svc = ProductService(Database(DB_PATH))
    result = svc.delete_product(product_id=product_id)

@cli.command('query-get_by_category_and_price_range')
@click.option('--category')
@click.option('--min-price', type=int)
@click.option('--max-price', type=int)
def query_get_by_category_and_price_range(category, min_price, max_price):
    """product/query/get_by_category_and_price_range"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_by_category_and_price_range(category=category, min_price=min_price, max_price=max_price)

@cli.command('bulk-bulk_update_stock')
@click.option('--product-ids', required=True)
@click.option('--new-stock-quantity', type=int, required=True)
def bulk_bulk_update_stock(product_ids, new_stock_quantity):
    """product/bulk/bulk_update_stock"""
    svc = ProductService(Database(DB_PATH))
    result = svc.bulk_update_stock(product_ids=product_ids, new_stock_quantity=new_stock_quantity)


if __name__ == "__main__":
    cli()

