"""Service layer."""
from __future__ import annotations

from typing import Optional

from contact_repository import ContactRepository
from database import Database
from models import Contact


class ContactService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.contact_repo = ContactRepository(db)

    def add_contact(self, name: str, email: Optional[str] = None, phone: Optional[str] = None) -> bool:
        contact = Contact(name=name, email=email, phone=phone)
        return self.contact_repo.create(contact)

    def list_contact(self, name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> list[Contact]:
        return self.contact_repo.list(name=name, email=email, phone=phone)

    def update_contact(self, id: int, name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'name': name, 'email': email, 'phone': phone}.items() if v is not None}
        return self.contact_repo.update(id, data)

    def delete_contact(self, id: int) -> bool:
        return self.contact_repo.delete(id)

