import click
from database import Database
from post_service import PostService

DB_PATH = "blog.db"

@click.group()
def cli():
    """Application root."""

@cli.command('author-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
def author_add(name, email):
    """author/add"""
    svc = PostService(Database(DB_PATH))
    result = svc.add_author(name=name, email=email)

@cli.command('post-add')
@click.option('--title', required=True)
@click.option('--content', required=True)
@click.option('--author-id', type=int, required=True)
def post_add(title, content, author_id):
    """post/add"""
    svc = PostService(Database(DB_PATH))
    result = svc.add_post(title=title, content=content, author_id=author_id)

@cli.command('post-list')
@click.option('--author-id')
def post_list(author_id):
    """post/list"""
    svc = PostService(Database(DB_PATH))
    result = svc.list_post(author_id=author_id)

@cli.command('tag-list')
def tag_list():
    """tag/list"""
    svc = PostService(Database(DB_PATH))
    result = svc.list_tag()

@cli.command('post-update')
@click.option('--id', type=int, required=True)
@click.option('--title')
@click.option('--content')
@click.option('--author-id', type=int)
def post_update(id, title, content, author_id):
    """post/update"""
    svc = PostService(Database(DB_PATH))
    result = svc.update_post(id=id, title=title, content=content, author_id=author_id)

@cli.command('post-delete')
@click.option('--id', type=int, required=True)
def post_delete(id):
    """post/delete"""
    svc = PostService(Database(DB_PATH))
    result = svc.delete_post(id=id)

@cli.command('author-delete')
@click.option('--id', type=int, required=True)
def author_delete(id):
    """author/delete"""
    svc = PostService(Database(DB_PATH))
    result = svc.delete_author(id=id)

@cli.command('tag-delete')
@click.option('--id', type=int, required=True)
def tag_delete(id):
    """tag/delete"""
    svc = PostService(Database(DB_PATH))
    result = svc.delete_tag(id=id)


if __name__ == "__main__":
    cli()

