import click
from database import Database
from notification_service import NotificationService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('notification-confirm')
@click.option('--id', type=int, required=True)
def notification_confirm(id):
    """notification/confirm"""
    svc = NotificationService(Database(DB_PATH))
    result = svc.confirm_notification(id=id)

@cli.command('notification-list')
@click.option('--order-id')
@click.option('--sent-at')
@click.option('--sent-at-end')
def notification_list(order_id, sent_at, sent_at_end):
    """notification/list"""
    svc = NotificationService(Database(DB_PATH))
    result = svc.list_notification(order_id=order_id, sent_at=sent_at, sent_at_end=sent_at_end)


if __name__ == "__main__":
    cli()

