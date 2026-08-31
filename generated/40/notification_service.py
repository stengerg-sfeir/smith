"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from database import Database
from exceptions import NotFoundError
from notification_repository import NotificationRepository


class NotificationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.notification_repo = NotificationRepository(db)

    def confirm_notification(self, id: int) -> Optional[Dict[str, str]]:
        notification = self.notification_repo.get_by_id(id)
        if not notification:
            raise NotFoundError(f'Notification with id {id} not found')
        if notification.sent_at:
            return None
        notification.sent_at = datetime.datetime.now()
        self.notification_repo.update(id, {'sent_at': notification.sent_at.isoformat()})
        return {'id': notification.id, 'message': notification.message, 'order_id': notification.order_id, 'sent_at': notification.sent_at.isoformat()}

    def list_notification(self, order_id: str, sent_at: str, sent_at_end: str) -> List[Dict[str, str]]:
        return self.notification_repo.list(order_id=order_id, sent_at=sent_at, sent_at_end=sent_at_end)

