import click
from database import Database
from reservation_service import ReservationService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('reservation-add')
@click.option('--customer-id', type=int, required=True)
@click.option('--room-id', type=int, required=True)
@click.option('--status', required=True)
def reservation_add(customer_id, room_id, status):
    """reservation/add"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.add_reservation(customer_id=customer_id, room_id=room_id, status=status)

@cli.command('reservation-list')
@click.option('--customer-id')
@click.option('--room-id')
@click.option('--start-date')
@click.option('--end-date')
@click.option('--status')
def reservation_list(customer_id, room_id, start_date, end_date, status):
    """reservation/list"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.list_reservation(customer_id=customer_id, room_id=room_id, start_date=start_date, end_date=end_date, status=status)

@cli.command('reservation-update')
@click.option('--id', type=int, required=True)
@click.option('--customer-id', type=int)
@click.option('--room-id', type=int)
@click.option('--status')
def reservation_update(id, customer_id, room_id, status):
    """reservation/update"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.update_reservation(id=id, customer_id=customer_id, room_id=room_id, status=status)

@cli.command('reservation-delete')
@click.option('--id', type=int, required=True)
def reservation_delete(id):
    """reservation/delete"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.delete_reservation(id=id)

@cli.command('reservation-check')
@click.option('--id', type=int, required=True)
def reservation_check(id):
    """reservation/check"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.check_reservation(id=id)

@cli.command('customer-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_add(name, email, phone):
    """customer/add"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email, phone=phone)

@cli.command('room-add')
@click.option('--room-number', required=True)
@click.option('--floor', type=int, required=True)
@click.option('--capacity', type=int, required=True)
@click.option('--room-type', required=True)
def room_add(room_number, floor, capacity, room_type):
    """room/add"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.add_room(room_number=room_number, floor=floor, capacity=capacity, room_type=room_type)


if __name__ == "__main__":
    cli()

