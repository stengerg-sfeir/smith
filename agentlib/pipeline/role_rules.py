"""Role / authorisation rules read out of a prompt (palier 4, correctif E4).

Prompt 39 states an access policy in two clauses::

    "Administrators can manage products and users."
    "Normal users can create orders and view their own orders but cannot
     modify products or other users."

The baseline renders an application where EVERY command is open to anyone: no
command identifies its caller, and nothing ever reads ``User.role`` — so a
normal user edits products and other users at will.

This module reads those clauses and returns the policy a guard can act on::

    {
        "actor":        "User",       # the class that carries the role
        "role_field":   "role",       # the column that carries it
        "admin_values": ["admin", "administrator"],
        "restricted":   {"Product": ["add", "update", "delete"],
                         "User":    ["add", "update", "delete"]},
        "own_row":      True,         # a normal user may still edit itself
    }

Two conditions keep the rule honest. The acting class must carry a role
COLUMN — a design with no role field has nothing to compare. And the policy
must be stated as one of these clauses; a project that merely mentions a role
is left alone, which is what keeps every unrelated prompt (and all six named
ones, none of which contains "administrator" or "normal users") untouched.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from agentlib.naming import _snake

# "Administrators can manage products and users."
_ADMIN_RE = re.compile(r"\badmins?\b|\badministrator\w*\b", re.IGNORECASE)
# "Normal users ...", "regular users ...", "standard users ..."
_NORMAL_RE = re.compile(
    r"\b(?:normal|regular|standard|ordinary|non-?admin\w*)\s+users?\b",
    re.IGNORECASE,
)
# "but cannot modify products or other users"
_CANNOT_RE = re.compile(r"\bcannot\s+(?P<clause>[^.;]*)", re.IGNORECASE)

# The prompt's wording -> the operations it names. "manage" is the umbrella the
# administrator clause uses, and it covers every write.
_VERB_WORDS: Dict[str, Tuple[str, ...]] = {
    "manage": ("add", "update", "delete"),
    "administrate": ("add", "update", "delete"),
    "add": ("add",),
    "create": ("add",),
    "register": ("add",),
    "update": ("update",),
    "modify": ("update",),
    "edit": ("update",),
    "change": ("update",),
    "delete": ("delete",),
    "remove": ("delete",),
}
# Only writes are ever gated: reading a catalogue is not "managing" it, and the
# prompt's prohibition is written about modifying.
_WRITE_VERBS = ("add", "update", "delete")


def _sentences(text: str) -> List[str]:
    """The prompt's sentences (a clause of the policy is one sentence)."""
    return [part for part in re.split(r"[.;\n]+", text or "") if part.strip()]


def _fields(entity: Any) -> List[str]:
    """Field names of an entity, tolerating both shapes the pipeline uses."""
    fields = entity.get("fields") if isinstance(entity, dict) else getattr(
        entity, "fields", None
    )
    names: List[str] = []
    for field in fields or []:
        if isinstance(field, str):
            names.append(field)
        elif isinstance(field, dict) and field.get("name"):
            names.append(str(field["name"]))
        elif getattr(field, "name", None):
            names.append(str(field.name))
    return names


def _role_field(fields: Sequence[str]) -> Optional[str]:
    """The column carrying the role: ``role`` when present, else ``*role*``."""
    candidates = [name for name in fields if "role" in name.lower()]
    if not candidates:
        return None
    candidates.sort(key=lambda name: (name != "role", len(name), name))
    return candidates[0]


def _actor_with_role(
    entities_by_class: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str]]:
    """``(class, role column)`` — the class whose rows carry a role.

    A class whose name says "user" is preferred, then the shortest name, so
    ``User`` beats ``AppUser`` (the tie-break the ownership rule already uses).
    """
    found: List[Tuple[str, str]] = []
    for name, entity in (entities_by_class or {}).items():
        column = _role_field(_fields(entity))
        if column is not None:
            found.append((name, column))
    if not found:
        return None, None
    found.sort(key=lambda pair: ("user" not in pair[0].lower(), len(pair[0]), pair[0]))
    return found[0]


def _entities_in(text: str, entities_by_class: Dict[str, Any]) -> List[str]:
    """The DESIGNED classes the text names, singular or plural.

    Word-bounded, and only a designed class can match, so a clause can never
    restrict an entity the specification never asked for.
    """
    lowered = " %s " % (text or "").lower()
    found: List[str] = []
    for name in entities_by_class or {}:
        stem = _snake(name)
        for form in (stem, "%ss" % stem, "%ses" % stem):
            if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(form), lowered):
                if name not in found:
                    found.append(name)
                break
    return found


def _verbs_in(text: str) -> Set[str]:
    """The operations the text names."""
    verbs: Set[str] = set()
    for word in re.findall(r"[a-z]+", (text or "").lower()):
        verbs.update(_VERB_WORDS.get(word, ()))
    return verbs


def _admin_values(words: Sequence[str]) -> List[str]:
    """The role values that mean "administrator".

    Derived from the prompt's own word, so a specification that says
    "Administrators" accepts both that spelling and the shorter ``admin`` the
    role column is normally seeded with.
    """
    values: Set[str] = set()
    for word in words or ():
        word = (word or "").strip().lower()
        if not word:
            continue
        singular = word[:-1] if word.endswith("s") else word
        values.add(singular)
        if singular.startswith("admin"):
            values.add("admin")
    if not values:
        values.update({"admin", "administrator"})
    return sorted(values)


def extract_role_rules(
    prompt_text: str, entities_by_class: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Return the role policy stated by ``prompt_text``, or ``None``.

    ``None`` means the prompt states no administrator/normal-user policy (or the
    design carries no role column), so no guard may be applied.
    """
    if not prompt_text or not entities_by_class:
        return None
    actor, role_field = _actor_with_role(entities_by_class)
    if actor is None:
        return None

    restricted: Dict[str, Set[str]] = {}
    admin_words: List[str] = []

    for sentence in _sentences(prompt_text):
        if _ADMIN_RE.search(sentence):
            admin_words.extend(_ADMIN_RE.findall(sentence))
            verbs = _verbs_in(sentence)
            if not verbs:
                continue
            for name in _entities_in(sentence, entities_by_class):
                restricted.setdefault(name, set()).update(verbs)
            continue
        if _NORMAL_RE.search(sentence):
            for match in _CANNOT_RE.finditer(sentence):
                clause = match.group("clause")
                verbs = _verbs_in(clause)
                if not verbs:
                    continue
                for name in _entities_in(clause, entities_by_class):
                    restricted.setdefault(name, set()).update(verbs)

    gated = {
        name: [verb for verb in _WRITE_VERBS if verb in verbs]
        for name, verbs in restricted.items()
        if verbs.intersection(_WRITE_VERBS)
    }
    if not gated:
        return None

    return {
        "actor": actor,
        "role_field": role_field,
        "admin_values": _admin_values(admin_words),
        "restricted": gated,
        # "cannot modify ... other users" leaves a user's OWN row modifiable.
        "own_row": actor in gated,
    }
