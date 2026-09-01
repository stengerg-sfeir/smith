import click
from contact_service import ContactService
from database import Database

DB_PATH = "contacts.db"

@click.group()
def cli():
    """Application root."""

@cli.command('contact-add')
@click.option('--first-name', required=True)
@click.option('--last-name', required=True)
@click.option('--email')
@click.option('--phone')
@click.option('--address')
def contact_add(first_name, last_name, email, phone, address):
    """contact/add"""
    svc = ContactService(Database(DB_PATH))
    result = svc.add_contact(first_name=first_name, last_name=last_name, email=email, phone=phone, address=address)

@cli.command('contact-list')
@click.option('--first-name')
@click.option('--last-name')
@click.option('--email')
@click.option('--phone')
@click.option('--created-at')
@click.option('--created-at-end')
def contact_list(first_name, last_name, email, phone, created_at, created_at_end):
    """contact/list"""
    svc = ContactService(Database(DB_PATH))
    result = svc.list_contact(first_name=first_name, last_name=last_name, email=email, phone=phone, created_at=created_at, created_at_end=created_at_end)

@cli.command('contact-update')
@click.option('--id', type=int, required=True)
@click.option('--first-name')
@click.option('--last-name')
@click.option('--email')
@click.option('--phone')
@click.option('--address')
def contact_update(id, first_name, last_name, email, phone, address):
    """contact/update"""
    svc = ContactService(Database(DB_PATH))
    result = svc.update_contact(id=id, first_name=first_name, last_name=last_name, email=email, phone=phone, address=address)

@cli.command('contact-delete')
@click.option('--id', type=int, required=True)
def contact_delete(id):
    """contact/delete"""
    svc = ContactService(Database(DB_PATH))
    result = svc.delete_contact(id=id)

@cli.command('contact-report')
@click.option('--id', type=int, required=True)
def contact_report(id):
    """contact/report"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contact_report(id=id)

@cli.command('contact-import')
@click.option('--id', type=int, required=True)
def contact_import(id):
    """contact/import"""
    svc = ContactService(Database(DB_PATH))
    result = svc.import_contact(id=id)


if __name__ == "__main__":
    cli()

