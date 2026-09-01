"""Service layer."""
from __future__ import annotations

import datetime

from appointment_repository import AppointmentRepository
from database import Database
from models import Appointment


class AppointmentService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.appointment_repo = AppointmentRepository(db)

    def add_appointment(self, title: str, description: str) -> bool:
        appointment = Appointment(title=title, description=description, end_time=datetime.datetime.now().isoformat(), start_time=datetime.datetime.now().isoformat())
        return self.appointment_repo.create(appointment)

    def ensure_appointment(self, id: int) -> bool:
        """Check if an appointment with the given ID exists in the repository."""
        appointment = self.appointment_repo.get_by_id(id)
        return appointment is not None

