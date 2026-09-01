"""TaskRepository data access."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from database import Database
from models import Task


class TaskRepository:
    """SQLite repository for Task over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, task: Task) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO tasks (title, description, status, priority, due_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task.title, task.description, task.status, task.priority, task.due_date, task.created_at, task.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Task]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (id,)
            ).fetchone()
            return Task(**dict(row)) if row else None

    def get_all(self) -> List[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY id"
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def list(self, title: Optional[Any] = None, status: Optional[Any] = None, priority: Optional[Any] = None, due_date: Optional[Any] = None, due_date_end: Optional[Any] = None, description: Optional[Any] = None) -> List[Task]:
        with self.db.connect() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params: List[Any] = []
            if title is not None:
                query += ' AND title = ?'
                params.append(title)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            if priority is not None:
                query += ' AND priority = ?'
                params.append(priority)
            if due_date is not None:
                query += ' AND due_date >= ?'
                params.append(due_date)
            if due_date_end is not None:
                query += ' AND due_date <= ?'
                params.append(due_date_end)
            if description is not None:
                query += ' AND description = ?'
                params.append(description)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Task(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['title', 'description', 'status', 'priority', 'due_date', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tasks SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM tasks WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_tasks_by_status_and_priority(self, status: str, priority: str) -> list[Task]:
        return self.list(
            status=status,
            priority=priority,
        )

    def get_tasks_with_due_date_range(self, start_date: date, end_date: date) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE due_date >= ? AND due_date <= ?", ((start_date, end_date))
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def get_task_count_by_status(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status AS k, COUNT(*) AS n FROM tasks GROUP BY status"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_tasks_with_pagination(self, page: int, page_size: int) -> list[Task]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size)
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def export_tasks_to_json(self) -> str:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY id"
            ).fetchall()
            payload = [
                {k: row[k] for k in row.keys()}
                for row in rows
            ]
            return json.dumps(payload)

    def import_tasks_from_json(self, json_data: str) -> bool:
        try:
            data = json.loads(json_data)
        except (ValueError, TypeError):
            return False
        if not isinstance(data, list):
            return False
        allowed = {"created_at", "description", "due_date", "id", "priority", "status", "title", "updated_at"}
        with self.db.connect() as conn:
            try:
                for item in data:
                    if not isinstance(item, dict):
                        return False
                    values = {k: item[k] for k in item
                               if k in allowed}
                    if not values:
                        return False
                    cols = ", ".join(values)
                    marks = ", ".join("?" for _ in values)
                    conn.execute(
                        "INSERT INTO tasks ({}) VALUES ({})".format(cols, marks),
                        tuple(values.values()),
                    )
                conn.commit()
            except sqlite3.IntegrityError:
                return False
        return True

    def get_tasks_with_priority_and_status_summary(self) -> dict[str, dict[str, int]]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    priority,\n                    status,\n                    COUNT(*) as count\n                FROM tasks\n                GROUP BY priority, status\n            '
            rows = conn.execute(query).fetchall()
            result: dict[str, dict[str, int]] = {}
            for row in rows:
                priority = row[0]
                status = row[1]
                count = row[2]
                if priority not in result:
                    result[priority] = {}
                result[priority][status] = count
            return result

