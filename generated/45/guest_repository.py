"""GuestRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import GuestNotFoundError
from models import Guest


class GuestRepository:
    """SQLite repository for Guest over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, guest: Guest) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO guests (first_name, last_name, email, phone) VALUES (?, ?, ?, ?)",
                (guest.first_name, guest.last_name, guest.email, guest.phone),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Guest]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM guests WHERE id = ?", (id,)
            ).fetchone()
            return Guest(**dict(row)) if row else None

    def get_all(self) -> List[Guest]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM guests ORDER BY id"
            ).fetchall()
            return [Guest(**dict(r)) for r in rows]

    def list(self, email: Optional[Any] = None, first_name: Optional[Any] = None, last_name: Optional[Any] = None, phone: Optional[Any] = None) -> List[Guest]:
        with self.db.connect() as conn:
            query = "SELECT * FROM guests WHERE 1=1"
            params: List[Any] = []
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if first_name is not None:
                query += ' AND first_name = ?'
                params.append(first_name)
            if last_name is not None:
                query += ' AND last_name = ?'
                params.append(last_name)
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Guest(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['first_name', 'last_name', 'email', 'phone']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE guests SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise GuestNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM guests WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_guests_by_first_name(self, first_name: str) -> list[Guest]:
        return self.list(
            first_name=first_name,
        )

    def get_guests_by_last_name(self, last_name: str) -> list[Guest]:
        return self.list(
            last_name=last_name,
        )

    def get_guests_by_email(self, email: str) -> list[Guest]:
        return self.list(
            email=email,
        )

    def get_guests_with_bookings(self) -> list[Guest]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT g.id, g.first_name, g.last_name, g.email, g.phone FROM guests g JOIN bookings b ON g.id = b.guest_id ORDER BY g.first_name, g.last_name').fetchall()
            return [Guest(**dict(r)) for r in rows]

    def get_guests_without_bookings(self) -> list[Guest]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT g.id, g.first_name, g.last_name, g.email, g.phone FROM guests g WHERE g.id NOT IN (SELECT guest_id FROM bookings) ORDER BY g.first_name, g.last_name').fetchall()
            return [Guest(**dict(r)) for r in rows]

    def get_guests_by_phone(self, phone: str) -> list[Guest]:
        return self.list(
            phone=phone,
        )

    def get_guest_count_by_first_name(self, first_name: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM guests WHERE first_name = ?', (first_name,)).fetchone()
            return row[0] if row else 0

    def get_guest_count_by_last_name(self, last_name: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM guests WHERE last_name = ?', (last_name,)).fetchone()
            return row[0] if row else 0

    def get_guest_count_by_email_domain(self, domain: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM guests WHERE email LIKE ?', (f'%@{domain}',)).fetchone()
            return row[0] if row else 0

    def get_guests_with_active_bookings(self) -> list[Guest]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT g.id, g.first_name, g.last_name, g.email, g.phone FROM guests g JOIN bookings b ON g.id = b.guest_id WHERE b.status = 'active' ORDER BY g.first_name, g.last_name").fetchall()
            return [Guest(**dict(r)) for r in rows]

    def get_guests_with_past_bookings(self) -> list[Guest]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT g.id, g.first_name, g.last_name, g.email, g.phone FROM guests g JOIN bookings b ON g.id = b.guest_id WHERE b.status != 'active' ORDER BY g.first_name, g.last_name").fetchall()
            return [Guest(**dict(r)) for r in rows]

