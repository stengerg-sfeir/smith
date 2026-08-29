"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List

from customer_repository import CustomerRepository
from database import Database
from models import AuditRecord


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def log_audit_record(self, customer_id: int, operation: str, timestamp: datetime) -> None:
        audit_record = AuditRecord(customer_id=customer_id, id=None, operation=operation, timestamp=timestamp)
        self.customer_repo.create(audit_record)

    def get_audit_records_by_customer(self, customer_id: int, start_date: datetime, end_date: datetime) -> List[AuditRecord]:
        return self.customer_repo.get_audit_records_for_customer(customer_id, start_date, end_date)

    def get_audit_records_by_operation(self, operation: str, start_date: datetime, end_date: datetime) -> List[AuditRecord]:
        customers = self.customer_repo.get_customers_with_active_status()
        records = []
        for customer in customers:
            customer_id = customer.id
            customer_records = self.customer_repo.get_audit_records_for_customer(customer_id=customer_id, start_date=start_date, end_date=end_date)
            records.extend([record for record in customer_records if record.operation == operation])
        return records

    def find_duplicate_audit_operations(self, operation: str) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.audit_record_repo.list(operation=operation):
            key = (row.operation)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'operation': key[0],
                    'count': len(group),
                })
        return results

    def get_audit_summary_by_month(self, start_year: int, end_year: int) -> Dict[str, int]:
        rows = self.audit_record_repo.list(
            timestamp=str(start_year) + '-01-01',
            timestamp_end=str(start_year) + '-12-31',
        )
        total = sum(e.id for e in rows)
        return {'start_year': start_year, 'total_audit_records_per_year': total}

