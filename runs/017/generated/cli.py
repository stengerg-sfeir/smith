import click
from database import Database
from product_service import ProductService

DB_PATH = "inventory.db"

@click.group()
def cli():
    """Application root."""

@cli.command('products-search')
@click.option('--name')
@click.option('--category')
@click.option('--max-price', type=int)
@click.option('--min-quantity', type=int)
def products_search(name, category, max_price, min_quantity):
    """search/products/search"""
    svc = ProductService(Database(DB_PATH))
    result = svc.search_products(name=name, category=category, max_price=max_price, min_quantity=min_quantity)

@cli.command('report-count')
def report_count():
    """report/count"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_count()

@cli.command('report-summary')
def report_summary():
    """report/summary"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_product_summary()

@cli.command('category_threshold-below_threshold')
@click.option('--category', required=True)
def category_threshold_below_threshold(category):
    """report/category_threshold/below_threshold"""
    svc = ProductService(Database(DB_PATH))
    result = svc.get_products_below_category_threshold(category=category)

@cli.command('export')
@click.option('--file-path', required=True)
def export(file_path):
    """export"""
    svc = ProductService(Database(DB_PATH))
    result = svc.export_products_to_csv(file_path=file_path)

@cli.command('diagnostic-duplicates')
def diagnostic_duplicates():
    """diagnostic/duplicates"""
    svc = ProductService(Database(DB_PATH))
    result = svc.find_duplicate_products()


if __name__ == "__main__":
    cli()

