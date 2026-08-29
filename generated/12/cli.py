import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-create')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_create(name, email, phone):
    """customer/create"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.create_customer(name=name, email=email, phone=phone)

@cli.command('customer-list')
@click.option('--domain')
def customer_list(domain):
    """customer/list"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_by_domain(domain=domain)

@cli.command('customer-search')
@click.option('--name', required=True)
def customer_search(name):
    """customer/search"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.search_customers_by_name(name=name)

@cli.command('customer-filter')
@click.option('--domain', required=True)
def customer_filter(domain):
    """customer/filter"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.filter_customers_by_email_domain(domain=domain)

@cli.command('phone-prefix')
@click.option('--prefix', required=True)
def phone_prefix(prefix):
    """customer/phone/prefix"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_with_phone_prefix(prefix=prefix)

@cli.command('stats-count')
def stats_count():
    """customer/stats/count"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_total_customers()


if __name__ == "__main__":
    cli()

