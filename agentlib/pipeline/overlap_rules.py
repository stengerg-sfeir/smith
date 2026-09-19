"""Spec-declared OVERLAP guards: one resource, no two overlapping periods.

The specification states the uniqueness of a time range per resource (prompt
27):

    "A room cannot have two overlapping reservations. ... reject reservations
     that overlap an existing reservation."

Nothing enforced it: the repository's ``create`` inserted the row
unconditionally, so two reservations for the same room over the same nights
both persisted. The rule is a plain SQL existence test on the item's two date
columns and its foreign key to the resource:

    same resource AND existing.start < new.end AND existing.end > new.start

Everything here is read from the PROMPT and bound to a designed entity: the
item class must be named by the prompt, carry TWO date/datetime columns and a
foreign key to the resource the prompt names.
"""
from __future__ import annotations

import re

from ..naming import _camel, _snake

# "A room cannot have two overlapping reservations."
_OVERLAP_RE = re.compile(
    r"\b(?:a|an|the)\s+(?P<res>[a-z_]+)\s+cannot\s+have\s+two\s+overlapping\s+"
    r"(?P<item>[a-z_]+)\b",
    re.I,
)
# The pair of columns that defines the period, most specific first.
_START_HINTS = ("start", "begin", "check_in", "from", "arrival")
_END_HINTS = ("end", "finish", "check_out", "to", "departure")
_DATE_TYPES = ("date", "datetime")


def _singleton(noun):
    """``reservations`` -> ``reservation`` (the class name is singular)."""
    noun = (noun or "").lower()
    if noun.endswith("ies"):
        return noun[:-3] + "y"
    if noun.endswith("s") and not noun.endswith("ss"):
        return noun[:-1]
    return noun


def _date_fields(ent):
    """The entity's date/datetime columns, in declaration order."""
    return [
        f["name"]
        for f in (ent or {}).get("fields") or []
        if isinstance(f, dict)
        and isinstance(f.get("name"), str)
        and f.get("type") in _DATE_TYPES
    ]


def _period_pair(fields):
    """(start, end) among ``fields``, or None.

    A spec that says "start date and end date" names its columns; failing
    that, exactly two date columns ARE the period (there is no other reading
    of a pair of dates on a booked resource). Any other count is ambiguous and
    declines — a wrong period column would silently check the wrong thing.
    """
    start = next(
        (f for h in _START_HINTS for f in fields if h in f), None
    )
    end = next(
        (f for h in _END_HINTS for f in fields if h in f), None
    )
    if start and end and start != end:
        return start, end
    if len(fields) == 2:
        return fields[0], fields[1]
    return None


def _resource_fk(item_ent, resource_cls):
    """The item's FK column onto ``resource_cls``, or None."""
    want = _snake(resource_cls) + "_id"
    for f in (item_ent or {}).get("fields") or []:
        if isinstance(f, dict) and f.get("name") == want:
            return want
    return None


def extract_overlap_rules(prompt_text, entities_by_class):
    """{item_class: {"resource", "fk_field", "start_field", "end_field"}}.

    A rule is kept only when the prompt names the resource and the item, the
    item class is DESIGNED, and the item carries a resolvable period pair plus
    a foreign key onto that resource. Anything less declines — an overlap
    guard built on a guessed column would refuse valid reservations.
    """
    text = prompt_text or ""
    if not text:
        return {}
    rules = {}
    for m in _OVERLAP_RE.finditer(text):
        res_cls = _camel(_singleton(m.group("res")))
        item_cls = _camel(_singleton(m.group("item")))
        item_ent = (entities_by_class or {}).get(item_cls)
        if not isinstance(item_ent, dict):
            continue
        pair = _period_pair(_date_fields(item_ent))
        if pair is None:
            continue
        fk_field = _resource_fk(item_ent, res_cls)
        if not fk_field:
            continue
        rules[item_cls] = {
            "resource": _snake(res_cls),
            "fk_field": fk_field,
            "start_field": pair[0],
            "end_field": pair[1],
        }
    return rules
