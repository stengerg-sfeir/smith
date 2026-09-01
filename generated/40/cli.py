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

@cli.command('order-add')
@click.option('--customer-id', type=int, required=True)
@click.option('--status', required=True)
@click.option('--total-amount', required=True)
def order_add(customer_id, status, total_amount):
    """order/add"""
    svc = NotificationService(Database(DB_PATH))
    result = svc.add_order(customer_id=customer_id, status=status, total_amount=total_amount)


if __name__ == "__main__":
    cli()

