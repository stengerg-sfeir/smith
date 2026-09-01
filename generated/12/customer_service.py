"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CustomerNotFoundError,
)
from models import Customer


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def add_customer(self, name: str, email: str, phone: str) -> None:
        customer = Customer(name=name, email=email, phone=phone)
        return self.customer_repo.create(customer)

    def list_customer(self, name: Optional[str] = None, email_domain: Optional[str] = None) -> List[Customer]:
        return self.customer_repo.list(name=name, email_domain=email_domain)

    def update_customer(self, id: int, name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> None:
        data = {k: v for k, v in {'name': name, 'email': email, 'phone': phone}.items() if v is not None}
        return self.customer_repo.update(id, data)

    def delete_customer(self, id: int) -> None:
        return self.customer_repo.delete(id)

    def search_customer(self, term: str) -> List[Customer]:
        """
            Search for customers whose name or email contains the given term.
            Uses case-insensitive matching for name and email.
            """
        results = []
        results.extend(self.customer_repo.get_customers_with_name_containing(term))
        try:
            if '@' in term and '.' in term:
                results.extend(self.customer_repo.get_customers_with_email_pattern(term))
        except Exception:
            pass
        if term.startswith('+') or term.startswith('0') or len(term) >= 3:
            results.extend(self.customer_repo.get_customers_with_phone_prefix(term))
        seen = set()
        unique_results = []
        for customer in results:
            if customer.email not in seen:
                seen.add(customer.email)
                unique_results.append(customer)
        return unique_results

    def filter_customer(self, id: int) -> List[Customer]:
        """
            Filter customer by ID. Returns a list containing the customer with the given ID.
            Raises CustomerNotFoundError if no such customer exists.
            """
        customer = self.customer_repo.get_by_id(id)
        if not customer:
            raise CustomerNotFoundError(f'Customer with ID {id} not found')
        return [customer]

