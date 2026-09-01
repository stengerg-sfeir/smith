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

@cli.command('customer-list')
def customer_list():
    """customer/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_customer()

@cli.command('order-update')
@click.option('--id', type=int, required=True)
@click.option('--customer-id', type=int)
@click.option('--order-date')
@click.option('--status')
def order_update(id, customer_id, order_date, status):
    """order/update"""
    svc = OrderService(Database(DB_PATH))
    result = svc.update_order(id=id, customer_id=customer_id, order_date=order_date, status=status)

@cli.command('order-delete')
@click.option('--id', type=int, required=True)
def order_delete(id):
    """order/delete"""
    svc = OrderService(Database(DB_PATH))
    result = svc.delete_order(id=id)

@cli.command('customer-delete')
@click.option('--id', type=int, required=True)
def customer_delete(id):
    """customer/delete"""
    svc = OrderService(Database(DB_PATH))
    result = svc.delete_customer(id=id)


if __name__ == "__main__":
    cli()

