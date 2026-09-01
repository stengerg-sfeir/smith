import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-add')
@click.option('--first-name', required=True)
@click.option('--last-name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_add(first_name, last_name, email, phone):
    """customer/add"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.add_customer(first_name=first_name, last_name=last_name, email=email, phone=phone)

@cli.command('customer-update')
@click.option('--id', type=int, required=True)
@click.option('--first-name')
@click.option('--last-name')
@click.option('--email')
@click.option('--phone')
def customer_update(id, first_name, last_name, email, phone):
    """customer/update"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.update_customer(id=id, first_name=first_name, last_name=last_name, email=email, phone=phone)

@cli.command('customer-delete')
@click.option('--id', type=int, required=True)
def customer_delete(id):
    """customer/delete"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.delete_customer(id=id)

@cli.command('customer-list')
@click.option('--first-name')
@click.option('--last-name')
@click.option('--email')
@click.option('--created-at')
@click.option('--created-at-end')
def customer_list(first_name, last_name, email, created_at, created_at_end):
    """customer/list"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.list_customer(first_name=first_name, last_name=last_name, email=email, created_at=created_at, created_at_end=created_at_end)


if __name__ == "__main__":
    cli()

