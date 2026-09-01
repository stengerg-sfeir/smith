"""AppointmentRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Appointment


class AppointmentRepository:
    """SQLite repository for Appointment over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, appointment: Appointment) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO appointments (start_time, end_time, title, description) VALUES (?, ?, ?, ?)",
                (appointment.start_time, appointment.end_time, appointment.title, appointment.description),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Appointment]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM appointments WHERE id = ?", (id,)
            ).fetchone()
            return Appointment(**dict(row)) if row else None

    def get_all(self) -> List[Appointment]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM appointments ORDER BY id"
            ).fetchall()
            return [Appointment(**dict(r)) for r in rows]

    def list(self, start_time: Optional[Any] = None, start_time_end: Optional[Any] = None, end_time: Optional[Any] = None, end_time_end: Optional[Any] = None, title: Optional[Any] = None, description: Optional[Any] = None) -> List[Appointment]:
        with self.db.connect() as conn:
            query = "SELECT * FROM appointments WHERE 1=1"
            params: List[Any] = []
            if start_time is not None:
                query += ' AND start_time >= ?'
                params.append(start_time)
            if start_time_end is not None:
                query += ' AND start_time <= ?'
                params.append(start_time_end)
            if end_time is not None:
                query += ' AND end_time >= ?'
                params.append(end_time)
            if end_time_end is not None:
                query += ' AND end_time <= ?'
                params.append(end_time_end)
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Appointment(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['start_time', 'end_time', 'title', 'description']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE appointments SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM appointments WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_appointments_by_date_range(self, start_date: datetime, end_date: datetime) -> list[Appointment]:
        return []

    def get_appointments_by_title(self, title: str) -> list[Appointment]:
        return self.list(
            title=title,
        )

    def get_appointments_overlapping_with(self, start_time: datetime, end_time: datetime) -> list[Appointment]:
        return self.list(
            start_time=start_time,
            end_time=end_time,
        )

    def get_appointments_with_total_duration(self) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT start_time, end_time, (strftime('%s', end_time) - strftime('%s', start_time)) AS duration FROM appointments").fetchall()
            return {row[0]: row[1] for row in rows}

    def get_appointments_count_by_day(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT substr(start_time, 1, 10) AS day, COUNT(*) AS count FROM appointments GROUP BY substr(start_time, 1, 10)').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_appointments_with_conflict_summary(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT title, COUNT(*) AS conflict_count FROM appointments GROUP BY title HAVING COUNT(*) > 1').fetchall()
            return {row[0]: row[1] for row in rows}

    def get_appointments_for_user(self, user_id: int) -> list[Appointment]:
        return []

    def get_appointments_with_time_range_stats(self) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT strftime('%Y', start_time) AS year, strftime('%m', start_time) AS month, MAX(strftime('%s', end_time) - strftime('%s', start_time)) AS max_duration, MIN(strftime('%s', end_time) - strftime('%s', start_time)) AS min_duration, AVG(strftime('%s', end_time) - strftime('%s', start_time)) AS avg_duration FROM appointments GROUP BY strftime('%Y', start_time), strftime('%m', start_time)").fetchall()
            result = {}
            for row in rows:
                key = f'{row[0]}-{row[1]}'
                result[key] = row[2]
            return result

