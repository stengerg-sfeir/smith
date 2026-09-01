import click
from appointment_service import AppointmentService
from database import Database

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('appointment-add')
@click.option('--title')
@click.option('--description')
def appointment_add(title, description):
    """appointment/add"""
    svc = AppointmentService(Database(DB_PATH))
    result = svc.add_appointment(title=title, description=description)

@cli.command('appointment-ensure')
@click.option('--id', type=int, required=True)
def appointment_ensure(id):
    """appointment/ensure"""
    svc = AppointmentService(Database(DB_PATH))
    result = svc.ensure_appointment(id=id)


if __name__ == "__main__":
    cli()

