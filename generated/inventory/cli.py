import click
from database import Database
from inventory_service import InventoryService

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
    svc = InventoryService(Database(DB_PATH))
    result = svc.add_product(sku=sku, name=name, category_id=category, price_cents=price, stock_qty=stock)

@cli.command('product-list')
@click.option('--category', type=int)
@click.option('--low-only', is_flag=True, default=False)
def product_list(category, low_only):
    """product/list"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.list_products(category_id=category, low_only=low_only)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--price', type=int)
@click.option('--category', type=int)
def product_update(id, name, price, category):
    """product/update"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.update_product(id=id, data={'name': name, 'price_cents': price, 'category_id': category})

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('product-restock')
@click.option('--id', type=int, required=True)
@click.option('--qty', type=int, required=True)
def product_restock(id, qty):
    """product/restock"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.restock(id=id, qty=qty)

@cli.command('report-low_stock')
def report_low_stock():
    """product/report/low_stock"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.low_stock_report()

@cli.command('report-value')
def report_value():
    """product/report/value"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.stock_value_by_category()

@cli.command('category-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--threshold', type=int)
def category_add(name, description, threshold):
    """category/add"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.add_category(name=name, description=description, reorder_threshold=threshold)

@cli.command('category-list')
def category_list():
    """category/list"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.list_category()

@cli.command('category-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--threshold', type=int)
def category_update(id, name, description, threshold):
    """category/update"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.update_category(id=id, name=name, description=description, reorder_threshold=threshold)

@cli.command('category-delete')
@click.option('--id', type=int, required=True)
def category_delete(id):
    """category/delete"""
    svc = InventoryService(Database(DB_PATH))
    result = svc.delete_category(id=id)


if __name__ == "__main__":
    cli()

