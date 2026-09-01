import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-list')
def customer_list():
    """customer/list"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.list_customer()

@cli.command('order-add')
@click.option('--customer-id', type=int, required=True)
@click.option('--total-amount', required=True)
@click.option('--status')
def order_add(customer_id, total_amount, status):
    """order/add"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.add_order(customer_id=customer_id, total_amount=total_amount, status=status)

@cli.command('customer-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_add(name, email, phone):
    """customer/add"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email, phone=phone)

@cli.command('customer-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--email')
@click.option('--phone')
def customer_update(id, name, email, phone):
    """customer/update"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.update_customer(id=id, name=name, email=email, phone=phone)

@cli.command('order-update')
@click.option('--id', type=int, required=True)
@click.option('--customer-id', type=int, required=True)
@click.option('--total-amount', required=True)
@click.option('--status')
def order_update(id, customer_id, total_amount, status):
    """order/update"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.update_order(id=id, customer_id=customer_id, total_amount=total_amount, status=status)

@cli.command('customer-delete')
@click.option('--id', type=int, required=True)
def customer_delete(id):
    """customer/delete"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.delete_customer(id=id)

@cli.command('order-delete')
@click.option('--id', type=int, required=True)
def order_delete(id):
    """order/delete"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.delete_order(id=id)


if __name__ == "__main__":
    cli()

