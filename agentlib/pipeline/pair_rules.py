"""Spec-declared INPUT pairs: two timestamps the prompt COMPARES.

A specification that compares two timestamps ("Each appointment must always end
after it starts", "appointments whose start and end time are identical", prompt
54) is stating that BOTH values are the caller's: the application cannot decide
them. The design model nevertheless marks such a pair ``auto: "now"`` — it reads
"a time field" and reaches for a stamp — and every downstream layer then
faithfully hides it: ``_derive_options`` omits auto-now date columns from
``add``, the model's ``__post_init__`` stamps ``datetime.now()``, and the
service method takes neither, so the shipped ``appointment add`` accepts only
``--title --description --is-active`` and the prompt's own rule ("end after it
starts") is not merely unenforced — it is unstateable.

The rule is read from the prompt alone and touches only the matching pair of one
named entity: a ``created_at``/``updated_at`` stamp is never a start/end pair,
and an auto-stamped pair the prompt never compares is left exactly as designed.
"""
from __future__ import annotations

import re

from agentlib.naming import _snake

# A comparison of two timestamps, stated in the prompt's own words. Kept tight:
# a mere mention of a start and an end somewhere is not a comparison, and only a
# comparison makes both values inputs. (The overlap case — "two overlapping
# reservations" — is its own rule, C3, and is included here because it is the
# same statement: two dates bound an interval the application must compare.)
_COMPARISON_RE = re.compile(
    r"\bend(?:s|ed|ing)?\b[^.]{0,60}\b(?:before|after|later|earlier|"
    r"same\s+time\s+as)\b"
    r"|\bstart(?:s|ed|ing)?\b[^.]{0,60}\band\b[^.]{0,30}\bend(?:s|ed|ing)?\b"
    r"|\bstart\s*(?:time|date|_time|_date)\b[^.]{0,60}"
    r"\bend\s*(?:time|date|_time|_date)\b"
    r"|\boverlapp?(?:ing|ed|s)?\b"
    # "book the same room twice for the same period" — the specification states
    # the interval by the CLASH it must refuse rather than by start/end.
    r"|\bthe\s+same\s+(?:period|time|slot|day|date|night)s?\b"
    r"|\bsame\s+(?:room|resource|car|table|desk)s?\s+twice\b",
    re.IGNORECASE,
)
_START_TOKENS = ("start", "begin", "from", "open", "check_in", "checkin")
_END_TOKENS = ("end", "finish", "close", "due", "check_out", "checkout")
_DATE_TYPES = ("date", "datetime")


def _names_entity(prompt_low, cls):
    snake = _snake(cls)
    return bool(re.search(r"\b%s\b" % re.escape(snake), prompt_low))


def _named_date_fields(ent, tokens):
    """The entity's date/datetime fields whose NAME carries one of ``tokens``."""
    hits = []
    for f in (ent or {}).get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "")
        if (f.get("type") or "") not in _DATE_TYPES or name == "id":
            continue
        if any(tok in name for tok in tokens):
            hits.append(f)
    return hits


def extract_time_pairs(prompt_text, entities_by_class):
    """{class: (start_field, end_field)} for the pairs the prompt compares.

    Only a designed entity the prompt NAMES, carrying one date field whose name
    says "start" and one that says "end", is returned — nothing is invented, and
    an entity whose pair the prompt never compares is absent.
    """
    prompt_low = (prompt_text or "").lower()
    if not prompt_low or not _COMPARISON_RE.search(prompt_low):
        return {}
    pairs = {}
    for cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict) or not _names_entity(prompt_low, cls):
            continue
        starts = _named_date_fields(ent, _START_TOKENS)
        ends = _named_date_fields(ent, _END_TOKENS)
        if starts and ends:
            pairs[cls] = (starts[0], ends[0])
    return pairs


def apply_time_pair_inputs(pairs, entities_by_class):
    """Make the compared pair ordinary INPUTS (no auto-stamp), in place.

    Clearing ``auto`` is the whole change: the field stays optional and nullable,
    it simply stops being stamped by the dataclass — so the surface offers it,
    the service takes it, and the caller's value survives to the row.
    """
    changed = []
    for cls, (start, end) in (pairs or {}).items():
        for field in (start, end):
            if field.get("auto") == "now":
                field.pop("auto", None)
                changed.append("%s.%s" % (_snake(cls), field.get("name")))
    return changed
