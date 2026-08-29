"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Dict, List, Optional

from database import Database
from exceptions import (
    InvoiceNotFoundError,
)
from invoice_repository import InvoiceRepository
from models import Invoice, InvoiceLine


class InvoiceService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.invoice_repo = InvoiceRepository(db)

    def get_invoice_with_lines(self, invoice_id: int) -> Optional[Invoice]:
        invoice = self.invoice_repo.get_by_id(invoice_id)
        if not invoice:
            raise InvoiceNotFoundError(f'Invoice with id {invoice_id} not found')
        invoice_lines = self.invoice_repo.get_invoice_lines_by_invoice_id(invoice_id)
        invoice.lines = invoice_lines
        return invoice

    def get_invoices_by_customer(self, customer_id: int, created_after: Optional[datetime.datetime] = None, created_before: Optional[datetime.datetime] = None) -> List[Invoice]:
        return self.invoice_repo.get_invoices_by_customer(customer_id, created_after, created_before)

    def get_invoices_with_total_range(self, min_total: float, max_total: float) -> List[Invoice]:
        return self.invoice_repo.get_invoices_with_total_range(min_total, max_total)

    def get_total_invoices_by_customer(self, customer_id: int) -> int:
        return self.invoice_repo.get_total_invoices_by_customer(customer_id)

    def get_total_revenue_by_product(self, product_id: int, start_date: datetime.datetime, end_date: datetime.datetime) -> float:
        return self.invoice_repo.get_total_revenue_by_product(product_id, start_date, end_date)

    def get_top_products_by_revenue(self, period: str, limit: int) -> List[tuple[str, float]]:
        return self.invoice_repo.get_top_products_by_revenue(period, limit)

    def get_invoice_lines_by_product(self, product_id: int, start_date: datetime.datetime, end_date: datetime.datetime) -> List[InvoiceLine]:
        invoice_lines = self.invoice_repo.get_invoice_lines_by_product_id(product_id, start_date, end_date)
        return invoice_lines

    def get_customer_invoice_summary(self, customer_id: int) -> Dict[str, float]:
        rows = self.invoice_repo.list(customer_id=customer_id)
        total = sum(e.total_amount for e in rows)
        return {'total_revenue': total}

    def export_invoice_lines_to_csv(self, file_path: str, product_id: Optional[int] = None, start_date: Optional[datetime.datetime] = None, end_date: Optional[datetime.datetime] = None) -> None:
        rows = self.invoice_repo.get_invoice_lines_by_product_id(product_id, start_date, end_date)
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["product_id", "invoice_id", "quantity", "unit_price", "total_price"])
            for row in rows:
                writer.writerow([
                    row.product_id,
                    row.invoice_id,
                    row.quantity,
                    row.unit_price,
                    row.total_price
                ])

    def find_invoices_with_low_total_vs_product_price(self) -> List[Invoice]:
        # This method identifies invoices where the total invoice amount is less than the product price
        # We assume the product price is stored in the Product table and can be joined
        # This is a simplified implementation based on available data
        low_total_invoices = []
        invoices = self.invoice_repo.list()
        for invoice in invoices:
            # For each invoice, we need to find the product(s) it references
            # This requires joining with InvoiceLine and Product tables
            # We assume the product price is available in the Product table
            invoice_lines = self.invoice_repo.get_invoice_lines_by_invoice_id(invoice.id)
            for line in invoice_lines:
                product = self.db.get_product_by_id(line.product_id)
                if product and invoice.total_amount < product.price:
                    low_total_invoices.append(invoice)
                    break
        return low_total_invoices
