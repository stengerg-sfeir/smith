"""MemberRepository data access."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from database import Database
from models import Loan, Member


class MemberRepository:
    """SQLite repository for Member over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, member: Member) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO members (name, email, membership_date, is_active) VALUES (?, ?, ?, ?)",
                (member.name, member.email, member.membership_date, member.is_active),
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

    def list(self, is_active: Optional[Any] = None, email: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Member]:
        with self.db.connect() as conn:
            query = "SELECT * FROM members WHERE 1=1"
            params: List[Any] = []
            if is_active is not None:
                query += ' AND is_active = ?'
                params.append(is_active)
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if start_date is not None:
                query += ' AND membership_date >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND membership_date <= ?'
                params.append(end_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Member(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'email', 'membership_date', 'is_active']
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
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM members WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def find_by_email(self, email: str) -> Optional[Member]:
        return self.list(email=email)

    def find_active_members(self) -> List[Member]:
        return self.list(is_active=True)

    def find_inactive_members(self) -> List[Member]:
        return self.list(is_active=False)

    def get_total_active_members(self) -> int:
        with self.db.connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM members WHERE is_active = ?", (True,))
            return cur.fetchone()[0]

    def get_total_inactive_members(self) -> int:
        with self.db.connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM members WHERE is_active = ?", (False,))
            return cur.fetchone()[0]

    def get_members_by_name_prefix(self, prefix: str) -> List[Member]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM members WHERE name LIKE ? ORDER BY name",
                (f"{prefix}%",)
            ).fetchall()
            return [Member(**dict(r)) for r in rows]

    def get_members_with_membership_date_range(self, start_date: date, end_date: date) -> List[Member]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_member_loan_history(self, member_id: int) -> List[Loan]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loans WHERE member_id = ? ORDER BY loan_date",
                (member_id,)
            ).fetchall()
            return [Loan(**dict(r)) for r in rows]

    def get_book_loan_history_by_member(self, member_id: int) -> List[Loan]:
        return self.get_member_loan_history(member_id)

