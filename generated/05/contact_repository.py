"""ContactRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Contact


class ContactRepository:
    """SQLite repository for Contact over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, contact: Contact) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO contacts (name, email, phone) VALUES (?, ?, ?)",
                (contact.name, contact.email, contact.phone),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Contact]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (id,)
            ).fetchone()
            return Contact(**dict(row)) if row else None

    def get_all(self) -> List[Contact]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY id"
            ).fetchall()
            return [Contact(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, email: Optional[Any] = None, phone: Optional[Any] = None) -> List[Contact]:
        with self.db.connect() as conn:
            query = "SELECT * FROM contacts WHERE 1=1"
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
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Contact(**dict(r)) for r in rows]

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
                "UPDATE contacts SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM contacts WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_contact_by_email(self, email: str) -> Optional[Contact]:
        return self.list(
            email=email,
        )

    def get_contact_by_phone(self, phone: str) -> Optional[Contact]:
        return self.list(
            phone=phone,
        )

    def search_contacts(self, query: str, case_sensitive: bool) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            if case_sensitive:
                cursor.execute('SELECT * FROM contacts WHERE name LIKE ? OR email LIKE ?', (f'%{query}%', f'%{query}%'))
            else:
                cursor.execute('SELECT * FROM contacts WHERE LOWER(name) LIKE LOWER(?) OR LOWER(email) LIKE LOWER(?)', (f'%{query}%', f'%{query}%'))
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

    def count_contacts(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM contacts')
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_contacts_with_email_domain(self, domain: str) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE email LIKE ?', (f'{domain}@',))
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

    def get_contacts_by_name_prefix(self, prefix: str) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE name LIKE ?', (f'{prefix}%',))
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

    def get_contact_with_most_phones(self) -> Optional[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT * FROM contacts \n                ORDER BY (CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) DESC, \n                       phone DESC \n                LIMIT 1\n            ')
            row = cursor.fetchone()
            return Contact(**dict(row)) if row else None

    def get_contact_with_most_emails(self) -> Optional[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('\n                SELECT * FROM contacts \n                ORDER BY (CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) DESC, \n                       email DESC \n                LIMIT 1\n            ')
            row = cursor.fetchone()
            return Contact(**dict(row)) if row else None

    def get_contacts_with_no_email(self) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE email IS NULL')
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

    def get_contacts_with_no_phone(self) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE phone IS NULL')
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

