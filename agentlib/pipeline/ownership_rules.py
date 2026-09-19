"""Ownership / access-scoping rules read out of a prompt (palier 4, correctif E3).

Prompt 38 says two things::

    "Users must authenticate before accessing documents."
    "A user can only read, modify or delete their own documents."

The baseline renders an application where any caller can list, update or delete
any document: the acting user is never required, and never compared with the
row's owner. (Prompt 38's own design even offers ``--user-id`` on
``document update``, but only to *write* it into the row — i.e. to hand the
document to somebody else.)

This module reads the sentence and returns the structured rule a guard can act
on::

    {
        "actor":         "User",        # who must be authenticated
        "resource":      "Document",    # what is being protected
        "owner_field":   "user_id",     # the FK that records the owner
        "auth_required": True,          # "must authenticate before accessing"
        "resource_noun": "documents",   # as written in the prompt
        "verbs":         ["delete", "modify", "read"],
        "scoped_writes": ["delete", "modify"],
    }

Nothing is inferred from a resource name alone: the rule only fires when the
prompt actually scopes access to the caller's *own* rows, which is what keeps
every unrelated prompt — and all six named ones — untouched.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agentlib.naming import _snake

# "can only read, modify or delete their own documents"
_OWN_ONLY_RE = re.compile(
    r"\b(?:can\s+only|may\s+only|only)\s+"
    r"(?P<verbs>[a-z]+(?:\s*,\s*[a-z]+)*\s+or\s+[a-z]+|[a-z]+)"
    r"[^.]*?\btheir\s+own\s+(?P<resource>[a-z][a-z_]*)",
    re.IGNORECASE,
)
# a looser fallback: "... their own <resource>" anywhere, provided an access
# verb appears in the same sentence.
_OWN_FALLBACK_RE = re.compile(
    r"\btheir\s+own\s+(?P<resource>[a-z][a-z_]*)", re.IGNORECASE
)
_AUTH_RE = re.compile(
    r"\b(?:must|have to|need to|should)\s+(?:first\s+)?authenticate\b"
    r"|\bauthenticate\s+before\b",
    re.IGNORECASE,
)

# Only these verbs make an "own" clause an access-scoping rule.
_ACCESS_VERBS = frozenset(
    {
        "read", "view", "see", "access", "modify", "edit", "update", "delete",
        "remove", "change",
    }
)
# Access verbs that name a write rather than a read.
_WRITE_VERBS = frozenset(
    {"modify", "edit", "update", "delete", "remove", "change"}
)


def _singular(noun: str) -> str:
    """``documents`` -> ``document``; an already singular noun is unchanged."""
    noun = noun.strip().lower()
    if noun.endswith("ies") and len(noun) > 3:
        return noun[:-3] + "y"
    if noun.endswith("ses") and len(noun) > 3:
        return noun[:-2]
    if noun.endswith("s") and not noun.endswith("ss"):
        return noun[:-1]
    return noun


def _class_name(noun: str) -> str:
    """``document`` -> ``Document``."""
    singular = _singular(noun)
    return singular[:1].upper() + singular[1:]


def _entity_fields(entities_by_class: Dict[str, Any], class_name: str) -> List[str]:
    """Field names of an entity, tolerating both shapes the pipeline uses."""
    entity = entities_by_class.get(class_name)
    if entity is None:
        return []
    fields = entity.get("fields") if isinstance(entity, dict) else getattr(
        entity, "fields", None
    )
    if not fields:
        return []
    names: List[str] = []
    for field in fields:
        if isinstance(field, str):
            names.append(field)
        elif isinstance(field, dict) and field.get("name"):
            names.append(str(field["name"]))
        elif getattr(field, "name", None):
            names.append(str(field.name))
    return names


def _owner_field(fields: List[str], actor: str, resource: str) -> Optional[str]:
    """The FK on the resource that records the owner.

    The preference order keeps the meaning explicit: ``owner_id`` beats
    ``<actor>_id``, which beats any other ``*_id`` whose stem names the actor.
    A bare ``id`` is never chosen.
    """
    candidates = [f for f in fields if f.endswith("_id") and f != "id"]
    if not candidates:
        return None
    for wanted in (
        "owner_id",
        "%s_id" % _snake(actor),
        "%s_id" % _snake(resource),
    ):
        if wanted in candidates:
            return wanted
    for name in candidates:
        stem = name[:-3]
        if stem.startswith("owner") or _snake(actor) in stem:
            return name
    return None


def _actor_class(
    entities_by_class: Dict[str, Any], resource: str
) -> Optional[str]:
    """The class that must be authenticated: ``User`` when it exists.

    Any class whose name contains "user" (``User``, ``AppUser``) qualifies; the
    shortest name wins, so ``User`` is preferred over ``AppUser``.
    """
    candidates = [
        name
        for name in entities_by_class
        if name != resource and "user" in name.lower()
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda name: (len(name), name))
    return candidates[0]


def _verbs_in(text: str) -> set:
    """The access verbs named in ``text``."""
    return {
        word for word in re.findall(r"[a-z]+", text.lower())
        if word in _ACCESS_VERBS
    }


def _resource_noun(match: "re.Match[str]") -> str:
    noun = (match.groupdict().get("resource") or "").strip()
    if not noun:
        return ""
    return re.split(r"[\s,.;):]", noun)[0]


def extract_ownership_rule(
    prompt_text: str, entities_by_class: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Return the ownership rule stated by ``prompt_text``, or ``None``.

    ``None`` means the prompt does not scope access to the caller's own rows, so
    no guard may be applied.
    """
    if not prompt_text:
        return None

    match = _OWN_ONLY_RE.search(prompt_text)
    if match is not None:
        verbs = _verbs_in(match.group("verbs"))
    else:
        match = _OWN_FALLBACK_RE.search(prompt_text)
        if match is None:
            return None
        # The fallback needs an access verb in the same sentence.
        sentence = _sentence_around(prompt_text, match.start())
        verbs = _verbs_in(sentence)

    if not verbs & _ACCESS_VERBS:
        return None

    resource_noun = _resource_noun(match)
    if not resource_noun:
        return None
    resource = _class_name(resource_noun)
    if resource not in entities_by_class:
        return None

    actor = _actor_class(entities_by_class, resource)
    if actor is None:
        return None

    owner_field = _owner_field(
        _entity_fields(entities_by_class, resource), actor, resource
    )
    if owner_field is None:
        return None

    return {
        "actor": actor,
        "resource": resource,
        "owner_field": owner_field,
        "auth_required": bool(_AUTH_RE.search(prompt_text)),
        "resource_noun": resource_noun,
        "verbs": sorted(verbs & _ACCESS_VERBS),
        "scoped_writes": sorted(verbs & _WRITE_VERBS),
    }


def _sentence_around(text: str, index: int) -> str:
    """The sentence of ``text`` containing ``index``."""
    start = text.rfind(".", 0, index) + 1
    end = text.find(".", index)
    if end == -1:
        end = len(text)
    return text[start:end]
