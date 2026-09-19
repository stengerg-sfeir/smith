"""Spec-declared REFERENTIAL guard on DELETE (C5).

The specification states it outright (prompt 36):

    "Every product must belong to an existing category. A category cannot be
     deleted while products still belong to it."

Nothing enforced it: ``category delete`` removed the row, and the products that
referenced it were left pointing at a category that no longer exists (or were
silently cascaded away). The rule is a plain referential check, read from the
prompt and bound to designed entities:

    a <resource> cannot be deleted while <items> still belong to it

Only a rule whose resource, item AND foreign key all resolve against the
design is kept — an invented column would refuse the wrong deletion.
"""
from __future__ import annotations

import re

from ..naming import _camel, _snake

# "A category cannot be deleted while products still belong to it."
_BLOCK_DELETE_RE = re.compile(
    r"\b(?:a|an|the)\s+(?P<res>[a-z_]+)\s+cannot\s+be\s+deleted\s+while\s+"
    r"(?P<item>[a-z_]+)\s+(?:still\s+)?belong\s+to\s+it\b",
    re.I,
)


def _singleton(noun):
    """``products`` -> ``product``."""
    noun = (noun or "").lower()
    if noun.endswith("ies"):
        return noun[:-3] + "y"
    if noun.endswith("s") and not noun.endswith("ss"):
        return noun[:-1]
    return noun


def _resource_fk(item_ent, resource_cls):
    """The item's FK column onto ``resource_cls``, or None."""
    want = _snake(resource_cls) + "_id"
    for f in (item_ent or {}).get("fields") or []:
        if isinstance(f, dict) and f.get("name") == want:
            return want
    return None


def extract_reference_rules(prompt_text, entities_by_class):
    """{resource_class: {"item", "item_class", "fk_field"}}.

    A rule is kept only when both classes are DESIGNED and the item carries a
    real foreign key onto the resource. Otherwise the prompt's refusal cannot
    be turned into a check, and the delete is left as it was.
    """
    text = prompt_text or ""
    if not text:
        return {}
    rules = {}
    for m in _BLOCK_DELETE_RE.finditer(text):
        res_cls = _camel(_singleton(m.group("res")))
        item_cls = _camel(_singleton(m.group("item")))
        item_ent = (entities_by_class or {}).get(item_cls)
        if not isinstance(item_ent, dict):
            continue
        if res_cls not in (entities_by_class or {}):
            continue
        fk_field = _resource_fk(item_ent, res_cls)
        if not fk_field:
            continue
        rules[res_cls] = {
            "item": _snake(item_cls),
            "item_class": item_cls,
            "fk_field": fk_field,
        }
    return rules
