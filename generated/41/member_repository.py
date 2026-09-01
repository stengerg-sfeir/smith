"""MemberRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import MemberNotFoundError
from models import Member


class MemberRepository:
    """SQLite repository for Member over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, member: Member) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO members (name, email, phone, membership_since, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (member.name, member.email, member.phone, member.membership_since, member.created_at, member.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Member]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM members WHERE id = ?", (id,)
            ).fetchone()
            return Member(**dict(row)) if row else None

    def get_all(self) -> List[Member]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM members ORDER BY id"
            ).fetchall()
            return [Member(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, membership_since: Optional[Any] = None, phone: Optional[Any] = None) -> List[Member]:
        with self.db.connect() as conn:
            query = "SELECT * FROM members WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if membership_since is not None:
                query += ' AND membership_since >= ?'
                params.append(membership_since)
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Member(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'phone', 'membership_since', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE members SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise MemberNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM members WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_members_by_email_domain(self, domain: str) -> list[Member]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM members WHERE (name LIKE ? OR email LIKE ? OR phone LIKE ?)",
                ("%" + domain + "%", "%" + domain + "%", "%" + domain + "%")
            ).fetchall()
            return [Member(**dict(r)) for r in rows]

    def get_members_with_active_loans(self) -> list[Member]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT DISTINCT m.id, m.name, m.email, m.phone, m.membership_since, m.created_at, m.updated_at \n                   FROM members m\n                   JOIN loans l ON m.id = l.member_id\n                   WHERE l.is_returned = 0').fetchall()
            return [Member(**dict(r)) for r in rows]

    def get_members_borrowing_specific_book(self, book_id: int) -> list[Member]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM members r JOIN loans j ON r.id = j.member_id JOIN books o ON j.book_id = o.id WHERE o.name = ?",
                (book_id,)
            ).fetchall()
            return [Member(**dict(r)) for r in rows]

    def get_members_with_membership_since(self, start_date: date, end_date: date) -> list[Member]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM members WHERE membership_since >= ? AND membership_since <= ?", ((start_date, end_date))
            ).fetchall()
            return [Member(**dict(r)) for r in rows]

    def get_total_members_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM members",
            ).fetchone()
            return int(row["n"])

    def get_members_by_name_contains(self, name: str) -> list[Member]:
        return self.list(
            name=name,
        )

    def get_members_with_phone(self, phone: str) -> list[Member]:
        return self.list(
            phone=phone,
        )

    def get_members_due_to_return_books(self) -> list[Member]:
        with self.db.connect() as conn:
            today = '2024-12-31'
            rows = conn.execute('SELECT DISTINCT m.id, m.name, m.email, m.phone, m.membership_since, m.created_at, m.updated_at \n                   FROM members m\n                   JOIN loans l ON m.id = l.member_id\n                   WHERE l.due_date <= ?', (today,)).fetchall()
            return [Member(**dict(r)) for r in rows]

