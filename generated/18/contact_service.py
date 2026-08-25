"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from contact_repository import ContactRepository
from database import Database
from exceptions import (
    DuplicateEntryError,
)
from models import Contact


class ContactService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.contact_repo = ContactRepository(db)

    def create_contact(self, contact: Contact) -> bool:
        try:
            self.contact_repo.create(contact)
            return True
        except DuplicateEntryError:
            raise
        except Exception as e:
            raise e

    def get_contact_by_id(self, contact_id: int) -> Optional[Contact]:
        return self.contact_repo.get_by_id(contact_id)

    def update_contact(self, contact_id: int, contact: Contact) -> bool:
        data = {k: v for k, v in {}.items() if v is not None}
        return self.contact_repo.update(contact_id, data)

    def delete_contact(self, contact_id: int) -> bool:
        return self.contact_repo.delete(contact_id)

    def get_contacts_by_email_domain(self, domain: str) -> List[Contact]:
        try:
            return self.contact_repo.get_contacts_by_email_domain(domain)
        except Exception as e:
            raise e

    def get_contacts_by_last_name_prefix(self, prefix: str) -> List[Contact]:
        try:
            return self.contact_repo.get_contacts_by_last_name_prefix(prefix)
        except Exception as e:
            raise e

    def get_contact_count_by_last_name(self) -> Dict[str, int]:
        return self.contact_repo.get_contact_count_by_last_name()

    def get_contacts_with_invalid_email_format(self) -> List[Contact]:
        try:
            return self.contact_repo.get_contacts_with_invalid_email_format()
        except Exception as e:
            raise e

    def export_to_csv(self, filename: str) -> bool:
        try:
            return self.contact_repo.export_to_csv(filename)
        except Exception as e:
            raise e

    def import_from_csv(self, filename: str) -> List[str]:
        try:
            return self.contact_repo.import_from_csv(filename)
        except Exception as e:
            raise e

    def get_total_contact_count(self) -> int:
        try:
            return self.contact_repo.get_total_contact_count()
        except Exception as e:
            raise e

    def get_contacts_with_phone_and_email(self) -> List[Contact]:
        try:
            return self.contact_repo.get_contacts_with_phone_and_email()
        except Exception as e:
            raise e

    def add_contact(self, first_name: str, last_name: str, email: str, phone: str, address: str) -> int:
        contact = Contact(first_name=first_name, last_name=last_name, email=email, phone=phone, address=address, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.contact_repo.create(contact)

