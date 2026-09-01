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
@click.option('--phone')
def customer_add(name, email, phone):
    """customer/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email, phone=phone)

@cli.command('customer-list')
@click.option('--name')
@click.option('--email')
@click.option('--phone')
def customer_list(name, email, phone):
    """customer/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_customer(name=name, email=email, phone=phone)

@cli.command('customer-search')
@click.option('--term', required=True)
def customer_search(term):
    """customer/search"""
    svc = OrderService(Database(DB_PATH))
    result = svc.search_customer(term=term)

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
@click.option('--category-id', type=int)
def product_add(name, description, price, stock_quantity, category_id):
    """product/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price, stock_quantity=stock_quantity, category_id=category_id)

@cli.command('product-list')
@click.option('--name')
@click.option('--category-id', type=int)
@click.option('--price')
def product_list(name, category_id, price):
    """product/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_product(name=name, category_id=category_id, price=price)

@cli.command('product-search')
@click.option('--term', required=True)
def product_search(term):
    """product/search"""
    svc = OrderService(Database(DB_PATH))
    result = svc.search_category(term=term)

@cli.command('category-add')
@click.option('--name', required=True)
def category_add(name):
    """category/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_category(name=name)

@cli.command('order-add')
@click.option('--customer-id', type=int, required=True)
@click.option('--status', required=True)
def order_add(customer_id, status):
    """order/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_order(customer_id=customer_id, status=status)

@cli.command('order-list')
@click.option('--customer-id', type=int)
@click.option('--status')
def order_list(customer_id, status):
    """order/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_order(customer_id=customer_id, status=status)

@cli.command('order-confirm')
@click.option('--id', type=int, required=True)
def order_confirm(id):
    """order/confirm"""
    svc = OrderService(Database(DB_PATH))
    result = svc.confirm_invoice(id=id)

@cli.command('order-cancel')
@click.option('--id', type=int, required=True)
def order_cancel(id):
    """order/cancel"""
    svc = OrderService(Database(DB_PATH))
    result = svc.cancel_order(id=id)

@cli.command('invoice-list')
@click.option('--order-id', type=int)
@click.option('--total-amount')
def invoice_list(order_id, total_amount):
    """invoice/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_invoice(order_id=order_id, total_amount=total_amount)


if __name__ == "__main__":
    cli()

