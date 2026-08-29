"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    ConflictError,
    ValidationError,
)
from models import AuditRecord, Customer


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def create_customer(self, customer_data: Dict[str, Optional[str]]) -> int:
        """Create a new customer and return the generated customer ID."""
        self.validate_customer_data(customer_data)
        customer = Customer(first_name=customer_data.get('first_name'), last_name=customer_data.get('last_name'), email=customer_data.get('email'), phone=customer_data.get('phone'))
        customer_id = self.customer_repo.create(customer)
        return customer_id

    def update_customer(self, customer_id: int, updates: Dict[str, Optional[str]]) -> None:
        data = {k: v for k, v in {}.items() if v is not None}
        return self.customer_repo.update(customer_id, data)

    def delete_customer(self, customer_id: int) -> None:
        return self.customer_repo.delete(customer_id)

    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        """Retrieve a customer by email address."""
        return self.customer_repo.get_customer_by_email(email)

    def get_customers_by_last_name_prefix(self, prefix: str) -> List[Customer]:
        """Retrieve customers whose last name starts with the given prefix."""
        return self.customer_repo.get_customers_by_last_name_prefix(prefix)

    def get_customers_with_active_status(self) -> List[Customer]:
        """Retrieve all customers with active status."""
        return self.customer_repo.get_customers_with_active_status()

    def get_customer_count(self) -> int:
        """Return the total number of customers."""
        return self.customer_repo.get_customer_count()

    def get_customers_with_total_spending(self) -> List[Customer]:
        """Retrieve customers with their total spending calculated."""
        return self.customer_repo.get_customers_with_total_spending()

    def get_audit_records_for_customer(self, customer_id: int, start_date: datetime, end_date: datetime) -> List[AuditRecord]:
        """Retrieve audit records for a specific customer within a date range."""
        return self.customer_repo.get_audit_records_for_customer(customer_id, start_date, end_date)

    def get_recent_activity_summary(self) -> Dict[str, Any]:
        return self.customer_repo.get_recent_activity_summary()

    def validate_customer_data(self, data: Dict[str, Optional[str]]) -> None:
        """Validate that customer data meets required constraints."""
        required_fields = ['first_name', 'last_name', 'email']
        for field in required_fields:
            if data.get(field) is None:
                raise ValidationError(f'Missing required field: {field}')
        email = data.get('email')
        if email and '@' not in email:
            raise ValidationError('Invalid email format')
        existing_customer = self.customer_repo.get_customer_by_email(email)
        if existing_customer is not None:
            raise ConflictError(f'Customer with email {email} already exists')
        phone = data.get('phone')
        if phone and (not phone.isdigit()):
            raise ValidationError('Phone number must contain only digits')

    def add_customer(self, first_name: str, last_name: str, email: str, phone: str) -> int:
        customer = Customer(first_name=first_name, last_name=last_name, email=email, phone=phone, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.customer_repo.create(customer)

