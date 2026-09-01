"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CustomerNotFoundError,
    InvoiceNotFoundError,
    InvoiceTotalCalculationError,
    ProductNotFoundError,
    ValidationError,
)
from invoice_line_repository import InvoiceLineRepository
from invoice_repository import InvoiceRepository
from models import Customer, Invoice, InvoiceLine, Product
from product_repository import ProductRepository


class InvoiceService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.invoice_repo = InvoiceRepository(db)
        self.invoice_line_repo = InvoiceLineRepository(db)
        self.product_repo = ProductRepository(db)

    def add_invoice(self, customer_id: int, total_amount: str) -> Optional[bool]:
        if customer_id is not None:
            if self.customer_repo.get_by_id(customer_id) is None:
                raise CustomerNotFoundError(customer_id)
        invoice = Invoice(customer_id=customer_id, total_amount=total_amount, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.invoice_repo.create(invoice)

    def list_invoice(self, customer_id: str, total_amount: str, created_at: str) -> List[Dict]:
        return self.invoice_repo.list(customer_id=customer_id, total_amount=total_amount, created_at=created_at)

    def add_invoice_line(self, invoice_id: int, product_id: int, quantity: int, unit_price: str) -> Optional[bool]:
        if invoice_id is not None:
            if self.invoice_repo.get_by_id(invoice_id) is None:
                raise InvoiceNotFoundError(invoice_id)
        if product_id is not None:
            if self.product_repo.get_by_id(product_id) is None:
                raise ProductNotFoundError(product_id)
        invoice_line = InvoiceLine(invoice_id=invoice_id, product_id=product_id, quantity=quantity, unit_price=unit_price)
        return self.invoice_line_repo.create(invoice_line)

    def delete_invoice_line(self, id: int) -> Optional[bool]:
        return self.invoice_line_repo.delete(id)

    def update_invoice_line(self, id: int, invoice_id: int, product_id: int, quantity: int, unit_price: str) -> Optional[bool]:
        data = {k: v for k, v in {'invoice_id': invoice_id, 'product_id': product_id, 'quantity': quantity, 'unit_price': unit_price}.items() if v is not None}
        return self.invoice_line_repo.update(id, data)

    def get_invoice_total(self, id: int) -> Optional[float]:
        try:
            invoice = self.invoice_repo.get_by_id(id)
            if not invoice:
                raise InvoiceNotFoundError(f'Invoice with id {id} not found')
            total = 0.0
            invoice_lines = self.invoice_line_repo.get_invoice_lines_by_invoice_id(invoice.id)
            for line in invoice_lines:
                total += line.quantity * float(line.unit_price)
            return total
        except Exception as e:
            raise InvoiceTotalCalculationError(f"Error calculating invoice total: {str(e)}")

    def add_customer(self, name: str, email: str) -> Optional[bool]:
        try:
            if not name or not email:
                raise ValidationError("Name and email are required")
            customer = Customer(name=name, email=email)
            return self.customer_repo.create(customer)
        except Exception as e:
            raise ValidationError(f"Failed to add customer: {str(e)}")

    def add_product(self, name: str, price: str) -> Optional[bool]:
        try:
            if not name or not price:
                raise ValidationError("Name and price are required")
            product = Product(name=name, price=price)
            return self.product_repo.create(product)
        except Exception as e:
            raise ValidationError(f"Failed to add product: {str(e)}")

    def get_product_report(self) -> List[Dict]:
        products = self.product_repo.list()
        report = []
        for product in products:
            report.append({
                "id": product.id,
                "name": product.name,
                "price": product.price
            })
        return report
