"""Recipe metadata types used by per-file RECIPES declaration.

A recipe is a callable that is tried in priority order by the kernel
dispatcher. It returns either a generated body string (when it applies) or
None (when it does not), preserving the "first match wins" semantics of the
former inline if/elif chains in agent.py.
"""
from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass(frozen=True)
class Recipe:
    """A single deterministic generation recipe.

    `name` is a stable identifier used for discovery / diagnostics.
    `priority` controls ordering in the dispatcher (lower runs first).
    `fn` is the recipe callable; its signature is recipe-specific but must
    return `Optional[List[str]]` (the generated body lines) or None.
    """

    name: str
    priority: int
    fn: Callable[..., Optional[List[str]]]


# Repository recipe callbacks receive this expanded context to avoid forcing
# every recipe to re-derive shared helpers. Kept as a plain dict-like to stay
# dependency-free; individual recipe modules read only the keys they need.
