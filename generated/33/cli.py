import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-create')
@click.option('--first-name', required=True)
@click.option('--last-name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_create(first_name, last_name, email, phone):
    """customer/create"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.add_customer(first_name=first_name, last_name=last_name, email=email, phone=phone)

@cli.command('customer-delete')
@click.option('--customer-id', type=int, required=True)
def customer_delete(customer_id):
    """customer/delete"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.delete_customer(customer_id=customer_id)

@cli.command('get-by_email')
@click.option('--email', required=True)
def get_by_email(email):
    """customer/get/by_email"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_by_email(email=email)

@cli.command('get-by_last_name_prefix')
@click.option('--prefix', required=True)
def get_by_last_name_prefix(prefix):
    """customer/get/by_last_name_prefix"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_by_last_name_prefix(prefix=prefix)

@cli.command('get-active')
def get_active():
    """customer/get/active"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_with_active_status()

@cli.command('get-count')
def get_count():
    """customer/get/count"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_count()

@cli.command('get-spending')
def get_spending():
    """customer/get/spending"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_with_total_spending()

@cli.command('get-by_customer')
@click.option('--customer-id', type=int, required=True)
@click.option('--start-date')
@click.option('--end-date')
def get_by_customer(customer_id, start_date, end_date):
    """audit/get/by_customer"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_audit_records_for_customer(customer_id=customer_id, start_date=start_date, end_date=end_date)

@cli.command('get-recent')
def get_recent():
    """audit/get/recent"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_recent_activity_summary()


if __name__ == "__main__":
    cli()

