import click
from database import Database
from post_service import PostService

DB_PATH = "blog.db"

@click.group()
def cli():
    """Application root."""

@cli.command('author-list')
@click.option('--author-id', type=int)
def author_list(author_id):
    """author/list"""
    svc = PostService(Database(DB_PATH))
    result = svc.get_posts_by_author(author_id=author_id)

@cli.command('post-read')
@click.option('--id', type=int, required=True)
def post_read(id):
    """post/read"""
    svc = PostService(Database(DB_PATH))
    result = svc.get_post_by_id(post_id=id)

@cli.command('post-update')
@click.option('--id', type=int, required=True)
@click.option('--title')
@click.option('--content')
@click.option('--tags')
def post_update(id, title, content, tags):
    """post/update"""
    svc = PostService(Database(DB_PATH))
    result = svc.update_post(post_id=id, title=title, content=content, tags=tags)

@cli.command('post-delete')
@click.option('--id', type=int, required=True)
def post_delete(id):
    """post/delete"""
    svc = PostService(Database(DB_PATH))
    result = svc.delete_post(post_id=id)

@cli.command('post-search')
@click.option('--title')
@click.option('--author-id', type=int)
@click.option('--tag')
def post_search(title, author_id, tag):
    """post/search"""
    svc = PostService(Database(DB_PATH))
    result = svc.search_posts(title_contains=title, author_id=author_id, tag_name=tag)

@cli.command('post-info')
def post_info():
    """post/info"""
    svc = PostService(Database(DB_PATH))
    result = svc.get_posts_with_tag_counts_and_author_info()


if __name__ == "__main__":
    cli()

