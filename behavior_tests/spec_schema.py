"""JSON schema + deterministic validators for the behavioral test spec.

The test oracle (``oracle.py``) produces a ``test_spec.json`` via a
schema-constrained LLM pass that reads ONLY the prompt text — never the
generated code or the design manifest. This module defines that schema and
validates/normalizes the parsed spec so the deterministic renderer
(``renderer.py``) can rely on a well-formed shape.

The spec deliberately exists at the level of *declared intent* (entities,
their fields, FK references, exceptions, and business rules such as
"overlapping reservations are rejected" or "invoice total = sum of lines").
It does not encode any implementation detail of the code under test.
"""

from __future__ import annotations

import re

from agentlib.naming import _camel, _snake

from .rule_kinds import kind_by_name, kind_names

_NAME_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
_NAME_CLASS = re.compile(r"^[A-Z][A-Za-z0-9_]*$")

_FIELD_TYPES = ("str", "int", "float", "bool", "date", "datetime")
# Business-rule kinds are discovered from the registry (single source of truth).
_BUSINESS_RULE_KINDS = tuple(kind_names())
_EXCEPTION_TRIGGERS = (
    "not_found", "validation", "conflict", "constraint", "custom",
)


def _field_schema():
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string", "enum": list(_FIELD_TYPES)},
            "nullable": {"type": "boolean"},
            "unique": {"type": "boolean"},
            "auto": {"type": "string", "enum": ["now", "autoincrement"]},
            "primary_key": {"type": "boolean"},
            "default": {"type": "string"},
        },
        "required": ["name", "type"],
        "additionalProperties": False,
    }


_LIST_RULE_FIELDS = {"child_amount_fields", "fields", "methods"}


def _rule_field_schema(name):
    if name in _LIST_RULE_FIELDS:
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "string"}


def _kind_rule_schema(kind_name: str, required_fields: tuple[str, ...],
                      one_of_required: tuple[tuple[str, ...], ...] = ()) -> dict:
    """Build a per-kind object schema that requires ``required_fields``.

    ``one_of_required`` lets a kind express "either group A or group B is
    present" (used by ``ensure_raise``: ``(("ref_field",), ("unique_field",))``)
    via an ``anyOf`` over ``required`` clauses. Fields named in a one-of group
    are added as properties but are NOT in the static ``required`` list — they
    are only pulled in by the ``anyOf``.
    """
    kk = kind_by_name(kind_name)
    props = {"id": {"type": "string"}, "kind": {"const": kind_name}}
    if kk is not None:
        for f in kk.fields:
            props[f] = _rule_field_schema(f)
    for group in one_of_required:
        for f in group:
            props.setdefault(f, _rule_field_schema(f))
    item = {
        "type": "object",
        "properties": props,
        "required": ["id", "kind"] + list(required_fields),
        "additionalProperties": False,
    }
    if one_of_required:
        item["allOf"] = [
            {"anyOf": [{"required": list(group)} for group in one_of_required]}
        ]
    return item


def _business_rules_array_schema():
    """JSON array schema for business_rules (shared by the full test-spec
    schema and the dedicated kind-detection schema).

    Each kind is a ``oneOf`` branch that REQUIRES its own fields, so a rule
    cannot be emitted with the right ``kind`` but missing a required field
    (e.g. ``filter_lt`` without ``field``). That was the root cause of
    malformed rules that had to be dropped downstream; a strict schema forces
    the model to produce complete, usable rules.
    """
    per_kind = {
        "overlap_conflict": ("entity", "start_field", "end_field", "scope_field"),
        "sum_equals": ("parent_entity", "parent_total_field", "child_entity",
                       "child_amount_fields", "fk_field"),
        "unique_pair": ("entity", "fields"),
        "no_stub": ("class", "methods"),
        "filter_lt": ("entity", "method", "field", "ref_entity", "ref_field", "fk"),
        "aggregate_mul_sum": ("entity", "method", "fk", "a", "b"),
    }
    branches = [
        _kind_rule_schema(kind, fields)
        for kind, fields in per_kind.items()
    ]
    # ensure_raise: method is mandatory, AND either ref_field or unique_field
    # must be present (entity / ref_entity stay optional).
    branches.append(
        _kind_rule_schema(
            "ensure_raise",
            ("method",),
            one_of_required=(("ref_field",), ("unique_field",)),
        )
    )
    return {
        "type": "array",
        "items": {"oneOf": branches},
    }


def business_rules_schema():
    """Narrow JSON schema for a dedicated business-rule detection pass.

    Unlike the full ``test_spec_schema``, this only constrains the
    business-rules output so the model's attention is focused on kind
    detection, not on the whole domain model.
    """
    return {
        "type": "object",
        "properties": {
            "business_rules": _business_rules_array_schema(),
            "business_logic_coverage": {
                "type": "string",
                "enum": ["full", "partial", "none"],
            },
            "unexpressed_rules": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["business_rules", "business_logic_coverage", "unexpressed_rules"],
        "additionalProperties": False,
    }


def test_spec_schema():
    """The GBNF-constrained schema for a behavioral test spec."""
    return {
        "type": "object",
        "properties": {
            "database_file": {"type": "string"},
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "table_name": {"type": "string"},
                        "fields": {
                            "type": "array",
                            "items": _field_schema(),
                        },
                        "unique_together": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "fks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string"},
                                    "ref": {"type": "string"},
                                },
                                "required": ["field", "ref"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["name", "fields"],
                    "additionalProperties": False,
                },
            },
            "exceptions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "trigger": {
                            "type": "string",
                            "enum": list(_EXCEPTION_TRIGGERS),
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
            "business_rules": _business_rules_array_schema(),
            "repositories": {
                "type": "array",
                "items": _api_object_schema(),
            },
            "services": {
                "type": "array",
                "items": _api_object_schema(),
            },
            "seed": {
                "type": "object",
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
        },
        "business_logic_coverage": {
            "type": "string",
            "enum": ["full", "partial", "none"],
        },
        "unexpressed_rules": {
            "type": "array",
            "items": {"type": "string"},
        },
        "required": ["entities", "exceptions", "repositories"],
        "additionalProperties": False,
    }


def _api_object_schema():
    return {
        "type": "object",
        "properties": {
            "module": {"type": "string"},
            "class": {"type": "string"},
            "entity": {"type": "string"},
            "methods": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "params": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"},
                                },
                                "required": ["name", "type"],
                                "additionalProperties": False,
                            },
                        },
                        "returns": {"type": "string"},
                    },
                    "required": ["name", "params", "returns"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["module", "class", "methods"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Deterministic normalization + validation
# ---------------------------------------------------------------------------

def _normalize_fields(ent):
    """Rescue common field-naming mistakes in a designed entity."""
    fields = ent.get("fields") or []
    for f in fields:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if isinstance(name, str):
            f["name"] = _snake(name.split(":")[0].split("(")[0].strip())
    return fields


def _normalize_fks(ent):
    fks = ent.get("fks") or []
    seen = set()
    out = []
    for fk in fks:
        if not isinstance(fk, dict):
            continue
        field, ref = fk.get("field"), fk.get("ref")
        if not field or not ref:
            continue
        field = _snake(str(field))
        ref = _camel(str(ref))
        if field in seen:
            continue
        seen.add(field)
        out.append({"field": field, "ref": ref})
    ent["fks"] = out


_REQUIRED_RULE_FIELDS: dict[str, tuple[str, ...]] = {
    "overlap_conflict": ("entity", "start_field", "end_field", "scope_field"),
    "sum_equals": ("parent_entity", "parent_total_field", "child_entity",
                   "child_amount_fields", "fk_field"),
    "unique_pair": ("entity", "fields"),
    "no_stub": ("class", "methods"),
    "filter_lt": ("entity", "method", "field", "ref_entity", "ref_field", "fk"),
    "aggregate_mul_sum": ("entity", "method", "fk", "a", "b"),
}


def rule_is_complete(rule: dict) -> bool:
    """True if the rule has the fields its kind strictly requires.

    The dedicated oracle may emit a rule with the right ``kind`` but missing
    some required per-kind fields (a small model often confuses fields between
    kinds, e.g. ``filter_lt`` given ``a``/``b`` instead of ``field``). Such a
    rule cannot be exercised meaningfully and would only crash or spuriously
    fail the renderer, so it is dropped (and surfaced as unexpressed).
    """
    kind = rule.get("kind")
    if kind == "ensure_raise":
        return bool(rule.get("method")) and bool(
            rule.get("ref_field") or rule.get("unique_field"))
    req = _REQUIRED_RULE_FIELDS.get(kind) if isinstance(kind, str) else None
    if req is None:
        return True  # unknown kind is caught by the validator
    for key in req:
        v = rule.get(key)
        if v is None or v == "" or v == []:
            return False
    return True


def _normalize_rule(rule):
    for key in (
        "entity", "start_field", "end_field", "scope_field", "parent_entity",
        "parent_total_field", "child_entity", "fk_field", "class",
        "method", "ref_entity", "ref_field", "fk", "a", "b",
    ):
        if isinstance(rule.get(key), str) and rule[key]:
            if key in ("entity", "parent_entity", "child_entity",
                       "class", "ref_entity"):
                rule[key] = _camel(rule[key])
            else:
                rule[key] = _snake(rule[key])
    for key in ("child_amount_fields", "fields", "methods"):
        val = rule.get(key)
        if isinstance(val, list):
            rule[key] = [_snake(str(v)) for v in val if isinstance(v, str)]


def normalize_test_spec(data):
    """Normalize a parsed test spec (rescues common LLM formatting slips)."""
    if not isinstance(data, dict):
        return data

    ents = data.get("entities")
    if isinstance(ents, list):
        for ent in ents:
            if not isinstance(ent, dict):
                continue
            ent["name"] = _camel(str(ent.get("name") or "").strip())
            tn = ent.get("table_name")
            ent["table_name"] = _snake(str(tn)) if isinstance(tn, str) and tn else ""
            _normalize_fields(ent)
            _normalize_fks(ent)
            ut = ent.get("unique_together")
            if isinstance(ut, list):
                ent["unique_together"] = [
                    [_snake(str(x)) for x in pair if isinstance(x, str)]
                    for pair in ut
                    if isinstance(pair, list)
                ]

    exc = data.get("exceptions")
    if isinstance(exc, list):
        for e in exc:
            if isinstance(e, dict) and isinstance(e.get("name"), str):
                e["name"] = _camel(e["name"].strip())

    rules = data.get("business_rules")
    if isinstance(rules, list):
        for r in rules:
            if isinstance(r, dict):
                _normalize_rule(r)

    for key in ("repositories", "services"):
        objs = data.get(key)
        if isinstance(objs, list):
            for obj in objs:
                if not isinstance(obj, dict):
                    continue
                obj["module"] = str(obj.get("module") or "").strip()
                obj["class"] = _camel(str(obj.get("class") or "").strip())
                obj["entity"] = (
                    _camel(str(obj.get("entity") or "").strip())
                    if obj.get("entity")
                    else ""
                )
    return data


def normalize_business_rules(data):
    """Normalize a parsed business-rules-only dict (kind-detection result)."""
    if not isinstance(data, dict):
        return data
    rules = data.get("business_rules")
    if isinstance(rules, list):
        for r in rules:
            if isinstance(r, dict):
                _normalize_rule(r)
    return data


def v_business_rules(data):
    """Return validation errors for a business-rules-only dict ([] when OK)."""
    if not isinstance(data, dict):
        return ["business-rule spec must be an object"]
    errs = []
    br = data.get("business_rules")
    if not isinstance(br, list):
        errs.append("business_rules must be an array")
    else:
        for r in br:
            if not isinstance(r, dict) or not isinstance(r.get("id"), str):
                errs.append("bad business rule %r" % (r,))
            elif r.get("kind") not in _BUSINESS_RULE_KINDS:
                errs.append("bad business rule kind %r" % (r.get("kind"),))
    if data.get("business_logic_coverage") not in ("full", "partial", "none"):
        errs.append(
            "bad business_logic_coverage %r" % (data.get("business_logic_coverage"),)
        )
    return errs


def _v_fields(ent):
    errs = []
    fields = ent.get("fields")
    if not isinstance(fields, list) or not fields:
        errs.append("%s: no fields" % ent.get("name"))
        return errs
    for f in fields:
        if not isinstance(f, dict):
            errs.append("%s: field not an object" % ent.get("name"))
            continue
        fname, ftype = f.get("name"), f.get("type")
        if not isinstance(fname, str) or not _NAME_SNAKE.match(fname):
            errs.append("%s: bad field name %r" % (ent.get("name"), fname))
        if ftype not in _FIELD_TYPES:
            errs.append("%s: bad type %r for %r" % (ent.get("name"), ftype, fname))
    return errs


def v_test_spec(data):
    """Return a list of validation errors ([] when the spec is well-formed)."""
    if not isinstance(data, dict):
        return ["test spec must be an object"]
    errs = []

    ents = data.get("entities")
    if not isinstance(ents, list) or not ents:
        return ["entities must be a non-empty array"]
    for ent in ents:
        if not isinstance(ent, dict):
            errs.append("entity not an object")
            continue
        name = ent.get("name")
        if not isinstance(name, str) or not _NAME_CLASS.match(name):
            errs.append("bad entity name %r" % (name,))
        errs.extend(_v_fields(ent))
        fk = ent.get("fks")
        if fk is not None and not isinstance(fk, list):
            errs.append("%s: fks must be an array" % (name,))

    exc = data.get("exceptions")
    if not isinstance(exc, list):
        errs.append("exceptions must be an array")
    else:
        for e in exc:
            if not isinstance(e, dict) or not isinstance(e.get("name"), str) \
                    or not _NAME_CLASS.match(e["name"]):
                errs.append("bad exception entry %r" % (e,))
            elif e.get("trigger") not in _EXCEPTION_TRIGGERS:
                errs.append("bad exception trigger %r" % (e.get("trigger"),))

    rules = data.get("business_rules")
    if rules is not None and not isinstance(rules, list):
        errs.append("business_rules must be an array")
    else:
        for r in rules or []:
            if not isinstance(r, dict) or not isinstance(r.get("id"), str):
                errs.append("bad business rule %r" % (r,))
            elif r.get("kind") not in _BUSINESS_RULE_KINDS:
                errs.append("bad business rule kind %r" % (r.get("kind"),))

    for key in ("repositories", "services"):
        objs = data.get(key)
        if objs is not None and not isinstance(objs, list):
            errs.append("%s must be an array" % key)
        else:
            for obj in objs or []:
                if not isinstance(obj, dict):
                    errs.append("%s entry not an object" % key)
                    continue
                if not isinstance(obj.get("module"), str) or not obj["module"]:
                    errs.append("%s entry missing module" % key)
                if not isinstance(obj.get("class"), str) or \
                        not _NAME_CLASS.match(obj["class"]):
                    errs.append("%s entry bad class %r" % (key, obj.get("class")))
                methods = obj.get("methods")
                if not isinstance(methods, list) or not methods:
                    errs.append("%s.%s: no methods" % (key, obj.get("class")))
                else:
                    for m in methods:
                        if not isinstance(m, dict) or not isinstance(m.get("name"), str) \
                                or not _NAME_SNAKE.match(m["name"]):
                            errs.append(
                                "%s.%s: bad method %r" % (key, obj.get("class"), m)
                            )
    return errs
