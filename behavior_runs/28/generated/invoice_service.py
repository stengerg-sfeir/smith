"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CustomerNotFoundError,
    InvoiceNotFoundError,
)
from invoice_line_repository import InvoiceLineRepository
from invoice_repository import InvoiceRepository
from models import Customer, Invoice, Product
from product_repository import ProductRepository


class InvoiceService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.invoice_repo = InvoiceRepository(db)
        self.invoice_line_repo = InvoiceLineRepository(db)
        self.product_repo = ProductRepository(db)

    def add_customer(self, name: str, email: str, phone: Optional[str] = None) -> None:
        customer = Customer(name=name, email=email, phone=phone)
        return self.customer_repo.create(customer)

    def list_invoice(self, customer_id: int, total_amount: Optional[str] = None, created_at: Optional[str] = None) -> List[Invoice]:
        return self.invoice_repo.list(customer_id=customer_id, total_amount=total_amount, created_at=created_at)

    def list_customer(self, name: Optional[str] = None, email: Optional[str] = None) -> List[Customer]:
        return self.customer_repo.list(name=name, email=email)

    def add_invoice(self, customer_id: int, total_amount: str) -> None:
        if customer_id is not None:
            if self.customer_repo.get_by_id(customer_id) is None:
                raise CustomerNotFoundError(customer_id)
        invoice = Invoice(customer_id=customer_id, total_amount=total_amount, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.invoice_repo.create(invoice)

    def delete_invoice(self, id: int) -> None:
        return self.invoice_repo.delete(id)

    def update_invoice(self, id: int, customer_id: Optional[int] = None, total_amount: Optional[str] = None) -> None:
        data = {k: v for k, v in {'customer_id': customer_id, 'total_amount': total_amount}.items() if v is not None}
        return self.invoice_repo.update(id, data)

    def get_invoice_report(self, id: int) -> Dict:
        invoice = self.invoice_repo.get_by_id(id)
        if not invoice:
            raise InvoiceNotFoundError(f'Invoice with id {id} not found')
        invoice_lines = self.invoice_line_repo.get_invoice_lines_by_invoice_id(invoice.id)
        customer = self.customer_repo.get_by_id(invoice.customer_id)
        if not customer:
            raise CustomerNotFoundError(f'Customer with id {invoice.customer_id} not found')
        invoice_product_summary = self.invoice_repo.get_invoices_with_product_summary(customer_id=invoice.customer_id, date_range_start=invoice.created_at, date_range_end=invoice.created_at)
        return {
            'invoice': invoice,
            'customer': customer,
            'lines': invoice_lines,
            'product_summary': invoice_product_summary
        }

    def list_product(self) -> List[Product]:
        return self.product_repo.list()
