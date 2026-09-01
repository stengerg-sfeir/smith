import click
from database import Database
from invoice_service import InvoiceService

DB_PATH = "invoicing.db"

@click.group()
def cli():
    """Application root."""

@cli.command('client-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def client_add(name, email, phone):
    """client/add"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_client(name=name, email=email, phone=phone)

@cli.command('invoice-add')
@click.option('--client-id', type=int, required=True)
@click.option('--invoice-number', required=True)
@click.option('--due-date', required=True)
@click.option('--amount', required=True)
@click.option('--status', required=True)
def invoice_add(client_id, invoice_number, due_date, amount, status):
    """invoice/add"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.add_invoice(client_id=client_id, invoice_number=invoice_number, due_date=due_date, amount=amount, status=status)

@cli.command('invoice-record')
@click.option('--id', type=int, required=True)
def invoice_record(id):
    """invoice/record"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.record_invoice(id=id)

@cli.command('invoice-list')
@click.option('--invoice-number')
@click.option('--due-date')
@click.option('--amount')
@click.option('--status')
def invoice_list(invoice_number, due_date, amount, status):
    """invoice/list"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.list_invoice(invoice_number=invoice_number, due_date=due_date, amount=amount, status=status)


if __name__ == "__main__":
    cli()

