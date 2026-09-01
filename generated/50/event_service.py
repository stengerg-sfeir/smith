"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from event_repository import EventRepository
from exceptions import EventFullException, EventNotFoundException, ValidationError
from models import Event


class EventService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.event_repo = EventRepository(db)

    def add_event(self, title: str, description: Optional[str] = None, max_participants: int = None, current_participants: int = None, start_time: str = None, end_time: str = None) -> bool:
        event = Event(
            title=title,
            description=description,
            max_participants=max_participants,
            current_participants=current_participants,
            start_time=start_time,
            end_time=end_time,
            created_at=datetime.datetime.now().isoformat(),
            updated_at=datetime.datetime.now().isoformat()
        )
        return self.event_repo.create(event)

    def register_event(self, id: int) -> bool:
        try:
            event = self.event_repo.get_event_with_registrations(id)
            if not event:
                raise EventNotFoundException(f'Event with ID {id} not found')
            if event.current_participants >= event.max_participants:
                raise EventFullException(f'Event with ID {id} is full')
            self.event_repo.update(id, {'current_participants': event.current_participants + 1})
            return True
        except EventFullException:
            raise
        except EventNotFoundException:
            raise
        except Exception as e:
            raise ValidationError(f'Failed to register event: {str(e)}')
