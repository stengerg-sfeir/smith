"""Discoverable registry of business-rule "kinds".

A ``kind`` is a named, deterministic *test template* (see the renderer's
``_test_*`` functions). Each entry declares:

* ``name``        — the enum value used in ``business_rules[].kind``;
* ``fields``      — the rule's schema parameters (field -> type hint), so the
                   test-spec schema and the oracle JSON constraint know which
                   keys to allow per kind;
* ``description`` — a short spec-text sentence used to build the oracle's
                   business_rules prompt, so the LLM knows the current
                   vocabulary (and only it);
* ``executor``    — the name of the deterministic test function in the
                   renderer template that runs this kind.

The registry is the single source of truth: ``spec_schema`` derives its
``kind`` enum from it, ``oracle`` derives its prompt text from it, and
``renderer`` derives its ``kind -> executor`` dispatch from it. Adding a rule
kind = one entry here (+ its executor in the renderer template) — nothing else
to touch.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleKind:
    name: str
    fields: dict
    description: str
    executor: str


RULE_KINDS: list[RuleKind] = [
    RuleKind(
        name="overlap_conflict",
        fields={
            "entity": str,
            "start_field": str,
            "end_field": str,
            "scope_field": str,
        },
        description=(
            "overlap_conflict: no two intervals of an entity may overlap within "
            "the same scope. Fields: entity, start_field, end_field, scope_field."
        ),
        executor="_test_overlap",
    ),
    RuleKind(
        name="sum_equals",
        fields={
            "parent_entity": str,
            "parent_total_field": str,
            "child_entity": str,
            "child_amount_fields": list,
            "fk_field": str,
        },
        description=(
            "sum_equals: parent_total_field on parent_entity must equal the sum "
            "of the products of child_amount_fields across child_entity rows "
            "joined via fk_field. Fields: parent_entity, parent_total_field, "
            "child_entity, child_amount_fields (list), fk_field."
        ),
        executor="_test_sum_equals",
    ),
    RuleKind(
        name="unique_pair",
        fields={"entity": str, "fields": list},
        description=(
            "unique_pair: composite multi-column uniqueness constraint (the given fields on entity "
            "must be unique together; do NOT use for a single field already marked unique: true). "
            "Fields: entity, fields (list)."
        ),
        executor="_test_unique_pair",
    ),
    RuleKind(
        name="no_stub",
        fields={"class": str, "methods": list},
        description=(
            "no_stub: the given service/repository methods on class must be implemented, not a "
            "stub (NEVER use for model attributes/fields). Fields: class, methods (list)."
        ),
        executor="_test_no_stub",
    ),
    RuleKind(
        name="filter_lt",
        fields={
            "entity": str,
            "method": str,
            "field": str,
            "ref_entity": str,
            "ref_field": str,
            "fk": str,
        },
        description=(
            "filter_lt: the dedicated zero-argument filter method on entity/service (e.g. low_stock_report) "
            "must return only rows where field is strictly less than ref_entity.ref_field, related through "
            "fk. Fields: entity, method, field, ref_entity, ref_field, fk."
        ),
        executor="_test_filter_lt",
    ),
    RuleKind(
        name="aggregate_mul_sum",
        fields={
            "entity": str,
            "method": str,
            "fk": str,
            "a": str,
            "b": str,
        },
        description=(
            "aggregate_mul_sum: the method on the service must return, grouped "
            "by fk, the sum of (a * b) over entity rows. Fields: entity, method, "
            "fk, a, b."
        ),
        executor="_test_aggregate_mul_sum",
    ),
    RuleKind(
        name="ensure_raise",
        fields={
            "method": str,
            "entity": str,
            "ref_entity": str,
            "ref_field": str,
            "unique_field": str,
        },
        description=(
            "ensure_raise: the method must raise when a referenced "
            "ref_entity.ref_field does not exist, and/or raise when "
            "unique_field is duplicated. Fields: method, entity, ref_entity, "
            "ref_field, unique_field."
        ),
        executor="_test_ensure_raise",
    ),
]


# Convenience lookup + auto-discovery helpers -------------------------------

_KIND_BY_NAME: dict[str, RuleKind] = {k.name: k for k in RULE_KINDS}


def kind_names() -> list[str]:
    """All registered kind names (used to build the schema enum)."""
    return [k.name for k in sorted(RULE_KINDS, key=lambda k: k.name)]


def kind_by_name(name: str) -> RuleKind | None:
    return _KIND_BY_NAME.get(name)


def rule_kind_descriptions() -> str:
    """Concatenated kind descriptions for the oracle's business_rules prompt."""
    return "\n".join("- " + k.description for k in RULE_KINDS)


def executor_for(kind: str) -> str | None:
    """Return the renderer executor function name for a kind, if registered."""
    k = _KIND_BY_NAME.get(kind)
    return k.executor if k else None
