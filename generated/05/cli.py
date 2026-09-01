import click
from contact_service import ContactService
from database import Database

DB_PATH = "contacts.db"

@click.group()
def cli():
    """Application root."""

@cli.command('contact-add')
@click.option('--name', required=True)
@click.option('--email')
@click.option('--phone')
def contact_add(name, email, phone):
    """contact/add"""
    svc = ContactService(Database(DB_PATH))
    result = svc.add_contact(name=name, email=email, phone=phone)

@cli.command('contact-list')
@click.option('--name')
@click.option('--email')
@click.option('--phone')
def contact_list(name, email, phone):
    """contact/list"""
    svc = ContactService(Database(DB_PATH))
    result = svc.list_contact(name=name, email=email, phone=phone)

@cli.command('contact-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--email')
@click.option('--phone')
def contact_update(id, name, email, phone):
    """contact/update"""
    svc = ContactService(Database(DB_PATH))
    result = svc.update_contact(id=id, name=name, email=email, phone=phone)

@cli.command('contact-delete')
@click.option('--id', type=int, required=True)
def contact_delete(id):
    """contact/delete"""
    svc = ContactService(Database(DB_PATH))
    result = svc.delete_contact(id=id)


if __name__ == "__main__":
    cli()

