"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from exceptions import (
    DuplicateNoteError,
    NotFoundError,
    ValidationException,
)
from models import Note
from note_repository import NoteRepository


class NoteService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.note_repo = NoteRepository(db)

    def add(self, title: str, content: str) -> None:
        """Add a new note with the given title and content."""
        try:
            note = Note(content=content, created_at=datetime.datetime.now(), title=title)
            self.note_repo.create(note)
        except Exception as e:
            if isinstance(e, DuplicateNoteError):
                raise DuplicateNoteError(f"Note with title '{title}' already exists.")
            raise ValidationException(f'Failed to create note: {str(e)}')

    def list(self, title: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None) -> List[Note]:
        """List notes with optional filtering by title, start date, or end date."""
        notes: List[Note] = []
        if title:
            notes.extend(self.note_repo.search_notes_by_content(title))
        if start_date and end_date:
            try:
                start_date_obj = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                end_date_obj = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                notes.extend(self.note_repo.get_notes_by_created_date_range(start_date_obj, end_date_obj))
            except ValueError:
                raise ValidationException('Invalid date format. Use YYYY-MM-DD.')
        if not notes:
            notes = self.note_repo.get_all()
        return notes

    def update(self, note_id: int, new_title: Optional[str]=None, new_content: Optional[str]=None) -> None:
        """Update a note's title and/or content by note_id."""
        if not new_title and (not new_content):
            raise ValidationException('At least one field (title or content) must be provided for update.')
        try:
            note = self.note_repo.get_by_id(note_id)
            if not note:
                raise NotFoundError(f'Note with ID {note_id} not found.')
            update_data = {}
            if new_title is not None:
                update_data['title'] = new_title
            if new_content is not None:
                update_data['content'] = new_content
            self.note_repo.update(note_id, update_data)
        except Exception as e:
            if isinstance(e, NotFoundError):
                raise NotFoundError(f'Note with ID {note_id} not found.')
            raise ValidationException(f'Failed to update note: {str(e)}')

    def delete(self, note_id: int) -> None:
        """Delete a note by its ID."""
        try:
            note = self.note_repo.get_by_id(note_id)
            if not note:
                raise NotFoundError(f'Note with ID {note_id} not found.')
            self.note_repo.delete(note_id)
        except Exception as e:
            if isinstance(e, NotFoundError):
                raise NotFoundError(f'Note with ID {note_id} not found.')
            raise ValidationException(f'Failed to delete note: {str(e)}')

