import click
from database import Database
from invoice_service import InvoiceService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('invoice-get')
@click.option('--invoice-id', type=int, required=True)
def invoice_get(invoice_id):
    """invoice/get"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_invoice_with_lines(invoice_id=invoice_id)

@cli.command('invoice-customer')
@click.option('--customer-id', type=int, required=True)
@click.option('--created-after')
@click.option('--created-before')
def invoice_customer(customer_id, created_after, created_before):
    """invoice/customer"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_invoices_by_customer(customer_id=customer_id, created_after=created_after, created_before=created_before)

@cli.command('invoice-total_range')
@click.option('--min-total', type=int, required=True)
@click.option('--max-total', type=int, required=True)
def invoice_total_range(min_total, max_total):
    """invoice/total_range"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_invoices_with_total_range(min_total=min_total, max_total=max_total)

@cli.command('invoice-summary')
@click.option('--customer-id', type=int, required=True)
def invoice_summary(customer_id):
    """invoice/summary"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_customer_invoice_summary(customer_id=customer_id)

@cli.command('invoice-lines')
@click.option('--product-id', type=int)
@click.option('--start-date')
@click.option('--end-date')
def invoice_lines(product_id, start_date, end_date):
    """invoice/lines"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_invoice_lines_by_product(product_id=product_id, start_date=start_date, end_date=end_date)

@cli.command('invoice-low_total_vs_price')
@click.option('--product-id', type=int, required=True)
@click.option('--min-invoice-total', type=int, required=True)
def invoice_low_total_vs_price(product_id, min_invoice_total):
    """invoice/low_total_vs_price"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.find_invoices_with_low_total_vs_product_price(product_id=product_id, min_invoice_total=min_invoice_total)

@cli.command('invoice-export')
@click.option('--file-path', required=True)
@click.option('--product-id', type=int)
@click.option('--start-date')
@click.option('--end-date')
def invoice_export(file_path, product_id, start_date, end_date):
    """invoice/export"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.export_invoice_lines_to_csv(file_path=file_path, product_id=product_id, start_date=start_date, end_date=end_date)

@cli.command('product-top_revenue')
@click.option('--period')
@click.option('--limit', type=int)
def product_top_revenue(period, limit):
    """product/top_revenue"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_top_products_by_revenue(period=period, limit=limit)

@cli.command('product-revenue')
@click.option('--product-id', type=int, required=True)
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def product_revenue(product_id, start_date, end_date):
    """product/revenue"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_total_revenue_by_product(product_id=product_id, start_date=start_date, end_date=end_date)

@cli.command('product-total_invoices')
@click.option('--customer-id', type=int, required=True)
def product_total_invoices(customer_id):
    """product/total_invoices"""
    svc = InvoiceService(Database(DB_PATH))
    result = svc.get_total_invoices_by_customer(customer_id=customer_id)


if __name__ == "__main__":
    cli()

