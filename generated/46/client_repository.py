"""ClientRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import ClientNotFoundError
from models import Client, Invoice, Payment


class ClientRepository:
    """SQLite repository for Client over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, client: Client) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO clients (name, email, phone) VALUES (?, ?, ?)",
                (client.name, client.email, client.phone),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Client]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM clients WHERE id = ?", (id,)
            ).fetchone()
            return Client(**dict(row)) if row else None

    def get_all(self) -> List[Client]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clients ORDER BY id"
            ).fetchall()
            return [Client(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, phone: Optional[Any] = None, max_amount: Optional[Any] = None, min_amount: Optional[Any] = None) -> List[Client]:
        with self.db.connect() as conn:
            query = "SELECT * FROM clients WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
            if max_amount is not None:
                query += ' AND id <= ?'
                params.append(max_amount)
            if min_amount is not None:
                query += ' AND id >= ?'
                params.append(min_amount)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Client(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'phone']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE clients SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ClientNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM clients WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_outstanding_invoices(self, client_id: int, due_date_after: date) -> list[Invoice]:
        return []

    def get_client_invoices_summary(self, client_id: int) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT \n                    status,\n                    COUNT(*) as count,\n                    SUM(amount) as total_amount\n                FROM invoices \n                WHERE client_id = ?\n                GROUP BY status\n                ', (client_id,)).fetchall()
            return {row[0]: {'count': row[1], 'total_amount': row[2]} for row in rows}

    def get_overdue_invoices(self, client_id: int, due_date_cutoff: date) -> list[Invoice]:
        return []

    def get_client_payment_history(self, client_id: int, start_date: date, end_date: date) -> list[Payment]:
        return []

    def get_total_outstanding_amount(self, client_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute("SELECT SUM(amount) FROM invoices WHERE client_id = ? AND status = 'outstanding'", (client_id,)).fetchone()
            return row[0] if row[0] is not None else 0.0

    def get_client_with_most_outstanding_invoices(self) -> Client:
        with self.db.connect() as conn:
            rows = conn.execute("\n                SELECT c.id, c.name, c.email, c.phone \n                FROM clients c\n                JOIN invoices i ON c.id = i.client_id\n                WHERE i.status = 'outstanding'\n                GROUP BY c.id, c.name, c.email, c.phone\n                ORDER BY COUNT(i.id) DESC\n                LIMIT 1\n                ").fetchall()
            if not rows:
                return None
            row = rows[0]
            return Client(**dict(row))

    def get_invoices_by_status(self, client_id: int, status: str) -> list[Invoice]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM invoices WHERE client_id = ? AND status = ?', (client_id, status)).fetchall()
            return [Invoice(**dict(r)) for r in rows]

