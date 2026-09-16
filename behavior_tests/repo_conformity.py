"""Prompt -> repository surface conformity: one method per capability.

A repository that ships two methods for one capability holds a second source of
truth for a single table, free to diverge. Measured on the tree before the
pruners: expenses' repository-level ``update_category`` wrote all four columns
unconditionally where the CRUD ``update(id, data)`` is PARTIAL, so a caller of
the duplicate nulled every field it omitted; library's
``list_authors_with_books`` shipped a ``SELECT`` with no ``FROM`` and filtered
on a column its own table does not have; ``get_overdue_loans_count`` counted
every loan where the canonical ``get_overdue_loans`` filtered the overdue ones.

This module is the regression test for the pruners in
``agentlib.generation.repo_render`` (R1/R2/R3c/R3e) and
``agentlib.pipeline.manifest`` (R3g). It reads the SHIPPED repository sources
and asserts, per method, that

* it is not a re-spelling of the deterministic CRUD surface
  (``add_member`` beside ``create``, ``list_expenses`` beside ``list``,
  ``get_category_by_id`` beside ``get_by_id``);
* it is not a sibling plus a scalar qualifier
  (``get_overdue_loans_count`` beside ``get_overdue_loans``);
* every content word of its name appears in the prompt that asked for the
  project at all — the prompt, never the design, is the ownership test, so a
  specification that asks for an aggregation query keeps it even though the
  rendered service realizes it inline.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from agentlib.generation.repo_render import (
    _CRUD_BASE_METHODS,
    _capability_tokens,
    _crud_shadow_target,
    _qualifier_extension_of,
)

# The names ``_render_repository_file`` renders deterministically; a designed
# custom may never duplicate one of them.
_DETERMINISTIC = set(_CRUD_BASE_METHODS) | {"find_by_id"}


def prompt_tokens(prompt_text: str) -> set[str]:
    """Lowercase alphanumeric tokens of a prompt, plural-stemmed."""
    out: set[str] = set()
    for raw in re.split(r"[^a-z0-9]+", (prompt_text or "").lower()):
        if not raw:
            continue
        out.add(raw)
        if raw.endswith("ies") and len(raw) > 3:
            out.add(raw[:-3] + "y")
        elif raw.endswith("s") and len(raw) > 1:
            out.add(raw[:-1])
    return out


def _method_names(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    return [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name != "__init__"
    ]


def repository_conformity_violations(prompt_text: str,
                                     project_dir: Path | str) -> list[str]:
    """Every duplicate / unasked repository method of one generated project."""
    stems = prompt_tokens(prompt_text)
    violations: list[str] = []
    # Recursive: a project may lay its repositories out inside a package
    # (``expense_tracker/repositories/category_repository.py``), and a
    # non-recursive glob silently skipped every one of them — the check
    # reported PASS by finding nothing to look at.
    for path in sorted(Path(project_dir).rglob("*_repository.py")):
        ent_snake = path.stem[: -len("_repository")]
        model = "".join(part.capitalize() for part in ent_snake.split("_"))
        # A PRIVATE helper is implementation detail, not a capability. The
        # ownership test asks "did the prompt request this capability?", which
        # is a question about the repository's public surface — a row mapper
        # named ``_row_to_category`` was being faulted for naming ``row``.
        names = [n for n in _method_names(path) if not n.startswith("_")]
        for name in names:
            shadow = _crud_shadow_target(name, ent_snake, model)
            if shadow:
                violations.append(
                    "%s.%s re-spells the deterministic %s()"
                    % (path.name, name, shadow)
                )
                continue
            for other in names:
                if other != name and _qualifier_extension_of(name, other):
                    violations.append(
                        "%s.%s merely extends %s() with a scalar qualifier"
                        % (path.name, name, other)
                    )
                    break
            if name in _DETERMINISTIC:
                continue
            _, content = _capability_tokens(name, ent_snake, model)
            # The ownership test asks whether the PROMPT requested the
            # CAPABILITY, so it fires only when the name shares NOTHING with
            # the prompt. Requiring EVERY word fired on a faithful name that
            # merely adds a modifier — ``find_potential_recurring`` for a
            # specification that asks for recurring detection — while the
            # near-duplicate defects this exists to catch (a sibling plus a
            # scalar qualifier, a re-spelling of the CRUD surface) are caught
            # by the two checks above.
            if content and not (set(content) & stems):
                violations.append(
                    "%s.%s names %s, which appear nowhere in the prompt"
                    % (path.name, name, ", ".join(sorted(set(content))))
                )
        # ONE capability, two methods: a repository that keeps two spellings of
        # a single duty (AuthorRepository's ``find_books_by_author`` beside
        # ``list_authors_with_books``, both reading as the capability
        # {'books'}) holds two implementations of one query. Compared on the
        # content tokens alone, so the verb a method happens to use is not the
        # test; empty content (the entity-wide ``search_books``) is never a
        # duplicate, since it names no object word to share.
        by_capability: dict[frozenset, list[str]] = {}
        for name in names:
            if name in _DETERMINISTIC:
                continue
            _, content = _capability_tokens(name, ent_snake, model)
            if content:
                by_capability.setdefault(frozenset(content), []).append(name)
        for content, group in sorted(by_capability.items()):
            if len(group) > 1:
                violations.append(
                    "%s ships %s — one capability (%s), two implementations"
                    % (path.name, " and ".join(sorted(group)),
                       ", ".join(sorted(content)))
                )
    return violations
