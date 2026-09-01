"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from author_repository import AuthorRepository
from database import Database
from models import Author, Post, Tag
from post_repository import PostRepository
from tag_repository import TagRepository


class PostService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.author_repo = AuthorRepository(db)
        self.post_repo = PostRepository(db)
        self.tag_repo = TagRepository(db)

    def add_author(self, name: str, email: str) -> None:
        author = Author(name=name, email=email, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.author_repo.create(author)

    def add_post(self, title: str, content: str, author_id: int) -> None:
        post = Post(title=title, content=content, author_id=author_id, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.post_repo.create(post)

    def list_post(self, author_id: Optional[int] = None) -> List[Post]:
        return self.post_repo.list(author_id=author_id)

    def list_tag(self) -> List[Tag]:
        return self.tag_repo.list()

    def update_post(self, id: int, title: Optional[str] = None, content: Optional[str] = None, author_id: Optional[int] = None) -> None:
        data = {k: v for k, v in {'title': title, 'content': content, 'author_id': author_id}.items() if v is not None}
        return self.post_repo.update(id, data)

    def delete_post(self, id: int) -> None:
        return self.post_repo.delete(id)

    def delete_author(self, id: int) -> None:
        return self.author_repo.delete(id)

    def delete_tag(self, id: int) -> None:
        return self.tag_repo.delete(id)

