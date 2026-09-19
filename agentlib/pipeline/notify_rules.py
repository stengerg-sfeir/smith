"""Spec-declared NOTIFICATION requirement (E2).

The specification states it outright (prompt 40):

    "When an order is confirmed, the application must send a notification.
     Define a notification service abstraction and provide a simple
     implementation that logs the notification instead of sending a real
     message."

Three things are asked and none exist: the confirmation sends nothing, there
is no abstraction, and there is no logging implementation. The design even
misnames the ORDER service ``NotificationService`` and its ``confirm_order``
returns True with no side effect at all.

This rule reads the trigger from the prompt — "when an <entity> is <verbed>"
— and resolves the service method that performs it (``confirmed`` ->
``confirm`` -> ``confirm_order``), which is where the notification belongs.
"""
from __future__ import annotations

import re

from ..naming import _camel, _snake

# "When an order is confirmed, the application must send a notification."
_WHEN_RE = re.compile(
    r"when\s+(?:an?|the)\s+(?P<entity>[a-z_]+)\s+is\s+(?P<verb>[a-z_]+?)(?:ed|d)\b"
    r"[^.]*?\b(?:send|notify|notif\w*)\b",
    re.I,
)
# "Define a notification service abstraction and provide a simple
#  implementation that logs the notification ..."
_ABSTRACTION_RE = re.compile(
    r"\bnotification\b[^.]*?\babstraction\b|\babstraction\b[^.]*?\bnotification\b"
    r"|\bimpl\w*\b[^.]*?\blog\w*\b[^.]*?\bnotification\b",
    re.I,
)


def _verb_stem(word):
    """``confirmed`` -> ``confirm``."""
    w = (word or "").lower()
    for suffix in ("ied", "ed", "d"):
        if w.endswith(suffix) and len(w) > len(suffix) + 1:
            stem = w[: -len(suffix)]
            if suffix == "ied":
                return stem + "y"
            return stem
    return w


def extract_notify_rules(prompt_text, entities_by_class):
    """{entity_class: {"verb", "method"}}.

    Kept only when the prompt states BOTH the trigger ("when an X is …" and a
    notification) AND the abstraction requirement, and the entity is designed.
    Without the abstraction sentence the specification is asking for an
    ordinary side effect, not this rule.
    """
    text = prompt_text or ""
    if not text or not _ABSTRACTION_RE.search(text):
        return {}
    rules = {}
    for m in _WHEN_RE.finditer(text):
        cls = _camel(m.group("entity"))
        if cls not in (entities_by_class or {}):
            continue
        verb = _verb_stem(m.group("verb"))
        if not verb:
            continue
        rules[cls] = {
            "verb": verb,
            "method": "%s_%s" % (verb, _snake(cls)),
        }
    return rules
