import click
from database import Database
from order_service import OrderService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('create-order')
@click.option('--order-data', required=True)
@click.option('--lines', required=True)
def create_order(order_data, lines):
    """order/create/order"""
    svc = OrderService(Database(DB_PATH))
    result = svc.create_order_with_lines(order_data=order_data, order_lines=lines)

@cli.command('get-by_id')
@click.option('--id', type=int, required=True)
def get_by_id(id):
    """order/get/by_id"""
    svc = OrderService(Database(DB_PATH))
    result = svc.get_order_by_id_with_lines(order_id=id)

@cli.command('list-filtered')
@click.option('--status')
@click.option('--created-after')
@click.option('--created-before')
@click.option('--product-id', type=int)
def list_filtered(status, created_after, created_before, product_id):
    """order/list/filtered"""
    svc = OrderService(Database(DB_PATH))
    result = svc.list_orders_with_filters(status=status, created_after=created_after, created_before=created_before, product_id=product_id)

@cli.command('report-product')
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def report_product(start_date, end_date):
    """order/report/product"""
    svc = OrderService(Database(DB_PATH))
    result = svc.generate_order_report_by_product(start_date=start_date, end_date=end_date)

@cli.command('validate-lines')
@click.option('--lines', required=True)
def validate_lines(lines):
    """order/validate/lines"""
    svc = OrderService(Database(DB_PATH))
    result = svc.validate_order_lines(order_lines=lines)

@cli.command('validate-line')
@click.option('--data', required=True)
def validate_line(data):
    """order/validate/line"""
    svc = OrderService(Database(DB_PATH))
    result = svc.validate_order_line_data(order_line_data=data)


if __name__ == "__main__":
    cli()

