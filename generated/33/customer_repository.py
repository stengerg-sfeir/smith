"""CustomerRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import AuditRecord, Customer


class CustomerRepository:
    """SQLite repository for Customer over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, customer: Customer) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO customers (first_name, last_name, email, phone, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (customer.first_name, customer.last_name, customer.email, customer.phone, customer.created_at, customer.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Customer]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ?", (id,)
            ).fetchone()
            return Customer(**dict(row)) if row else None

    def get_all(self) -> List[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM customers ORDER BY id"
            ).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def list(self, first_name: Optional[Any] = None, last_name: Optional[Any] = None, email: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, phone: Optional[Any] = None) -> List[Customer]:
        with self.db.connect() as conn:
            query = "SELECT * FROM customers WHERE 1=1"
            params: List[Any] = []
            if first_name is not None:
                query += ' AND first_name = ?'
                params.append(first_name)
            if last_name is not None:
                query += ' AND last_name = ?'
                params.append(last_name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Customer(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['first_name', 'last_name', 'email', 'phone', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE customers SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM customers WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        return self.list(
            email=email,
        )

    def get_customers_by_last_name_prefix(self, prefix: str) -> list[Customer]:
        return []

    def get_customers_with_active_status(self) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM customers').fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_customer_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM customers",
            ).fetchone()
            return int(row["n"])

    def get_customers_with_total_spending(self) -> list[Customer]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM customers').fetchall()
            return [Customer(**dict(r)) for r in rows]

    def get_audit_records_for_customer(self, customer_id: int, start_date: str, end_date: str) -> list[AuditRecord]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM auditrecords WHERE customer_id = ? AND timestamp BETWEEN ? AND ?', (customer_id, start_date, end_date)).fetchall()
            return [AuditRecord(**dict(r)) for r in rows]

    def get_recent_operations(self, limit: int) -> list[AuditRecord]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM auditrecords ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
            return [AuditRecord(**dict(r)) for r in rows]

    def get_customers_with_last_updated_in_range(self, start_date: datetime, end_date: datetime) -> list[Customer]:
        return []

