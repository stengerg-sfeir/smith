"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from author_repository import AuthorRepository
from database import Database
from exceptions import (
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

    def search_posts_by_tag(self, tag_name: str, title_contains: Optional[str] = None) -> List[Post]:
        if not tag_name:
            raise ValidationError('Tag name is required')
        posts = self.post_repo.search_posts(title_contains=title_contains, author_id=None, tag_name=tag_name)
        return posts

    def get_posts_with_tag_counts(self) -> List[dict]:
        """
            Retrieves a list of posts with their associated tag counts.
            Each post entry includes its title, author ID, and a dictionary of tag names mapped to their counts.
            """
        posts_with_tag_counts_and_author_info = self.post_repo.get_posts_with_tag_counts_and_author_info()
        result = []
        for post_data in posts_with_tag_counts_and_author_info:
            post = {
                'id': post_data['id'],
                'title': post_data['title'],
                'author_id': post_data['author_id'],
                'tag_counts': post_data['tag_counts']
            }
            result.append(post)
        return result

    def get_posts_with_author_and_tag_info(self) -> List[dict]:
        """
            Retrieves a list of posts with author and tag information.
            Each post includes title, author ID, and tag names.
            """
        posts_with_author_and_tag_info = self.post_repo.get_posts_with_author_and_tag_info()
        result = []
        for post_data in posts_with_author_and_tag_info:
            post = {
                'id': post_data['id'],
                'title': post_data['title'],
                'author_id': post_data['author_id'],
                'tags': post_data['tags']
            }
            result.append(post)
        return result

    def get_posts_with_tag_counts_and_author_info(self) -> List[dict]:
        """
            Retrieves a list of posts with tag counts and author information.
            Each post includes title, author ID, tag counts, and author details.
            """
        posts_with_tag_counts_and_author_info = self.post_repo.get_posts_with_tag_counts_and_author_info()
        result = []
        for post_data in posts_with_tag_counts_and_author_info:
            post = {
                'id': post_data['id'],
                'title': post_data['title'],
                'author_id': post_data['author_id'],
                'tag_counts': post_data['tag_counts'],
                'author_name': post_data['author_name']
            }
            result.append(post)
        return result

    def get_posts_by_author(self, author_id: int) -> List[dict]:
        """
            Retrieves a list of posts by a specific author.
            Each post includes title, author ID, and tag names.
            """
        posts_with_author_and_tag_info = self.post_repo.get_posts_with_author_and_tag_info()
        result = []
        for post_data in posts_with_author_and_tag_info:
            if post_data['author_id'] == author_id:
                post = {
                    'id': post_data['id'],
                    'title': post_data['title'],
                    'author_id': post_data['author_id'],
                    'tags': post_data['tags']
                }
                result.append(post)
        return result
