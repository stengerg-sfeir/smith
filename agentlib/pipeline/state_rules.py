"""Spec-declared STATE TRANSITIONS: the allowed moves, and the refused ones.

The specification states a state machine outright (prompt 32):

    "An order starts in the `pending` state and can become `confirmed`,
     `shipped` or `cancelled`. A cancelled order cannot be shipped, and a
     shipped order cannot be cancelled."

The shipped code carried only the IDEMPOTENT half of that: each operation
refused to run when the row was ALREADY in its target state
(``if row.status == 'shipped': return False``), which is a repeat guard, not a
transition guard. ``ship_order`` never looked at ``cancelled`` and
``cancel_order`` never looked at ``shipped``, so both forbidden moves the
specification names were performed happily.

Everything here is read from the PROMPT and bound to a designed entity: the
states are the words the specification writes in backticks, and the state
column must be a ``str`` field of that entity named ``status``/``state``.
"""
from __future__ import annotations

import re

from ..naming import _snake

# The states are written in backticks — the specification's own convention for
# a literal value ("starts in the `pending` state").
_STATE_RE = re.compile(r"`([a-z_]+)`")
# "A cancelled order cannot be shipped" — the current state refuses the move.
_FORBID_RE = re.compile(
    r"\b(?:a|an|the)\s+(?P<from>[a-z_]+)\s+[a-z_]+\s+cannot\s+be\s+"
    r"(?P<to>[a-z_]+)\b",
    re.I,
)
# "starts in the `pending` state" — the column's initial value.
_INITIAL_RE = re.compile(r"starts?\s+in\s+the\s+`(?P<state>[a-z_]+)`\s+state", re.I)
# "can become `confirmed`, `shipped` or `cancelled`" — the reachable states.
_BECOME_RE = re.compile(r"can\s+become\s+(?P<list>[^.]*)", re.I)
_STATE_COLUMNS = ("status", "state")


def _state_column(ent):
    """The entity's state column: a ``str`` field named status/state."""
    for f in (ent or {}).get("fields") or []:
        if not isinstance(f, dict):
            continue
        if f.get("name") in _STATE_COLUMNS and f.get("type") in (None, "str"):
            return f["name"]
    return ""


def extract_state_rules(prompt_text, entities_by_class):
    """{class: {"field", "initial", "states", "forbidden": [{"from","to"}]}}.

    Only an entity that (a) the prompt names and (b) carries a real
    ``status``/``state`` column is served, and only transitions between states
    the prompt itself writes in backticks are kept — a refusal naming a word
    the specification never declared as a state is dropped rather than
    rendered against a value that cannot occur.
    """
    text = prompt_text or ""
    if not text:
        return {}
    states = _STATE_RE.findall(text)
    if not states:
        return {}
    initial_match = _INITIAL_RE.search(text)
    initial = initial_match.group("state") if initial_match else ""
    become = _BECOME_RE.search(text)
    reachable = set(_STATE_RE.findall(become.group("list"))) if become else set()
    forbidden = []
    for m in _FORBID_RE.finditer(text):
        frm, to = m.group("from").lower(), m.group("to").lower()
        if frm in states and to in states:
            entry = {"from": frm, "to": to}
            if entry not in forbidden:
                forbidden.append(entry)
    if not forbidden and not initial:
        return {}
    low = text.lower()
    rules = {}
    for cls, ent in (entities_by_class or {}).items():
        field = _state_column(ent)
        if not field:
            continue
        # The entity must be the one the prompt is talking about: its own
        # snake name appears in the sentence.
        if _snake(cls) not in low:
            continue
        rules[cls] = {
            "field": field,
            "initial": initial,
            "states": sorted(set(states) | reachable),
            "forbidden": forbidden,
        }
    return rules
