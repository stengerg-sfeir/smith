"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Any, Dict, List, Optional

from database import Database
from invoice_line_repository import InvoiceLineRepository
from invoice_repository import InvoiceRepository
from models import Invoice, InvoiceLine
from product_repository import ProductRepository


class InvoiceService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.invoice_repo = InvoiceRepository(db)
        self.invoice_line_repo = InvoiceLineRepository(db)
        self.product_repo = ProductRepository(db)

    def get_invoice_with_lines(self, invoice_id: int) -> Optional[Invoice]:
        invoice = self.invoice_repo.get_by_id(invoice_id)
        if not invoice:
            return None
        invoice_lines = self.invoice_line_repo.get_invoice_lines_by_invoice_id(invoice_id)
        invoice.lines = invoice_lines
        return invoice

    def get_invoices_by_customer(self, customer_id: int, created_after: Optional[datetime] = None, created_before: Optional[datetime] = None) -> List[Invoice]:
        return self.invoice_repo.get_invoices_by_customer(customer_id=customer_id, created_after=created_after, created_before=created_before)

    def get_invoices_with_total_range(self, min_total: float, max_total: float) -> List[Invoice]:
        return self.invoice_repo.get_invoices_with_total_range(min_total=min_total, max_total=max_total)

    def get_total_invoices_by_customer(self, customer_id: int) -> int:
        return self.invoice_repo.get_total_invoices_by_customer(customer_id=customer_id)

    def get_total_revenue_by_product(self, product_id: int, start_date: datetime, end_date: datetime) -> float:
        results = {}
        for row in self.invoice_line_repo.list(product_id=product_id):
            key = row.product_id
            results[key] = results.get(key, 0) + row.unit_price
        return sum(results.values()) if results else 0

    def get_top_products_by_revenue(self, period: str, limit: int) -> List[tuple[str, float]]:
        results = {}
        for row in self.invoice_line_repo.list():
            key = row.product_id
            results[key] = results.get(key, 0) + row.unit_price
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        return [(product_id, total) for product_id, total in sorted_results[:limit]]

    def get_invoice_lines_by_product(self, product_id: int, start_date: datetime, end_date: datetime) -> List[InvoiceLine]:
        return self.invoice_line_repo.get_invoice_lines_by_product_id(product_id=product_id, start_date=start_date, end_date=end_date)

    def get_customer_invoice_summary(self, customer_id: int) -> dict:
        return self.invoice_repo.get_customer_invoice_summary(customer_id=customer_id)

    def find_invoices_with_low_total_vs_product_price(self) -> List[Dict[str, Any]]:
        """Find invoices where the total is less than the product price."""
        results = []
        for invoice in self.invoice_repo.list():
            invoice_total = invoice.total
            # Get the product price for the invoice's product
            product_price = 0
            for line in self.invoice_line_repo.get_invoice_lines_by_invoice_id(invoice.id):
                product = self.product_repo.get_by_id(line.product_id)
                if product:
                    product_price = product.price
                    break
            if invoice_total < product_price:
                results.append({
                    'invoice_id': invoice.id,
                    'total': invoice_total,
                    'product_price': product_price,
                    'difference': product_price - invoice_total
                })
        return results

    def export_invoice_lines_to_csv(self, invoice_id: int, output_path: str) -> None:
        """Export invoice lines to a CSV file."""
        invoice_lines = self.invoice_line_repo.get_invoice_lines_by_invoice_id(invoice_id)
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['invoice_id', 'product_id', 'unit_price', 'quantity']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for line in invoice_lines:
                writer.writerow({
                    'invoice_id': line.invoice_id,
                    'product_id': line.product_id,
                    'unit_price': line.unit_price,
                    'quantity': line.quantity
                })
