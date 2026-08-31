import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('order-create')
@click.option('--customer-id', type=int, required=True)
@click.option('--total-amount', type=int, required=True)
def order_create(customer_id, total_amount):
    """order/create"""
    svc = OrderService(Database(DB_PATH))
    result = svc.create_order(customer_id=customer_id, total_amount=total_amount)

@cli.command('count-pending')
def count_pending():
    """order/status/count/pending"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_pending_orders_count()

@cli.command('count-confirmed')
def count_confirmed():
    """order/status/count/confirmed"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_confirmed_orders_count()

@cli.command('count-shipped')
def count_shipped():
    """order/status/count/shipped"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_shipped_orders_count()

@cli.command('count-cancelled')
def count_cancelled():
    """order/status/count/cancelled"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_cancelled_orders_count()

@cli.command('status-latest')
def status_latest():
    """order/status/latest"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_orders_with_latest_status_change()

@cli.command('status-total')
def status_total():
    """order/status/total"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_total_orders_by_status()

@cli.command('status-range')
@click.option('--status', required=True)
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def status_range(status, start_date, end_date):
    """order/status/range"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_orders_by_status_and_date_range(status=status, start_date=start_date, end_date=end_date)

@cli.command('status-amount')
@click.option('--min-amount', type=int, required=True)
@click.option('--max-amount', type=int, required=True)
def status_amount(min_amount, max_amount):
    """order/status/amount"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_orders_with_total_amount_range(min_amount=min_amount, max_amount=max_amount)

@cli.command('get-by_customer_and_status')
@click.option('--customer-id', type=int, required=True)
@click.option('--status', required=True)
def get_by_customer_and_status(customer_id, status):
    """order/status/get/by_customer_and_status"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_order_by_customer_and_status(customer_id=customer_id, status=status)


if __name__ == "__main__":
    cli()

