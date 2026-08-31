import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('order-add')
@click.option('--status', required=True)
def order_add(status):
    """order/add"""
    svc = OrderService(Database(DB_PATH))
    result = svc.add_order(status=status)


if __name__ == "__main__":
    cli()

