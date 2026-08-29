"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from author_repository import AuthorRepository
from database import Database
from exceptions import (
    NotFoundError,
    ValidationError,
)
from models import Post
from post_repository import PostRepository
from tag_repository import TagRepository


class PostService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.author_repo = AuthorRepository(db)
        self.post_repo = PostRepository(db)
        self.tag_repo = TagRepository(db)

    def create_post(self, author_id: int, title: str, content: str, tags: List[str]) -> Post:
        post = Post(author_id=author_id, title=title, content=content, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.post_repo.create(post)

    def get_post_by_id(self, post_id: int) -> Optional[Post]:
        return self.post_repo.get_by_id(post_id)

    def update_post(self, post_id: int, title: Optional[str] = None, content: Optional[str] = None, tags: Optional[List[str]] = None) -> Post:
        data = {k: v for k, v in {'title': title, 'content': content}.items() if v is not None}
        return self.post_repo.update(post_id, data)

    def delete_post(self, post_id: int) -> bool:
        return self.post_repo.delete(post_id)

    def search_posts_by_tag(self, tag_name: str, title_contains: Optional[str]=None) -> List[Post]:
        """
            Search posts by tag name and optionally by title content.
        
            Args:
                tag_name: The name of the tag to search for.
                title_contains: Optional filter to match titles containing this string.
            
            Returns:
                List of posts that match the tag and optional title filter.
            """
        if not tag_name or not tag_name.strip():
            raise ValidationError('Tag name cannot be empty.')
        tag = self.tag_repo.get_tag_by_name(tag_name.strip())
        if not tag:
            raise NotFoundError(f"Tag '{tag_name}' not found.")
        posts = self.post_repo.search_posts_by_tag(tag_name, title_contains, tag.name)
        return posts

    def get_posts_with_tag_counts(self) -> List[dict]:
        """Retrieve posts with their tag counts, including tag names and counts."""
        posts_with_counts = self.post_repo.get_posts_with_tag_counts()
        return posts_with_counts

    def get_posts_by_author(self, author_id: int) -> List[Post]:
        return self.post_repo.get_posts_by_author(author_id)

    def get_post_tag_counts(self) -> dict[str, int]:
        return self.post_repo.get_post_tag_counts()

    def get_posts_with_author_and_tag_info(self) -> List[dict]:
        """
            Retrieves all posts with their author information and tag information.
            Each post entry includes:
            - post details (id, title, content, created_at, updated_at)
            - author name and email
            - list of tag names associated with the post
            """
        posts_with_info = self.post_repo.get_posts_with_author_and_tag_info()
        result = []
        for post_data in posts_with_info:
            post_id = post_data['post_id']
            post_title = post_data['title']
            post_content = post_data['content']
            post_created_at = post_data['created_at']
            post_updated_at = post_data['updated_at']
            author_id = post_data['author_id']
            author_name = post_data['author_name']
            author_email = post_data['author_email']
            tag_names = post_data['tags']
            result.append({'id': post_id, 'title': post_title, 'content': post_content, 'created_at': post_created_at, 'updated_at': post_updated_at, 'author': {'id': author_id, 'name': author_name, 'email': author_email}, 'tags': tag_names})
        return result

    def get_posts_with_tag_counts_and_author_info(self) -> List[dict]:
        """
            Retrieves a list of posts with their tag counts and author information.
            Each post entry includes:
            - post_id, title, content
            - author_name, author_id
            - tag_counts: dictionary of tag names to counts
            """
        posts_with_info = self.post_repo.get_posts_with_tag_counts_and_author_info()
        result = []
        for post_data in posts_with_info:
            post_id = post_data['post_id']
            title = post_data['title']
            content = post_data['content']
            author_id = post_data['author_id']
            tag_counts = post_data['tag_counts']
            author = self.author_repo.get_by_id(author_id)
            author_name = author.name if author else 'Unknown'
            result.append({'post_id': post_id, 'title': title, 'content': content, 'author_name': author_name, 'author_id': author_id, 'tag_counts': tag_counts})
        return result

    def search_posts(self, title_contains: str, author_id: Optional[int]=None, tag_name: Optional[str]=None) -> List[Post]:
        """
            Search posts by title, author, and/or tag.
        
            Args:
                title_contains: Search for posts where title contains this string.
                author_id: Filter posts by author ID (optional).
                tag_name: Filter posts by tag name (optional).
        
            Returns:
                List of matching Post objects.
            """
        posts = self.post_repo.search_posts(title_contains=title_contains, author_id=author_id, tag_name=tag_name)
        if tag_name is not None:
            tag_posts = self.post_repo.get_posts_by_tag(tag_name)
            posts = [post for post in posts if post.id in [p.id for p in tag_posts]]
        return posts

