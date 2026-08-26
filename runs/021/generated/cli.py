import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('orders-list')
@click.option('--customer-id', type=int, required=True)
@click.option('--status')
@click.option('--start-date')
@click.option('--end-date')
def orders_list(customer_id, status, start_date, end_date):
    """customer/orders/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_customer_orders(customer_id=customer_id, status=status, start_date=start_date, end_date=end_date)

@cli.command('customer-create')
@click.option('--customer-id', type=int, required=True)
@click.option('--order-date', required=True)
@click.option('--status', required=True)
def customer_create(customer_id, order_date, status):
    """customer/create"""
    svc = OrderService(Database(DB_PATH))
    result = svc.create_order(customer_id=customer_id, order_date=order_date, status=status)

@cli.command('customer-update_status')
@click.option('--order-id', type=int, required=True)
@click.option('--new-status', required=True)
def customer_update_status(order_id, new_status):
    """customer/update_status"""
    svc = OrderService(Database(DB_PATH))
    result = svc.update_order_status(order_id=order_id, new_status=new_status)

@cli.command('customer-count_by_status')
@click.option('--customer-id', type=int, required=True)
def customer_count_by_status(customer_id):
    """customer/count_by_status"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_customer_order_count_by_status(customer_id=customer_id)

@cli.command('customer-total_orders_and_revenue')
@click.option('--customer-id', type=int, required=True)
def customer_total_orders_and_revenue(customer_id):
    """customer/total_orders_and_revenue"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_customer_total_orders_and_revenue(customer_id=customer_id)

@cli.command('orders-by_status_and_date_range')
@click.option('--status', required=True)
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def orders_by_status_and_date_range(status, start_date, end_date):
    """orders/by_status_and_date_range"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_orders_by_status_and_date_range(status=status, start_date=start_date, end_date=end_date)

@cli.command('orders-export')
@click.option('--customer-id', type=int, required=True)
@click.option('--file-path', required=True)
def orders_export(customer_id, file_path):
    """customer/orders/export"""
    svc = OrderService(Database(DB_PATH))
    result = svc.export_orders_to_csv(customer_id=customer_id, file_path=file_path)


if __name__ == "__main__":
    cli()

