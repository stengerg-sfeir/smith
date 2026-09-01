"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from contact_repository import ContactRepository
from database import Database
from exceptions import (
    ImportError,
    NotFoundError,
)
from models import Contact


class ContactService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.contact_repo = ContactRepository(db)

    def add_contact(self, first_name: str, last_name: str, email: Optional[str] = None, phone: Optional[str] = None, address: Optional[str] = None) -> bool:
        contact = Contact(first_name=first_name, last_name=last_name, email=email, phone=phone, address=address, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.contact_repo.create(contact)

    def list_contact(self, first_name: Optional[str] = None, last_name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None, created_at: Optional[str] = None, created_at_end: Optional[str] = None) -> list[dict]:
        return self.contact_repo.list(first_name=first_name, last_name=last_name, email=email, phone=phone, created_at=created_at, created_at_end=created_at_end)

    def update_contact(self, id: int, first_name: Optional[str] = None, last_name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None, address: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'first_name': first_name, 'last_name': last_name, 'email': email, 'phone': phone, 'address': address}.items() if v is not None}
        return self.contact_repo.update(id, data)

    def delete_contact(self, id: int) -> bool:
        return self.contact_repo.delete(id)

    def get_contact_report(self, id: int) -> dict:
        """
            Retrieve a detailed report for a specific contact by ID.
        
            Returns:
                dict: A dictionary containing contact details and related metadata.
            """
        try:
            contact = self.contact_repo.get_by_id(id)
            if not contact:
                raise NotFoundError(f'Contact with ID {id} not found')
            report = {'id': contact.id, 'first_name': contact.first_name, 'last_name': contact.last_name, 'email': contact.email, 'phone': contact.phone, 'address': contact.address, 'created_at': contact.created_at.isoformat() if contact.created_at else None, 'updated_at': contact.updated_at.isoformat() if contact.updated_at else None}
            return report
        except Exception as e:
            raise NotFoundError(f'Failed to retrieve contact: {str(e)}')

    def import_contact(self, filename: str) -> List[str]:
        """
            Import contacts from a CSV file.
        
            Args:
                filename (str): Path to the CSV file to import.
            
            Returns:
                List[str]: List of error messages for failed imports.
            """
        try:
            errors = self.contact_repo.import_from_csv(filename)
            if errors:
                return errors
            return []
        except Exception as e:
            raise ImportError(f'Failed to import contacts from {filename}: {str(e)}')

