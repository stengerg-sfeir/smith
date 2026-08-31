"""NotificationRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Notification


class NotificationRepository:
    """SQLite repository for Notification over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, notification: Notification) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO notifications (order_id, message, sent_at, sent_to) VALUES (?, ?, ?, ?)",
                (notification.order_id, notification.message, notification.sent_at, notification.sent_to),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Notification]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM notifications WHERE id = ?", (id,)
            ).fetchone()
            return Notification(**dict(row)) if row else None

    def get_all(self) -> List[Notification]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY id"
            ).fetchall()
            return [Notification(**dict(r)) for r in rows]

    def list(self, order_id: Optional[Any] = None, sent_at: Optional[Any] = None, sent_at_end: Optional[Any] = None) -> List[Notification]:
        with self.db.connect() as conn:
            query = "SELECT * FROM notifications WHERE 1=1"
            params: List[Any] = []
            if order_id is not None:
                query += ' AND order_id = ?'
                params.append(order_id)
            if sent_at is not None:
                query += ' AND sent_at >= ?'
                params.append(sent_at)
            if sent_at_end is not None:
                query += ' AND sent_at <= ?'
                params.append(sent_at_end)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Notification(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['order_id', 'message', 'sent_at', 'sent_to']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE notifications SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM notifications WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

