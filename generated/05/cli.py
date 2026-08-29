import click
from contact_service import ContactService
from database import Database

DB_PATH = "contacts.db"

@click.group()
def cli():
    """Application root."""

@cli.command('contact-create')
@click.option('--name', required=True)
@click.option('--email')
@click.option('--phone')
def contact_create(name, email, phone):
    """contact/create"""
    svc = ContactService(Database(DB_PATH))
    result = svc.create_contact(name=name, email=email, phone=phone)

@cli.command('contact-list')
def contact_list():
    """contact/list"""
    svc = ContactService(Database(DB_PATH))
    result = svc.list_contacts()

@cli.command('contact-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--email')
@click.option('--phone')
def contact_update(id, name, email, phone):
    """contact/update"""
    svc = ContactService(Database(DB_PATH))
    result = svc.update_contact(contact_id=id, name=name, email=email, phone=phone)

@cli.command('contact-delete')
@click.option('--id', type=int, required=True)
def contact_delete(id):
    """contact/delete"""
    svc = ContactService(Database(DB_PATH))
    result = svc.delete_contact(contact_id=id)

@cli.command('contact-search')
@click.option('--query', required=True)
@click.option('--case-sensitive', is_flag=True, default=False)
def contact_search(query, case_sensitive):
    """contact/search"""
    svc = ContactService(Database(DB_PATH))
    result = svc.search_contacts(query=query, case_sensitive=case_sensitive)

@cli.command('find_by_email-by_email')
@click.option('--email', required=True)
def find_by_email_by_email(email):
    """contact/find_by_email/by_email"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contact_by_email(email=email)

@cli.command('find_by_phone-by_phone')
@click.option('--phone', required=True)
def find_by_phone_by_phone(phone):
    """contact/find_by_phone/by_phone"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contact_by_phone(phone=phone)

@cli.command('filter-by_domain')
@click.option('--domain', required=True)
def filter_by_domain(domain):
    """contact/filter/by_domain"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_with_email_domain(domain=domain)

@cli.command('filter-by_prefix')
@click.option('--prefix', required=True)
def filter_by_prefix(prefix):
    """contact/filter/by_prefix"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_by_name_prefix(prefix=prefix)

@cli.command('stats-most_emails')
def stats_most_emails():
    """contact/stats/most_emails"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contact_with_most_emails()

@cli.command('stats-most_phones')
def stats_most_phones():
    """contact/stats/most_phones"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contact_with_most_phones()

@cli.command('filter-no_email')
def filter_no_email():
    """contact/filter/no_email"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_with_no_email()

@cli.command('filter-no_phone')
def filter_no_phone():
    """contact/filter/no_phone"""
    svc = ContactService(Database(DB_PATH))
    result = svc.get_contacts_with_no_phone()


if __name__ == "__main__":
    cli()

