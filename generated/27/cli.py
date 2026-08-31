import click
from database import Database
from reservation_service import ReservationService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('reservation-create')
@click.option('--customer-id', type=int, required=True)
@click.option('--room-id', type=int, required=True)
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
@click.option('--status')
def reservation_create(customer_id, room_id, start_date, end_date, status):
    """reservation/create"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.create_reservation(customer_id=customer_id, room_id=room_id, start_date=start_date, end_date=end_date, status=status)

@cli.command('reservation-get_by_id')
@click.option('--id', type=int, required=True)
def reservation_get_by_id(id):
    """reservation/get_by_id"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.get_reservation_by_id(reservation_id=id)

@cli.command('reservation-list_by_customer')
@click.option('--customer-id', type=int, required=True)
def reservation_list_by_customer(customer_id):
    """reservation/list_by_customer"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.list_reservations_by_customer(customer_id=customer_id)

@cli.command('reservation-list_by_room')
@click.option('--room-id', type=int, required=True)
def reservation_list_by_room(room_id):
    """reservation/list_by_room"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.list_reservations_by_room(room_id=room_id)

@cli.command('reservation-overlapping_with_date')
@click.option('--room-id', type=int, required=True)
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def reservation_overlapping_with_date(room_id, start_date, end_date):
    """reservation/overlapping_with_date"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.list_reservations_overlapping_with_date(room_id=room_id, start_date=start_date, end_date=end_date)

@cli.command('reservation-count_by_room')
def reservation_count_by_room():
    """reservation/count_by_room"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.get_reservation_count_by_room()

@cli.command('reservation-by_status')
@click.option('--status', required=True)
def reservation_by_status(status):
    """reservation/by_status"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.get_reservations_by_status(status=status)

@cli.command('reservation-total_by_customer')
def reservation_total_by_customer():
    """reservation/total_by_customer"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.get_total_reservations_by_customer()

@cli.command('reservation-available_for_date_range')
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def reservation_available_for_date_range(start_date, end_date):
    """reservation/available_for_date_range"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.get_available_rooms_for_date_range(start_date=start_date, end_date=end_date)

@cli.command('reservation-overlap_report')
@click.option('--room-id', type=int, required=True)
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
def reservation_overlap_report(room_id, start_date, end_date):
    """reservation/overlap_report"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.get_overlapping_reservations_report(room_id=room_id, start_date=start_date, end_date=end_date)

@cli.command('reservation-validate')
@click.option('--reservation', required=True)
def reservation_validate(reservation):
    """reservation/validate"""
    svc = ReservationService(Database(DB_PATH))
    result = svc.validate_reservation_overlap(reservation=reservation)


if __name__ == "__main__":
    cli()

