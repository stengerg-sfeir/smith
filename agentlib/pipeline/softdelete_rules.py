"""Spec-declared SOFT DELETE rule.

Prompt 14 states it outright:

    "Deleting a project must be implemented as a soft delete: the project
     remains in the database but is no longer returned by normal listing
     operations."

The design is half right — it carries the ``deleted_at`` column and even
writes it on insert — but the delete path issues a real ``DELETE`` and the
listing never looks at the column, so the row is gone as far as anyone can
tell.

The rule is read from the PROMPT and bound to the design's OWN column: only an
entity that actually has a ``deleted*`` field qualifies, so a specification
asking for a soft delete on an entity that was never designed with such a
column declines rather than inventing one.
"""

from __future__ import annotations

import re

_SOFT_DELETE_RE = re.compile(
    r"soft[\s-]?delete|softly\s+deleted|"
    r"remains?\s+in\s+the\s+database|"
    r"still\s+(?:be\s+)?(?:present\s+)?in\s+the\s+database|"
    r"no\s+longer\s+returned\s+by\s+normal\s+listing",
    re.I,
)
_DELETED_HINTS = ("deleted", "removed", "archived")


def _deleted_field(entity_design):
    """The entity's own 'this row is deleted' column, or None.

    A TIMESTAMP column (``deleted_at``) is preferred over a boolean flag
    because it also records when; either is accepted, since the listing filter
    is the same ``IS NULL``/``= 0`` test either way.
    """
    fields = [
        f for f in (entity_design or {}).get("fields") or []
        if isinstance(f, dict) and isinstance(f.get("name"), str)
    ]
    hinted = [
        f for f in fields
        if any(hint in f["name"].lower() for hint in _DELETED_HINTS)
    ]
    if not hinted:
        return None
    timed = [f for f in hinted if f.get("type") in ("datetime", "date", "str")]
    return (timed or hinted)[0]


def extract_soft_delete_rules(prompt_text, entities_by_class):
    """``{entity_class: {"column": name, "is_flag": bool}}``.

    Empty when the specification never asks for a soft delete, or when no
    designed entity carries a deletion marker to write.
    """
    text = prompt_text or ""
    if not text or not _SOFT_DELETE_RE.search(text):
        return {}
    rules = {}
    for cls, entity in (entities_by_class or {}).items():
        field = _deleted_field(entity)
        if field is None:
            continue
        rules[cls] = {
            "column": field["name"],
            "is_flag": field.get("type") == "bool",
        }
    return rules
