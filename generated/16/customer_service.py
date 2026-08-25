"""Service layer."""
from __future__ import annotations

from typing import Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from models import Customer


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        return self.customer_repo.get_customer_by_email(email)

    def get_customers_by_last_name_prefix(self, last_name_prefix: str, page_number: int, page_size: int) -> List[Customer] & Dict[str, int]:
        results = {}
        for row in self.customer_repo.list():
            key = row.last_name
            results[key] = results.get(key, 0) + row.id
        return results

    def get_customers_with_active_status(self, page_number: int, page_size: int) -> List[Customer] & Dict[str, int]:
        return self.customer_repo.get_customers_with_active_status(page_number, page_size)

    def get_customers_with_email_domain(self, domain: str, page_number: int, page_size: int) -> List[Customer] & Dict[str, int]:
        results = []
        groups = {}
        for row in self.customer_repo.list():
            key = (row.email)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'email': key[0],
                    'count': len(group),
                })
        return results

    def get_customers_by_phone_pattern(self, phone_pattern: str, page_number: int, page_size: int) -> List[Customer] & Dict[str, int]:
        return self.customer_repo.get_customers_by_phone_pattern(phone_pattern, page_number, page_size)

    def get_customers_with_recent_activity(self, days_ago: int, page_number: int, page_size: int) -> List[Customer] & Dict[str, int]:
        return self.customer_repo.get_customers_with_recent_activity(days_ago, page_number, page_size)

