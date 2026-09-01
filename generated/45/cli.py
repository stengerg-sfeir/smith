import click
from booking_service import BookingService
from database import Database

DB_PATH = "hotel.db"

@click.group()
def cli():
    """Application root."""

@cli.command('room-add')
@click.option('--room-number', required=True)
@click.option('--floor', type=int, required=True)
@click.option('--room-type', required=True)
@click.option('--price-per-night', required=True)
def room_add(room_number, floor, room_type, price_per_night):
    """room/add"""
    svc = BookingService(Database(DB_PATH))
    result = svc.add_room(room_number=room_number, floor=floor, room_type=room_type, price_per_night=price_per_night)

@cli.command('room-list')
def room_list():
    """room/list"""
    svc = BookingService(Database(DB_PATH))
    result = svc.list_room()

@cli.command('guest-add')
@click.option('--first-name', required=True)
@click.option('--last-name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def guest_add(first_name, last_name, email, phone):
    """guest/add"""
    svc = BookingService(Database(DB_PATH))
    result = svc.add_guest(first_name=first_name, last_name=last_name, email=email, phone=phone)

@cli.command('guest-book')
@click.option('--id', type=int, required=True)
def guest_book(id):
    """guest/book"""
    svc = BookingService(Database(DB_PATH))
    result = svc.book_guest(id=id)

@cli.command('booking-list')
@click.option('--check-in-date')
@click.option('--check-out-date')
def booking_list(check_in_date, check_out_date):
    """booking/list"""
    svc = BookingService(Database(DB_PATH))
    result = svc.list_booking(check_in_date=check_in_date, check_out_date=check_out_date)


if __name__ == "__main__":
    cli()

