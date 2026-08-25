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
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE email LIKE ?', (f'%@{domain}',))
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

    def get_contacts_by_last_name_prefix(self, prefix: str) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE last_name LIKE ?', (f'{prefix}%',))
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

    def get_contact_count_by_last_name(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT last_name, COUNT(*) AS count FROM contacts GROUP BY last_name')
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    def get_contacts_with_invalid_email_format(self) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE email NOT LIKE ? AND email NOT LIKE ?', ('%@.', '%@%'))
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

    def export_to_csv(self, filename: str) -> bool:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts')
            rows = cursor.fetchall()
            if not rows:
                return False
            headers = ['id', 'first_name', 'last_name', 'email', 'phone', 'address', 'created_at', 'updated_at']
            content = [headers]
            for row in rows:
                content.append([row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]])
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    for line in content:
                        f.write(','.join((str(cell) for cell in line)) + '\n')
                return True
            except Exception:
                return False

    def import_from_csv(self, filename: str) -> list[str]:
        errors = []
        with self.db.connect() as conn:
            cursor = conn.cursor()
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                if not lines:
                    return errors
                headers = lines[0].strip().split(',')
                if len(headers) != 8:
                    errors.append('Invalid number of columns in CSV')
                    return errors
                for line in lines[1:]:
                    fields = line.strip().split(',')
                    if len(fields) != 8:
                        errors.append(f'Line has invalid number of fields: {len(fields)}')
                        continue
                    try:
                        contact_data = {'first_name': fields[1], 'last_name': fields[2], 'email': fields[3], 'phone': fields[4], 'address': fields[5], 'created_at': fields[6], 'updated_at': fields[7]}
                        if '@' not in contact_data['email'] or '.' not in contact_data['email']:
                            errors.append(f"Invalid email format: {contact_data['email']}")
                            continue
                        if not contact_data['phone']:
                            errors.append(f"Missing phone for contact: {contact_data['first_name']} {contact_data['last_name']}")
                            continue
                        cursor.execute('INSERT INTO contacts (first_name, last_name, email, phone, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)', (contact_data['first_name'], contact_data['last_name'], contact_data['email'], contact_data['phone'], contact_data['address'], contact_data['created_at'], contact_data['updated_at']))
                    except Exception as e:
                        errors.append(f'Error importing contact: {str(e)}')
            except Exception as e:
                errors.append(f'Error reading CSV file: {str(e)}')
        return errors

    def get_total_contact_count(self) -> int:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM contacts')
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_contacts_with_phone_and_email(self) -> list[Contact]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contacts WHERE phone IS NOT NULL AND email IS NOT NULL')
            rows = cursor.fetchall()
            return [Contact(**dict(r)) for r in rows]

