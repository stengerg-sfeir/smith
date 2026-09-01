import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
def customer_add(name, email):
    """customer/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email)

@cli.command('customer-get')
@click.option('--id', type=int, required=True)
def customer_get(id):
    """customer/get"""
    svc = OrderService(Database(DB_PATH))
    result = svc.customers_customer(id=id)

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
def product_add(name, description, price, stock_quantity):
    """product/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price, stock_quantity=stock_quantity)

@cli.command('product-search')
@click.option('--term', required=True)
def product_search(term):
    """product/search"""
    svc = OrderService(Database(DB_PATH))
    result = svc.search_product(term=term)

@cli.command('product-filter')
@click.option('--id', type=int, required=True)
def product_filter(id):
    """product/filter"""
    svc = OrderService(Database(DB_PATH))
    result = svc.filter_product(id=id)

@cli.command('product-list')
@click.option('--name')
@click.option('--price')
@click.option('--stock-quantity')
def product_list(name, price, stock_quantity):
    """product/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_product(name=name, price=price, stock_quantity=stock_quantity)

@cli.command('order-list')
@click.option('--status')
@click.option('--total-amount')
@click.option('--created-at')
def order_list(status, total_amount, created_at):
    """order/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_order(status=status, total_amount=total_amount, created_at=created_at)

@cli.command('product-cancel')
@click.option('--id', type=int, required=True)
def product_cancel(id):
    """product/cancel"""
    svc = OrderService(Database(DB_PATH))
    result = svc.cancel_product(id=id)


if __name__ == "__main__":
    cli()

