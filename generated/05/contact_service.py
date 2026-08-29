"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from contact_repository import ContactRepository
from database import Database
from models import Contact


class ContactService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.contact_repo = ContactRepository(db)

    def create_contact(self, name: str, email: Optional[str] = None, phone: Optional[str] = None) -> Contact:
        contact = Contact(name=name, email=email, phone=phone)
        return self.contact_repo.create(contact)

    def list_contacts(self) -> List[Contact]:
        return self.contact_repo.list()

    def update_contact(self, contact_id: int, name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> Optional[Contact]:
        data = {k: v for k, v in {'name': name, 'email': email, 'phone': phone}.items() if v is not None}
        return self.contact_repo.update(contact_id, data)

    def delete_contact(self, contact_id: int) -> bool:
        return self.contact_repo.delete(contact_id)

    def search_contacts(self, query: str, case_sensitive: bool) -> List[Contact]:
        return self.contact_repo.search_contacts(query, case_sensitive)

    def get_contact_by_email(self, email: str) -> Optional[Contact]:
        return self.contact_repo.get_contact_by_email(email)

    def get_contact_by_phone(self, phone: str) -> Optional[Contact]:
        return self.contact_repo.get_contact_by_phone(phone)

    def get_contacts_with_email_domain(self, domain: str) -> List[Contact]:
        return self.contact_repo.get_contacts_with_email_domain(domain)

    def get_contacts_by_name_prefix(self, prefix: str) -> List[Contact]:
        return self.contact_repo.get_contacts_by_name_prefix(prefix)

    def get_contact_with_most_phones(self) -> Optional[Contact]:
        return self.contact_repo.get_contact_with_most_phones()

    def get_contact_with_most_emails(self) -> Optional[Contact]:
        return self.contact_repo.get_contact_with_most_emails()

    def get_contacts_with_no_email(self) -> List[Contact]:
        return self.contact_repo.get_contacts_with_no_email()

    def get_contacts_with_no_phone(self) -> List[Contact]:
        return self.contact_repo.get_contacts_with_no_phone()

