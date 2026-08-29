import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('get-by_email')
@click.option('--email', required=True)
def get_by_email(email):
    """customer/get/by_email"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_by_email(email=email)

@cli.command('list-by_last_name_prefix')
@click.option('--prefix', required=True)
@click.option('--page', type=int)
@click.option('--page-size', type=int)
def list_by_last_name_prefix(prefix, page, page_size):
    """customer/list/by_last_name_prefix"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_by_last_name_prefix(last_name_prefix=prefix, page_number=page, page_size=page_size)

@cli.command('list-by_phone_pattern')
@click.option('--pattern', required=True)
@click.option('--page', type=int)
@click.option('--page-size', type=int)
def list_by_phone_pattern(pattern, page, page_size):
    """customer/list/by_phone_pattern"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_by_phone_pattern(phone_pattern=pattern, page_number=page, page_size=page_size)

@cli.command('list-active')
@click.option('--page', type=int)
@click.option('--page-size', type=int)
def list_active(page, page_size):
    """customer/list/active"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_with_active_status(page_number=page, page_size=page_size)

@cli.command('list-by_domain')
@click.option('--domain', required=True)
@click.option('--page', type=int)
@click.option('--page-size', type=int)
def list_by_domain(domain, page, page_size):
    """customer/list/by_domain"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_with_email_domain(domain=domain, page_number=page, page_size=page_size)

@cli.command('list-recent_activity')
@click.option('--days-ago', type=int, required=True)
@click.option('--page', type=int)
@click.option('--page-size', type=int)
def list_recent_activity(days_ago, page, page_size):
    """customer/list/recent_activity"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_with_recent_activity(days_ago=days_ago, page_number=page, page_size=page_size)


if __name__ == "__main__":
    cli()

