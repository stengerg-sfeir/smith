"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    ValidationError,
)
from models import AuditRecord, Customer


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def create_customer(self, customer_data: Dict[str, Optional[str]]) -> int:
        self.validate_customer_data(customer_data)
        customer = Customer(email=customer_data.get('email'), first_name=customer_data.get('first_name'), last_name=customer_data.get('last_name'), phone=customer_data.get('phone'))
        customer_id = self.customer_repo.create(customer)
        return customer_id

    def update_customer(self, customer_id: int, updates: Dict[str, Optional[str]]) -> None:
        data = {k: v for k, v in updates.items() if v is not None}
        self.customer_repo.update(customer_id, data)

    def delete_customer(self, customer_id: int) -> None:
        self.customer_repo.delete(customer_id)

    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        return self.customer_repo.get_customer_by_email(email)

    def get_customers_by_last_name_prefix(self, prefix: str) -> List[Customer]:
        return self.customer_repo.get_customers_by_last_name_prefix(prefix)

    def get_customers_with_active_status(self) -> List[Customer]:
        return self.customer_repo.get_customers_with_active_status()

    def get_customer_count(self) -> int:
        return self.customer_repo.get_customer_count()

    def get_customers_with_total_spending(self) -> List[Customer]:
        return self.customer_repo.get_customers_with_total_spending()

    def get_audit_records_for_customer(self, customer_id: int, start_date: datetime, end_date: datetime) -> List[AuditRecord]:
        return self.customer_repo.get_audit_records_for_customer(customer_id, start_date, end_date)

    def get_recent_activity_summary(self) -> Dict[str, Any]:
        return self.customer_repo.get_recent_activity_summary()

    def validate_customer_data(self, data: Dict[str, Optional[str]]) -> None:
        required_fields = ['email', 'first_name', 'last_name']
        for field in required_fields:
            if data.get(field) is None:
                raise ValidationError(f'Missing required field: {field}')
        email = data.get('email')
        if '@' not in email or '.' not in email:
            raise ValidationError('Invalid email format')
