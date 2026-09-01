import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_add(name, email, phone):
    """customer/add"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email, phone=phone)

@cli.command('customer-list')
@click.option('--name')
@click.option('--email-domain')
def customer_list(name, email_domain):
    """customer/list"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.list_customer(name=name, email_domain=email_domain)

@cli.command('customer-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--email')
@click.option('--phone')
def customer_update(id, name, email, phone):
    """customer/update"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.update_customer(id=id, name=name, email=email, phone=phone)

@cli.command('customer-delete')
@click.option('--id', type=int, required=True)
def customer_delete(id):
    """customer/delete"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.delete_customer(id=id)

@cli.command('customer-search')
@click.option('--term', required=True)
def customer_search(term):
    """customer/search"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.search_customer(term=term)

@cli.command('customer-filter')
@click.option('--id', type=int, required=True)
def customer_filter(id):
    """customer/filter"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.filter_customer(id=id)


if __name__ == "__main__":
    cli()

