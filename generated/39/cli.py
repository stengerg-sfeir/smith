import click
from database import Database
from user_service import UserService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
@click.option('--stock-quantity', type=int, required=True)
def product_add(name, description, price, stock_quantity):
    """product/add"""
    svc = UserService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price, stock_quantity=stock_quantity)

@cli.command('product-list')
@click.option('--name')
@click.option('--price')
@click.option('--price-end')
@click.option('--created-at')
@click.option('--created-at-end')
def product_list(name, price, price_end, created_at, created_at_end):
    """product/list"""
    svc = UserService(Database(DB_PATH))
    result = svc.list_product(name=name, price=price, price_end=price_end, created_at=created_at, created_at_end=created_at_end)

@cli.command('product-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--price')
@click.option('--stock-quantity', type=int)
def product_update(id, name, description, price, stock_quantity):
    """product/update"""
    svc = UserService(Database(DB_PATH))
    result = svc.update_product(id=id, name=name, description=description, price=price, stock_quantity=stock_quantity)

@cli.command('product-delete')
@click.option('--id', type=int, required=True)
def product_delete(id):
    """product/delete"""
    svc = UserService(Database(DB_PATH))
    result = svc.delete_product(id=id)

@cli.command('user-add')
@click.option('--email', required=True)
@click.option('--password-hash', required=True)
@click.option('--role', required=True)
def user_add(email, password_hash, role):
    """user/add"""
    svc = UserService(Database(DB_PATH))
    result = svc.add_user(email=email, password_hash=password_hash, role=role)

@cli.command('user-list')
@click.option('--email')
@click.option('--role')
@click.option('--created-at')
@click.option('--created-at-end')
def user_list(email, role, created_at, created_at_end):
    """user/list"""
    svc = UserService(Database(DB_PATH))
    result = svc.list_user(email=email, role=role, created_at=created_at, created_at_end=created_at_end)

@cli.command('user-update')
@click.option('--id', type=int, required=True)
@click.option('--email')
@click.option('--password-hash')
@click.option('--role')
def user_update(id, email, password_hash, role):
    """user/update"""
    svc = UserService(Database(DB_PATH))
    result = svc.update_user(id=id, email=email, password_hash=password_hash, role=role)

@cli.command('user-delete')
@click.option('--id', type=int, required=True)
def user_delete(id):
    """user/delete"""
    svc = UserService(Database(DB_PATH))
    result = svc.delete_user(id=id)

@cli.command('order-list')
@click.option('--user-id')
@click.option('--status')
@click.option('--created-at')
@click.option('--created-at-end')
def order_list(user_id, status, created_at, created_at_end):
    """order/list"""
    svc = UserService(Database(DB_PATH))
    result = svc.list_order(user_id=user_id, status=status, created_at=created_at, created_at_end=created_at_end)


if __name__ == "__main__":
    cli()

