"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List

from auditrecord_repository import AuditrecordRepository
from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    ValidationError,
)
from models import AuditRecord


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.audit_record_repo = AuditrecordRepository(db)
        self.customer_repo = CustomerRepository(db)

    def log_audit_record(self, customer_id: int, operation: str, timestamp: datetime.datetime) -> None:
        """
            Logs an audit record for a customer operation.
            """
        self.validate_audit_operation(operation)
        audit_record = AuditRecord(customer_id=customer_id, id=None, operation=operation, timestamp=timestamp)
        self.audit_record_repo.create(audit_record)

    def get_audit_records_by_customer(self, customer_id: int, start_date: datetime.datetime, end_date: datetime.datetime) -> List[AuditRecord]:
        """
            Retrieves audit records for a specific customer within a date range.
            """
        records = self.customer_repo.get_audit_records_for_customer(customer_id, start_date, end_date)
        return records

    def get_audit_records_by_operation(self, operation: str, start_date: datetime.datetime, end_date: datetime.datetime) -> List[AuditRecord]:
        """
            Retrieves audit records for a specific operation within a date range.
            """
        self.validate_audit_operation(operation)
        records = self.audit_record_repo.list(operation=operation, start_date=start_date, end_date=end_date)
        return records

    def get_audit_summary_by_month(self, start_year: int, end_year: int) -> Dict[str, int]:
        """
            Returns a summary of audit operations grouped by month.
            """
        summary = {}
        records = self.audit_record_repo.list(start_date=datetime.datetime(start_year, 1, 1), end_date=datetime.datetime(end_year, 12, 31))
        for record in records:
            month = f'{record.timestamp.year}-{record.timestamp.month:02d}'
            summary[month] = summary.get(month, 0) + 1
        return summary

    def validate_audit_operation(self, operation: str) -> None:
        """
            Validates that the operation is one of the allowed operations.
            """
        allowed_operations = ['create', 'update', 'delete', 'read']
        if operation not in allowed_operations:
            raise ValidationError(f"Invalid operation: {operation}. Allowed operations are: {', '.join(allowed_operations)}")
