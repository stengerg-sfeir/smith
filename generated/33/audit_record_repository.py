"""AuditRecordRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import AuditRecord


class AuditRecordRepository:
    """SQLite repository for AuditRecord over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, audit_record: AuditRecord) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO auditrecords (customer_id, operation, timestamp) VALUES (?, ?, ?)",
                (audit_record.customer_id, audit_record.operation, audit_record.timestamp),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[AuditRecord]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM auditrecords WHERE id = ?", (id,)
            ).fetchone()
            return AuditRecord(**dict(row)) if row else None

    def get_all(self) -> List[AuditRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM auditrecords ORDER BY id"
            ).fetchall()
            return [AuditRecord(**dict(r)) for r in rows]

    def list(self, customer_id: Optional[Any] = None, operation: Optional[Any] = None, from_timestamp: Optional[Any] = None, to_timestamp: Optional[Any] = None) -> List[AuditRecord]:
        with self.db.connect() as conn:
            query = "SELECT * FROM auditrecords WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if operation is not None:
                query += ' AND operation = ?'
                params.append(operation)
            if from_timestamp is not None:
                query += ' AND timestamp >= ?'
                params.append(from_timestamp)
            if to_timestamp is not None:
                query += ' AND timestamp <= ?'
                params.append(to_timestamp)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [AuditRecord(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'operation', 'timestamp']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE auditrecords SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM auditrecords WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def log_customer_operation(self, customer_id: int, operation: str) -> None:
        return self.list(
            customer_id=customer_id,
            operation=operation,
        )

    def get_audit_records_by_customer_and_date_range(self, customer_id: int, start_date: datetime, end_date: datetime) -> list[AuditRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM auditrecords r JOIN customers o ON r.customer_id = o.id WHERE o.name = ? AND r.timestamp >= ? AND r.timestamp <= ?",
                (customer_id, start_date, end_date)
            ).fetchall()
            return [AuditRecord(**dict(r)) for r in rows]

    def get_audit_records_by_operation_type(self, operation: str, start_date: datetime, end_date: datetime) -> list[AuditRecord]:
        return []

    def get_audit_records_with_customer_last_name_prefix(self, prefix: str, start_date: datetime, end_date: datetime) -> list[AuditRecord]:
        return []

    def get_audit_records_for_time_period(self, start_date: datetime, end_date: datetime) -> list[AuditRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM auditrecords WHERE timestamp >= ? AND timestamp <= ?", ((start_date, end_date))
            ).fetchall()
            return [AuditRecord(**dict(r)) for r in rows]

