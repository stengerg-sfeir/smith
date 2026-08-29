"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Author:
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Post:
    title: str
    content: str
    author_id: int
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class Tag:
    name: str
    created_at: datetime
    updated_at: datetime
    id: Optional[int] = None


@dataclass
class PostTag:
    post_id: int
    tag_id: int


UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {
    "PostTag": [("post_id", "tag_id")],
}

