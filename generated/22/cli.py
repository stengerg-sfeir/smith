import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--price', required=True)
def product_add(name, price):
    """product/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_product(name=name, price=price)

@cli.command('order-list')
@click.option('--customer-name')
@click.option('--created-at-from')
@click.option('--created-at-to')
def order_list(customer_name, created_at_from, created_at_to):
    """order/list"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_order(customer_name=customer_name, created_at_from=created_at_from, created_at_to=created_at_to)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--price')
def product_update(id, name, price):
    """product/update"""
    svc = OrderService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, price=price)

@cli.command('order-delete')
@click.option('--id', type=int, required=True)
def order_delete(id):
    """order/delete"""
    svc = OrderService(Database(DB_PATH))
    result = svc.delete_order(id=id)

@cli.command('product-report')
@click.option('--id', type=int, required=True)
def product_report(id):
    """product/report"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_product_report(id=id)


if __name__ == "__main__":
    cli()

