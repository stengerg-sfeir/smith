import click
from database import Database
from user_service import UserService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('user-create')
@click.option('--email', required=True)
@click.option('--password', required=True)
@click.option('--role')
def user_create(email, password, role):
    """user/create"""
    svc = UserService(Database(DB_PATH))
    result = svc.create_user(email=email, password_hash=password, role=role)

@cli.command('user-orders')
@click.option('--user-id', type=int, required=True)
@click.option('--status')
def user_orders(user_id, status):
    """user/orders"""
    svc = UserService(Database(DB_PATH))
    result = svc.get_user_orders(user_id=user_id, status=status)

@cli.command('user-details')
@click.option('--user-id', type=int, required=True)
def user_details(user_id):
    """user/details"""
    svc = UserService(Database(DB_PATH))
    result = svc.get_user_order_details(user_id=user_id)

@cli.command('user-most_orders')
def user_most_orders():
    """user/most_orders"""
    svc = UserService(Database(DB_PATH))
    result = svc.get_user_with_most_orders()

@cli.command('user-export_orders')
@click.option('--user-id', type=int, required=True)
@click.option('--file-path', required=True)
def user_export_orders(user_id, file_path):
    """user/export_orders"""
    svc = UserService(Database(DB_PATH))
    result = svc.export_user_orders_to_csv(user_id=user_id, file_path=file_path)

@cli.command('order-list')
@click.option('--user-id', type=int)
@click.option('--status')
def order_list(user_id, status):
    """order/list"""
    svc = UserService(Database(DB_PATH))
    result = svc.get_user_orders(user_id=user_id, status=status)

@cli.command('order-details')
@click.option('--user-id', type=int, required=True)
def order_details(user_id):
    """order/details"""
    svc = UserService(Database(DB_PATH))
    result = svc.get_user_order_details(user_id=user_id)


if __name__ == "__main__":
    cli()

