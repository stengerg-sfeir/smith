"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from models import Note
from note_repository import NoteRepository


class NoteService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.note_repo = NoteRepository(db)

    def create_note(self, title: str, content: str) -> Optional[Note]:
        note = Note(title=title, content=content, created_at=datetime.datetime.now().isoformat())
        return self.note_repo.create(note)

    def list_notes(self, title_filter: Optional[str] = None, created_after: Optional[datetime] = None, created_before: Optional[datetime] = None) -> List[Note]:
        return self.note_repo.list(created_after=created_after, created_before=created_before)

    def update_note(self, note_id: int, title: Optional[str] = None, content: Optional[str] = None) -> Optional[Note]:
        data = {k: v for k, v in {'title': title, 'content': content}.items() if v is not None}
        return self.note_repo.update(note_id, data)

    def delete_note(self, note_id: int) -> bool:
        return self.note_repo.delete(note_id)

    def search_notes(self, query: str) -> List[Note]:
        """
            Search for notes matching the query using the note repository's search_notes method.
            """
        return self.note_repo.search_notes(query)

    def get_notes_by_month(self, year_month: str) -> List[Note]:
        """
            Retrieve notes grouped by the specified year-month (e.g., "2023-01").
            """
        return self.note_repo.get_notes_by_created_date_range(start_date=year_month + '-01', end_date=(datetime.datetime.strptime(year_month + '-01', '%Y-%m') + datetime.timedelta(days=31)).strftime('%Y-%m-%d'))

