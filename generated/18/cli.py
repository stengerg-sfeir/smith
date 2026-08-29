import click
from contact_service import ContactService
from database import Database

DB_PATH = "contacts.db"

@click.group()
def cli():
    """Application root."""

@cli.command('create-add')
@click.option('--first-name', required=True)
@click.option('--last-name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
@click.option('--address')
def create_add(first_name, last_name, email, phone, address):
    """contact/create/add"""
    svc = ContactService(Database(DB_PATH))
    result = svc.add_contact(first_name=first_name, last_name=last_name, email=email, phone=phone, address=address)

@cli.command('read-count_by_last_name')
def read_count_by_last_name():
    """contact/read/count_by_last_name"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contact_count_by_last_name()

@cli.command('read-by_email_domain')
@click.option('--domain', required=True)
def read_by_email_domain(domain):
    """contact/read/by_email_domain"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_by_email_domain(domain=domain)

@cli.command('read-by_last_name_prefix')
@click.option('--prefix', required=True)
def read_by_last_name_prefix(prefix):
    """contact/read/by_last_name_prefix"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_by_last_name_prefix(prefix=prefix)

@cli.command('read-invalid_emails')
def read_invalid_emails():
    """contact/read/invalid_emails"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_with_invalid_email_format()

@cli.command('read-phone_and_email')
def read_phone_and_email():
    """contact/read/phone_and_email"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_with_phone_and_email()

@cli.command('read-total_count')
def read_total_count():
    """contact/read/total_count"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_total_contact_count()

@cli.command('contact-export')
@click.option('--filename', required=True)
def contact_export(filename):
    """contact/export"""
    svc = ContactService(Database(DB_PATH))
    result = svc.export_to_csv(filename=filename)

@cli.command('contact-import')
@click.option('--filename', required=True)
def contact_import(filename):
    """contact/import"""
    svc = ContactService(Database(DB_PATH))
    result = svc.import_from_csv(filename=filename)


if __name__ == "__main__":
    cli()

