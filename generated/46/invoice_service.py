"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List

from client_repository import ClientRepository
from database import Database
from exceptions import (
    ClientNotFoundError,
)
from invoice_repository import InvoiceRepository
from models import Client, Invoice
from payment_repository import PaymentRepository


class InvoiceService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.client_repo = ClientRepository(db)
        self.invoice_repo = InvoiceRepository(db)
        self.payment_repo = PaymentRepository(db)

    def add_client(self, name: str, email: str, phone: str) -> None:
        client = Client(name=name, email=email, phone=phone)
        return self.client_repo.create(client)

    def add_invoice(self, client_id: int, invoice_number: str, due_date: str, amount: str, status: str) -> None:
        if client_id is not None:
            if self.client_repo.get_by_id(client_id) is None:
                raise ClientNotFoundError(client_id)
        invoice = Invoice(client_id=client_id, invoice_number=invoice_number, due_date=due_date, amount=amount, status=status, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.invoice_repo.create(invoice)

    def record_invoice(self, id: int) -> None:
        client = self.client_repo.get_by_id(id)
        if not client:
            raise ClientNotFoundError(f'Client with id {id} not found')
        invoice_number = f'INV-{id:04d}'
        new_invoice = Invoice(amount=0.0, client_id=id, created_at=datetime.datetime.now(), due_date=datetime.datetime.now() + datetime.timedelta(days=30), id=id, invoice_number=invoice_number, status='pending', updated_at=datetime.datetime.now())
        self.invoice_repo.create(new_invoice)

    def list_invoice(self, invoice_number: str, due_date: str, amount: str, status: str) -> List[Dict]:
        results = []
        groups = {}
        for row in self.invoice_repo.list(invoice_number=invoice_number, due_date=due_date, amount=amount, status=status):
            key = (row.invoice_number, row.due_date, row.status)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'invoice_number': key[0],
                    'due_date': key[1],
                    'status': key[2],
                    'count': len(group),
                })
        return results

