import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('order-add')
@click.option('--customer-id', type=int)
@click.option('--status', required=True)
@click.option('--total-amount', required=True)
def order_add(customer_id, status, total_amount):
    """order/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_order(customer_id=customer_id, status=status, total_amount=total_amount)

@cli.command('order-confirm')
@click.option('--id', type=int, required=True)
def order_confirm(id):
    """order/confirm"""
    svc = OrderService(Database(DB_PATH))
    result = svc.confirm_order(id=id)

@cli.command('order-ship')
@click.option('--id', type=int, required=True)
def order_ship(id):
    """order/ship"""
    svc = OrderService(Database(DB_PATH))
    result = svc.ship_order(id=id)

@cli.command('order-cancel')
@click.option('--id', type=int, required=True)
def order_cancel(id):
    """order/cancel"""
    svc = OrderService(Database(DB_PATH))
    result = svc.cancel_order(id=id)

@cli.command('order-check')
@click.option('--id', type=int, required=True)
def order_check(id):
    """order/check"""
    svc = OrderService(Database(DB_PATH))
    result = svc.check_order(id=id)


if __name__ == "__main__":
    cli()

