import click
from customer_service import CustomerService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('manage-create')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def manage_create(name, email, phone):
    """customer/manage/create"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.create_customer(name=name, email=email, phone=phone)

@cli.command('retrieve-by_email')
@click.option('--email', required=True)
def retrieve_by_email(email):
    """customer/retrieve/by_email"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_by_email(email=email)

@cli.command('orders-list')
@click.option('--customer-id', type=int, required=True)
@click.option('--status')
@click.option('--from-date')
@click.option('--to-date')
def orders_list(customer_id, status, from_date, to_date):
    """customer/orders/list"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_orders(customer_id=customer_id, status=status, from_date=from_date, to_date=to_date)

@cli.command('orders-with_details')
@click.option('--customer-id', type=int, required=True)
def orders_with_details(customer_id):
    """customer/orders/with_details"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_with_orders(customer_id=customer_id)

@cli.command('summary-spend')
@click.option('--customer-id', type=int, required=True)
def summary_spend(customer_id):
    """customer/summary/spend"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_total_spent(customer_id=customer_id)

@cli.command('summary-order_summary')
@click.option('--customer-id', type=int, required=True)
def summary_order_summary(customer_id):
    """customer/summary/order_summary"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customer_order_summary(customer_id=customer_id)

@cli.command('search-by_prefix')
@click.option('--prefix', required=True)
def search_by_prefix(prefix):
    """customer/search/by_prefix"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_customers_by_name_prefix(prefix=prefix)

@cli.command('update-phone')
@click.option('--customer-id', type=int, required=True)
@click.option('--phone', required=True)
def update_phone(customer_id, phone):
    """customer/update/phone"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.update_customer_phone(customer_id=customer_id, phone=phone)

@cli.command('count-active')
def count_active():
    """customer/count/active"""
    svc = CustomerService(Database(DB_PATH))
    result = svc.get_active_customers_count()


if __name__ == "__main__":
    cli()

