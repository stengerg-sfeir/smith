"""Service layer."""
from __future__ import annotations

from typing import Optional

from database import Database
from loan_repository import LoanRepository
from models import Member


class LoanService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.loan_repo = LoanRepository(db)

    def add_member(self, name: str, email: str, phone: Optional[str] = None) -> bool:
        member = Member(name=name, email=email, phone=phone)
        return self.member_repo.create(member)

