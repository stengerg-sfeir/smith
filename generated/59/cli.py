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

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
@click.option('--category')
def product_add(name, description, price, stock_quantity, category):
    """product/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price, stock_quantity=stock_quantity, category=category)

@cli.command('product-list')
@click.option('--name')
@click.option('--category')
@click.option('--price-min')
@click.option('--price-max')
@click.option('--stock-min')
@click.option('--stock-max')
def product_list(name, category, price_min, price_max, stock_min, stock_max):
    """product/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_product(name=name, category=category, price_min=price_min, price_max=price_max, stock_min=stock_min, stock_max=stock_max)

@cli.command('order-add')
@click.option('--customer-id', type=int, required=True)
@click.option('--order-date', required=True)
@click.option('--status', required=True)
@click.option('--total-amount', required=True)
@click.option('--discount-id', type=int)
@click.option('--tax-rate', required=True)
def order_add(customer_id, order_date, status, total_amount, discount_id, tax_rate):
    """order/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_order(customer_id=customer_id, order_date=order_date, status=status, total_amount=total_amount, discount_id=discount_id, tax_rate=tax_rate)

@cli.command('discount-apply')
@click.option('--id', type=int, required=True)
def discount_apply(id):
    """discount/apply"""
    svc = OrderService(Database(DB_PATH))
    result = svc.apply_discount(id=id)

@cli.command('order-apply')
@click.option('--id', type=int, required=True)
def order_apply(id):
    """order/apply"""
    svc = OrderService(Database(DB_PATH))
    result = svc.apply_order(id=id)

@cli.command('order-cancel')
@click.option('--id', type=int, required=True)
def order_cancel(id):
    """order/cancel"""
    svc = OrderService(Database(DB_PATH))
    result = svc.cancel_order(id=id)

@cli.command('order-restore')
@click.option('--id', type=int, required=True)
def order_restore(id):
    """order/restore"""
    svc = OrderService(Database(DB_PATH))
    result = svc.restore_order(id=id)

@cli.command('order-list')
@click.option('--customer-id')
@click.option('--order-date')
@click.option('--status')
@click.option('--total-amount')
def order_list(customer_id, order_date, status, total_amount):
    """order/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_order(customer_id=customer_id, order_date=order_date, status=status, total_amount=total_amount)

@cli.command('customer-report')
@click.option('--id', type=int, required=True)
def customer_report(id):
    """customer/report"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_customer_report(id=id)

@cli.command('order-report')
@click.option('--id', type=int, required=True)
def order_report(id):
    """order/report"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_order_report(id=id)

@cli.command('discount-add')
@click.option('--name', required=True)
@click.option('--type', required=True)
@click.option('--value', required=True)
@click.option('--min-order-amount')
@click.option('--max-discount-amount')
def discount_add(name, type, value, min_order_amount, max_discount_amount):
    """discount/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_discount(name=name, type=type, value=value, min_order_amount=min_order_amount, max_discount_amount=max_discount_amount)


if __name__ == "__main__":
    cli()

