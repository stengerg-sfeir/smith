"""ContactRepository data access."""
from __future__ import annotations

import sqlite3
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
                "INSERT INTO contacts (first_name, last_name, email, phone, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (contact.first_name, contact.last_name, contact.email, contact.phone, contact.address, contact.created_at, contact.updated_at),
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

    def list(self, first_name: Optional[Any] = None, last_name: Optional[Any] = None, email: Optional[Any] = None, phone: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, address: Optional[Any] = None) -> List[Contact]:
        with self.db.connect() as conn:
            query = "SELECT * FROM contacts WHERE 1=1"
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
            if phone is not None:
                query += ' AND phone = ?'
                params.append(phone)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            if address is not None:
                query += ' AND address = ?'
                params.append(address)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Contact(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['first_name', 'last_name', 'email', 'phone', 'address', 'created_at', 'updated_at']
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

    def get_contacts_by_email_domain(self, domain: str) -> list[Contact]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE (first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR address LIKE ?)",
                ("%" + domain + "%", "%" + domain + "%", "%" + domain + "%", "%" + domain + "%", "%" + domain + "%")
            ).fetchall()
            return [Contact(**dict(r)) for r in rows]

    def get_contacts_by_last_name_prefix(self, prefix: str) -> list[Contact]:
        return []

    def get_contact_count_by_last_name(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT last_name AS k, COUNT(*) AS n FROM contacts GROUP BY last_name"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_contacts_with_invalid_email_format(self) -> list[Contact]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM contacts WHERE email NOT LIKE '%@%' OR email NOT LIKE '%@%.%'").fetchall()
            return [Contact(**dict(r)) for r in rows]

    def export_to_csv(self, filename: str) -> bool:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM contacts').fetchall()
            if not rows:
                return False
            csv_content = 'first_name,last_name,email,phone,address,created_at,updated_at\n'
            for row in rows:
                csv_content += f'{row[3]},{row[4]},{row[2]},{row[5]},{row[1]},{row[6]},{row[7]}\n'
            with open(filename, 'w') as f:
                f.write(csv_content)
            return True

    def import_from_csv(self, filename: str) -> list[str]:
        errors = []
        with self.db.connect() as conn:
            with open(filename, 'r') as f:
                lines = f.readlines()
            if not lines or not lines[0].strip().startswith('first_name'):
                return errors
            for line in lines[1:]:
                parts = line.strip().split(',')
                if len(parts) != 7:
                    errors.append(f'Invalid row format: {line}')
                    continue
                first_name, last_name, email, phone, address, created_at, updated_at = parts
                if '@' not in email or ('@' in email and email.count('@') > 1) or '.' not in email.split('@')[-1]:
                    errors.append(f'Invalid email format: {email}')
                    continue
                try:
                    conn.execute('INSERT INTO contacts (first_name, last_name, email, phone, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)', (first_name, last_name, email, phone, address, created_at, updated_at))
                except sqlite3.Error as e:
                    errors.append(f'Database error inserting row: {e}')
        return errors

    def get_total_contact_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM contacts",
            ).fetchone()
            return int(row["n"])

    def get_contacts_created_in_range(self, start_date: datetime, end_date: datetime) -> list[Contact]:
        return []

