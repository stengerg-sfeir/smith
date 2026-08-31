import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('order-create')
@click.option('--customer-name', required=True)
@click.option('--items', required=True)
def order_create(customer_name, items):
    """order/create"""
    svc = OrderService(Database(DB_PATH))
    result = svc.create_order(customer_name=customer_name, items=items)

@cli.command('order-list')
@click.option('--customer-name')
@click.option('--start-date')
@click.option('--end-date')
def order_list(customer_name, start_date, end_date):
    """order/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_orders_by_customer(customer_name=customer_name, start_date=start_date, end_date=end_date)

@cli.command('get-total')
@click.option('--order-id', type=int, required=True)
def get_total(order_id):
    """order/get/total"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_order_total_amount(order_id=order_id)

@cli.command('get-items')
@click.option('--order-id', type=int, required=True)
def get_items(order_id):
    """order/get/items"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_order_with_items(order_id=order_id)

@cli.command('get-revenue')
@click.option('--start-date')
@click.option('--end-date')
def get_revenue(start_date, end_date):
    """order/get/revenue"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_total_revenue_by_product(start_date=start_date, end_date=end_date)

@cli.command('get-popular')
def get_popular():
    """order/get/popular"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_most_popular_product()

@cli.command('get-over_limit')
@click.option('--min-quantity', type=int, required=True)
def get_over_limit(min_quantity):
    """order/get/over_limit"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_orders_with_quantity_over_limit(min_quantity=min_quantity)

@cli.command('order-export')
@click.option('--file-path', required=True)
@click.option('--customer-name')
@click.option('--start-date')
@click.option('--end-date')
def order_export(file_path, customer_name, start_date, end_date):
    """order/export"""
    svc = OrderService(Database(DB_PATH))
    result = svc.export_orders_to_csv(file_path=file_path, customer_name=customer_name, start_date=start_date, end_date=end_date)


if __name__ == "__main__":
    cli()

