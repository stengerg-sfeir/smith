import click
from database import Database
from invoice_service import InvoiceService

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
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email, phone=phone)

@cli.command('invoice-list')
@click.option('--customer-id')
@click.option('--total-amount')
@click.option('--created-at')
def invoice_list(customer_id, total_amount, created_at):
    """invoice/list"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.list_invoice(customer_id=customer_id, total_amount=total_amount, created_at=created_at)

@cli.command('customer-list')
@click.option('--name')
@click.option('--email')
def customer_list(name, email):
    """customer/list"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.list_customer(name=name, email=email)

@cli.command('invoice-add')
@click.option('--customer-id', type=int, required=True)
@click.option('--total-amount', required=True)
def invoice_add(customer_id, total_amount):
    """invoice/add"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_invoice(customer_id=customer_id, total_amount=total_amount)

@cli.command('invoice-delete')
@click.option('--id', type=int, required=True)
def invoice_delete(id):
    """invoice/delete"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.delete_invoice(id=id)

@cli.command('invoice-update')
@click.option('--id', type=int, required=True)
@click.option('--customer-id', type=int)
@click.option('--total-amount')
def invoice_update(id, customer_id, total_amount):
    """invoice/update"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.update_invoice(id=id, customer_id=customer_id, total_amount=total_amount)

@cli.command('invoice-report')
@click.option('--id', type=int, required=True)
def invoice_report(id):
    """invoice/report"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_invoice_report(id=id)

@cli.command('product-list')
@click.option('--name')
@click.option('--price')
def product_list(name, price):
    """product/list"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.list_product(name=name, price=price)


if __name__ == "__main__":
    cli()

