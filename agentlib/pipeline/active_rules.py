"""Spec-declared "at most one ACTIVE row per resource" rule (C4).

The specification states it outright (prompt 26):

    "A member can borrow multiple books, but a book can have at most one
     active loan."

Nothing enforced it: creating a second loan for a book that already carried
an active one simply inserted another row, so a book could be on loan twice.
The rule is a single SQL existence test on the item's foreign key and its own
"active" marker:

    same resource AND <active flag set>  -- at most one such row may exist

Everything here is read from the PROMPT and bound to a designed entity; the
"active" marker is the design's OWN column (``is_active: bool`` for prompt
26's Loan), never a value invented by the renderer.
"""
from __future__ import annotations

import re

from ..naming import _camel, _snake

# "a book can have at most one active loan"
_AT_MOST_ONE_RE = re.compile(
    r"\b(?:a|an|the)\s+(?P<res>[a-z_]+)\s+can\s+have\s+at\s+most\s+one\s+"
    r"active\s+(?P<item>[a-z_]+)\b",
    re.I,
)
_ACTIVE_HINTS = ("active", "open", "current")


def _singleton(noun):
    """``loans`` -> ``loan``."""
    noun = (noun or "").lower()
    if noun.endswith("ies"):
        return noun[:-3] + "y"
    if noun.endswith("s") and not noun.endswith("ss"):
        return noun[:-1]
    return noun


def _active_field(item_ent):
    """The item's "still active" flag: a bool column.

    ``is_active``/``active`` is what the design names it; a bare bool is
    accepted only when it is the entity's ONLY bool, because a second bool
    ("is_returned") would mean the opposite and makes the predicate
    ambiguous — better to decline than to guard the wrong column.
    """
    bools = [
        f["name"]
        for f in (item_ent or {}).get("fields") or []
        if isinstance(f, dict)
        and isinstance(f.get("name"), str)
        and f.get("type") == "bool"
    ]
    preferred = [
        name for name in bools
        if any(hint in name.lower() for hint in _ACTIVE_HINTS)
    ]
    if preferred:
        return preferred[0]
    return bools[0] if len(bools) == 1 else None


def _resource_fk(item_ent, resource_cls):
    """The item's FK column onto ``resource_cls``, or None."""
    want = _snake(resource_cls) + "_id"
    for f in (item_ent or {}).get("fields") or []:
        if isinstance(f, dict) and f.get("name") == want:
            return want
    return None


def extract_active_rules(prompt_text, entities_by_class):
    """{item_class: {"resource", "fk_field", "flag_field"}}.

    A rule is kept only when the prompt names both the resource and the item,
    the item class is DESIGNED, it carries a foreign key onto that resource
    AND a resolvable active flag. Anything less declines.
    """
    text = prompt_text or ""
    if not text:
        return {}
    rules = {}
    for m in _AT_MOST_ONE_RE.finditer(text):
        res_cls = _camel(_singleton(m.group("res")))
        item_cls = _camel(_singleton(m.group("item")))
        item_ent = (entities_by_class or {}).get(item_cls)
        if not isinstance(item_ent, dict):
            continue
        flag = _active_field(item_ent)
        if not flag:
            continue
        fk_field = _resource_fk(item_ent, res_cls)
        if not fk_field:
            continue
        rules[item_cls] = {
            "resource": _snake(res_cls),
            "fk_field": fk_field,
            "flag_field": flag,
        }
    return rules
