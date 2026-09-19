"""Spec-declared AUDIT TRAIL rule (E1).

The specification states it outright (prompt 33):

    "Provide CRUD operations for customers. Every creation, update and
     deletion must also produce an audit record containing the operation,
     customer ID and timestamp."

The design DOES create the audit entity (``AuditRecord(customer_id,
operation, timestamp)``, timestamp defaulted in ``__post_init__``) and wires
its repository — but no create/update/delete ever writes a row, so the audit
trail is empty. The rule read here names the audited entity and the audit
entity; the guard renders the writes.

Note the schema half, which the same prompt forces: the rendered audit table
carries ``FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE
CASCADE``. A cascading audit row cannot survive the very deletion it records
— and inserting it after the delete violates the FK — so the audit entity's
foreign key must be dropped (see ``audit_guard.strip_audit_cascade``). An
audit log is a historical record: it outlives its subject by definition.
"""
from __future__ import annotations

import re

from ..naming import _snake

# "Every creation, update and deletion must also produce an audit record ..."
_AUDIT_RE = re.compile(
    r"every\s+(?:creation|create)\s*,?\s*update\s*(?:,|and)\s*"
    r"(?:deletion|delete)\b[^.]*?\baudit\b",
    re.I,
)
_OP_HINTS = ("operation", "op", "action", "event", "type")


def _audit_entity(entities_by_class):
    """The designed entity that IS the audit log, or None.

    Recognised by name (``AuditRecord``/``AuditLog``/``AuditEntry``) — the
    spec calls it an "audit record", and the design follows the wording.
    """
    for cls in entities_by_class or {}:
        if "audit" in str(cls).lower():
            return cls
    return None


def _op_field(ent):
    """The audit entity's "which operation" column (``operation``)."""
    for hint in _OP_HINTS:
        for f in (ent or {}).get("fields") or []:
            if not isinstance(f, dict):
                continue
            if (f.get("name") or "") == hint:
                return f["name"]
    for f in (ent or {}).get("fields") or []:
        if isinstance(f, dict) and f.get("type") == "str":
            name = f.get("name") or ""
            if name not in ("timestamp",):
                return name
    return None


def _audited_entity(audit_cls, audit_ent, entities_by_class):
    """The entity an audit row refers to, via its ``<entity>_id`` column."""
    if not isinstance(audit_ent, dict):
        return None
    for f in audit_ent.get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name") or ""
        if name.endswith("_id") and name != "id":
            target = name[: -len("_id")]
            for cls in (entities_by_class or {}):
                if cls != audit_cls and _snake(cls) == target:
                    return cls
    return None


def extract_audit_rules(prompt_text, entities_by_class):
    """{audited_class: {audit_cls, id_field, operation_field, ops}}.

    Empty unless the prompt demands an audit record for create+update+delete
    AND the design actually produced an audit entity with a resolvable
    reference column and operation column. Absent those, nothing is invented.
    """
    text = prompt_text or ""
    if not text or not _AUDIT_RE.search(text):
        return {}
    audit_cls = _audit_entity(entities_by_class)
    if not audit_cls:
        return {}
    audit_ent = (entities_by_class or {}).get(audit_cls) or {}
    audited = _audited_entity(audit_cls, audit_ent, entities_by_class)
    if not audited:
        return {}
    id_field = _snake(audited) + "_id"
    operation_field = _op_field(audit_ent)
    if not operation_field:
        return {}
    return {
        audited: {
            "audit_cls": audit_cls,
            "id_field": id_field,
            "operation_field": operation_field,
            "ops": ["create", "update", "delete"],
        }
    }
