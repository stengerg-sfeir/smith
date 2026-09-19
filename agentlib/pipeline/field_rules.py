"""Spec-declared FIELD VALIDATIONS, transcribed from the prompt alone.

The specification states a field's domain in prose — "The email must be valid,
age must be between 18 and 70, and salary must be positive" (prompt 09) — and
nothing downstream ever enforced it: the shipped ``add_employee`` built the row
with no check at all, so an invalid email, an age of 17 or 71 and a negative
salary were all accepted.

This module reads those sentences DETERMINISTICALLY and returns, per entity, the
checks to render. It is independent of the generated code (the prompt is the
only source), and every rule is bound to a field the DESIGNED entity actually
carries — a sentence about a field the model does not have is ignored rather
than invented into the code.
"""
from __future__ import annotations

import re

# "between 18 and 70" / "from 18 to 70" — an inclusive numeric range.
_RANGE_RE = re.compile(
    r"\b(?P<field>[a-z_]+)\s+must\s+be\s+(?:between|from)\s+"
    r"(?P<lo>-?\d+(?:\.\d+)?)\s+(?:and|to)\s+(?P<hi>-?\d+(?:\.\d+)?)\b",
    re.I,
)
# "must be positive" / "must be greater than 0" — a strictly positive number.
_POSITIVE_RE = re.compile(
    r"\b(?P<field>[a-z_]+)\s+must\s+be\s+(?:positive|greater\s+than\s+0)\b",
    re.I,
)
# "must be a valid email" / "must be valid" on an address-shaped field.
_VALID_RE = re.compile(
    r"\b(?P<field>[a-z_]*email[a-z_]*)\s+must\s+be\s+(?:a\s+)?valid\b",
    re.I,
)


def _entity_fields(entities_by_class):
    """{field_name: class} for every designed scalar field."""
    out = {}
    for cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict):
            continue
        for f in ent.get("fields") or []:
            if not isinstance(f, dict) or not f.get("name"):
                continue
            if f["name"] == "id":
                continue
            out.setdefault(f["name"], cls)
    return out


def extract_field_rules(prompt_text, entities_by_class):
    """{class: [rule]} of validations the prompt states for DESIGNED fields.

    A rule is ``{"field", "kind"}`` plus the kind's own data:
    ``{"kind": "range", "lo", "hi"}``, ``{"kind": "positive"}`` or
    ``{"kind": "email"}``. Only fields of a designed entity are returned, so a
    sentence naming a column the model never declared cannot inject a guard
    against something that does not exist.
    """
    text = prompt_text or ""
    if not text:
        return {}
    fields = _entity_fields(entities_by_class)
    rules = {}

    def _add(field, rule):
        cls = fields.get(field)
        if cls is None:
            return
        rules.setdefault(cls, [])
        if rule not in rules[cls]:
            rules[cls].append(rule)

    for m in _RANGE_RE.finditer(text):
        _add(m.group("field").lower(), {
            "field": m.group("field").lower(),
            "kind": "range",
            "lo": float(m.group("lo")),
            "hi": float(m.group("hi")),
        })
    for m in _POSITIVE_RE.finditer(text):
        _add(m.group("field").lower(), {
            "field": m.group("field").lower(),
            "kind": "positive",
        })
    for m in _VALID_RE.finditer(text):
        _add(m.group("field").lower(), {
            "field": m.group("field").lower(),
            "kind": "email",
        })
    return rules
