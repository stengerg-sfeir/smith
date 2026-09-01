import click
from database import Database
from invoice_service import InvoiceService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('invoice-add')
@click.option('--customer-id', type=int, required=True)
@click.option('--total-amount', required=True)
def invoice_add(customer_id, total_amount):
    """invoice/add"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_invoice(customer_id=customer_id, total_amount=total_amount)

@cli.command('invoice-list')
@click.option('--customer-id')
@click.option('--total-amount')
@click.option('--created-at')
def invoice_list(customer_id, total_amount, created_at):
    """invoice/list"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.list_invoice(customer_id=customer_id, total_amount=total_amount, created_at=created_at)

@cli.command('invoice_line-add')
@click.option('--invoice-id', type=int, required=True)
@click.option('--product-id', type=int, required=True)
@click.option('--quantity', type=int, required=True)
@click.option('--unit-price', required=True)
def invoice_line_add(invoice_id, product_id, quantity, unit_price):
    """invoice_line/add"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_invoice_line(invoice_id=invoice_id, product_id=product_id, quantity=quantity, unit_price=unit_price)

@cli.command('invoice_line-delete')
@click.option('--id', type=int, required=True)
def invoice_line_delete(id):
    """invoice_line/delete"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.delete_invoice_line(id=id)

@cli.command('invoice_line-update')
@click.option('--id', type=int, required=True)
@click.option('--invoice-id', type=int)
@click.option('--product-id', type=int)
@click.option('--quantity', type=int)
@click.option('--unit-price')
def invoice_line_update(id, invoice_id, product_id, quantity, unit_price):
    """invoice_line/update"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.update_invoice_line(id=id, invoice_id=invoice_id, product_id=product_id, quantity=quantity, unit_price=unit_price)

@cli.command('invoice-report')
@click.option('--id', type=int, required=True)
def invoice_report(id):
    """invoice/report"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_invoice_total(id=id)

@cli.command('product-report')
@click.option('--id', type=int, required=True)
def product_report(id):
    """product/report"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_product_report(id=id)

@cli.command('customer-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_add(name, email, phone):
    """customer/add"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email, phone=phone)

@cli.command('product-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--price', required=True)
def product_add(name, description, price):
    """product/add"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_product(name=name, description=description, price=price)


if __name__ == "__main__":
    cli()

