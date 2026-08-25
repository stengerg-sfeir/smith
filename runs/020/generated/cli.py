import click
from database import Database
from sales_report_service import SalesReportService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('crud-create')
@click.option('--name', required=True)
@click.option('--price', required=True)
def crud_create(name, price):
    """product/crud/create"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.add_product(name=name, price=price)

@cli.command('crud-read')
@click.option('--product-id', type=int, required=True)
def crud_read(product_id):
    """product/crud/read"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_sales_report_by_product(product_id=product_id)

@cli.command('crud-update')
def crud_update():
    """product/crud/update"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_sales_count_per_product()

@cli.command('sale-crud-create')
@click.option('--product-id', type=int, required=True)
@click.option('--quantity', type=int, required=True)
@click.option('--date', required=True)
def sale_crud_create(product_id, quantity, date):
    """sale/crud/create"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.add_sale(product_id=product_id, quantity=quantity, sale_date=date)

@cli.command('sale-crud-update')
@click.option('--threshold', type=int)
def sale_crud_update(threshold):
    """sale/crud/update"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_sales_with_low_quantity_threshold(threshold=threshold)

@cli.command('report-total')
def report_total():
    """report/total"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_total_sales_amount()

@cli.command('report-per_product')
def report_per_product():
    """report/per_product"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_sales_count_per_product()

@cli.command('report-by_product')
@click.option('--product-id', type=int, required=True)
def report_by_product(product_id):
    """report/by_product"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_sales_report_by_product(product_id=product_id)

@cli.command('report-period')
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def report_period(start_date, end_date):
    """report/period"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_sales_with_product_names(start_date=start_date, end_date=end_date)

@cli.command('report-low_quantity')
@click.option('--threshold', type=int, required=True)
def report_low_quantity(threshold):
    """report/low_quantity"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.get_sales_with_low_quantity_threshold(threshold=threshold)

@cli.command('report-export')
@click.option('--file-path', required=True)
def report_export(file_path):
    """report/export"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.export_sales_report_to_csv(file_path=file_path)

@cli.command('report-duplicates')
def report_duplicates():
    """report/duplicates"""
    svc = SalesReportService(Database(DB_PATH))
    result = svc.find_duplicate_sales_by_product()


if __name__ == "__main__":
    cli()

