"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    DomainFilterError,
    ValidationError,
)
from models import Customer


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def create_customer(self, name: str, email: str, phone: Optional[str] = None) -> bool:
        customer = Customer(name=name, email=email, phone=phone)
        return self.customer_repo.create(customer)

    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        """Retrieve a customer by email address."""
        try:
            customers = self.customer_repo.get_customers_with_email_pattern(email)
            return customers[0] if customers else None
        except (IndexError, TypeError):
            return None

    def get_customers_by_domain(self, domain: str) -> List[Customer]:
        """Retrieve all customers by domain."""
        try:
            return self.customer_repo.get_customers_by_domain(domain)
        except Exception as e:
            raise DomainFilterError(f'Error filtering customers by domain: {str(e)}')

    def search_customers_by_name(self, name: str) -> List[Customer]:
        """Search customers whose name contains the given substring."""
        try:
            return self.customer_repo.get_customers_with_name_containing(name)
        except Exception as e:
            raise ValidationError(f'Error searching customers by name: {str(e)}')

    def filter_customers_by_email_domain(self, domain: str) -> List[Customer]:
        """Filter customers by email domain."""
        try:
            return self.customer_domain_filter(domain)
        except Exception as e:
            raise DomainFilterError(f'Error filtering customers by email domain: {str(e)}')

    def get_total_customers(self) -> int:
        """Get the total number of customers."""
        try:
            return self.customer_repo.get_total_customers()
        except Exception as e:
            raise ValidationError(f'Error getting total customer count: {str(e)}')

    def get_customers_with_phone_prefix(self, prefix: str) -> List[Customer]:
        """Retrieve customers whose phone number starts with the given prefix."""
        try:
            return self.customer_repo.get_customers_with_phone_prefix(prefix)
        except Exception as e:
            raise ValidationError(f'Error filtering customers by phone prefix: {str(e)}')

