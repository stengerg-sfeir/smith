"""Service layer."""
from __future__ import annotations

import csv
import datetime

from database import Database
from exceptions import DatabaseError, SalesReportError
from models import Product, Sale
from product_repository import ProductRepository
from sale_repository import SaleRepository


class SalesReportService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)
        self.sale_repo = SaleRepository(db)

    def get_total_sales_amount(self) -> float:
        """Retrieve the total sales amount from all sales records."""
        try:
            return self.sale_repo.get_total_sales_amount()
        except Exception as e:
            raise DatabaseError(f'Error retrieving total sales amount: {str(e)}')

    def get_sales_count_per_product(self) -> dict:
        results = {}
        for row in self.sale_repo.list():
            key = row.product_id
            results[key] = results.get(key, 0) + row.quantity
        return results

    def get_sales_report_by_product(self, product_id: int) -> dict:
        rows = self.sale_repo.list(product_id=product_id)
        total = sum(e.quantity for e in rows)
        return {'total_quantity': total}

    def export_sales_report_to_csv(self, file_path: str) -> None:
        rows = self.sale_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'product_id', 'quantity', 'sale_date',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.product_id, row.quantity, row.sale_date,
                ])

    def find_duplicate_sales_by_product(self) -> list:
        """Find duplicate sales entries (same product_id and quantity) across sales records."""
        try:
            sales = self.sale_repo.get_all()
            sales_list = []
            for sale in sales:
                sales_list.append({'product_id': sale.product_id, 'quantity': sale.quantity})
            from collections import defaultdict
            duplicates = defaultdict(list)
            for sale in sales_list:
                key = (sale['product_id'], sale['quantity'])
                duplicates[key].append(sale)
            result = []
            for key, entries in duplicates.items():
                if len(entries) > 1:
                    result.extend(entries)
            return result
        except Exception as e:
            raise SalesReportError(f'Error finding duplicate sales: {str(e)}')

    def get_sales_with_product_names(self, start_date: datetime, end_date: datetime) -> list:
        """Retrieve sales with product names, filtered by date range."""
        try:
            sales_with_names = self.sale_repo.get_sales_with_product_names(start_date, end_date)
            result = []
            for sale in sales_with_names:
                product_id = sale.product_id
                product = self.product_repo.get_by_id(product_id)
                if product:
                    result.append({'sale_id': sale.id, 'product_name': product.name, 'quantity': sale.quantity, 'sale_date': sale.sale_date})
            return result
        except Exception as e:
            raise SalesReportError(f'Error retrieving sales with product names: {str(e)}')

    def get_sales_with_low_quantity_threshold(self, threshold: float) -> list:
        """Retrieve sales with quantity below the given threshold."""
        try:
            sales = self.sale_repo.get_all()
            result = []
            for sale in sales:
                if sale.quantity < threshold:
                    product = self.product_repo.get_by_id(sale.product_id)
                    if product:
                        result.append({'sale_id': sale.id, 'product_name': product.name, 'quantity': sale.quantity, 'sale_date': sale.sale_date})
            return result
        except Exception as e:
            raise SalesReportError(f'Error retrieving sales with low quantity threshold: {str(e)}')

    def add_product(self, name: str, price: str) -> int:
        product = Product(name=name, price=price)
        return self.product_repo.create(product)

    def add_sale(self, product_id: int, quantity: int, sale_date: str) -> int:
        sale = Sale(product_id=product_id, quantity=quantity, sale_date=sale_date)
        return self.sale_repo.create(sale)

