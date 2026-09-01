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
                "INSERT INTO members (name, email, phone) VALUES (?, ?, ?)",
                (member.name, member.email, member.phone),
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

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, max_isbn: Optional[Any] = None, min_isbn: Optional[Any] = None) -> List[Member]:
        with self.db.connect() as conn:
            query = "SELECT * FROM members WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if max_isbn is not None:
                query += ' AND id <= ?'
                params.append(max_isbn)
            if min_isbn is not None:
                query += ' AND id >= ?'
                params.append(min_isbn)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Member(**dict(r)) for r in rows]

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

    def get_members_by_name_prefix(self, prefix: str) -> list[Member]:
        return []

    def get_members_with_active_borrow_records(self) -> list[Member]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM members JOIN borrow_records ON members.id = borrow_records.member_id WHERE borrow_records.return_date IS NULL', ()).fetchall()
            return [Member(**dict(r)) for r in rows]

    def get_total_members_with_borrowed_books(self) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(DISTINCT members.id) FROM members JOIN borrow_records ON members.id = borrow_records.member_id', ()).fetchone()
            return rows[0] if rows else 0

    def get_members_borrowing_specific_books(self, book_isbn: str) -> list[Member]:
        return []

    def get_members_borrowing_books_in_date_range(self, start_date: datetime, end_date: datetime) -> list[Member]:
        return []

    def get_most_frequent_borrowers(self) -> list[Member]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT members.id, members.name, members.email, members.phone FROM members JOIN borrow_records ON members.id = borrow_records.member_id GROUP BY members.id ORDER BY COUNT(borrow_records.id) DESC LIMIT 10', ()).fetchall()
            return [Member(**dict(r)) for r in rows]

    def get_members_with_no_borrow_records(self) -> list[Member]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM members WHERE id NOT IN (SELECT member_id FROM borrow_records)', ()).fetchall()
            return [Member(**dict(r)) for r in rows]

