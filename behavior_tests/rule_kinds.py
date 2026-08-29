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
            "the same scope. entity = the entity whose rows must not overlap; "
            "start_field/end_field = the two interval-bounding fields; "
            "scope_field = the field that must match for two intervals to "
            "conflict. Use the entity/field names verbatim from the "
            "specification."
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
            "joined via fk_field. parent_entity/child_entity = the two entities "
            "the specification relates; fk_field = the foreign key linking child "
            "to parent; child_amount_fields = the numeric fields multiplied per "
            "child row. Use the entity/field names verbatim from the "
            "specification."
        ),
        executor="_test_sum_equals",
    ),
    RuleKind(
        name="unique_pair",
        fields={"entity": str, "fields": list},
        description=(
            "unique_pair: the given fields on entity must be unique together. "
            "entity = the entity; fields = the list of field names the "
            "specification declares unique together. Use the field names "
            "verbatim from the specification."
        ),
        executor="_test_unique_pair",
    ),
    RuleKind(
        name="no_stub",
        fields={"class": str, "methods": list},
        description=(
            "no_stub: the given methods on class must be implemented, not a "
            "stub. class = the repository/service class named in the "
            "specification; methods = the method names it requires to be "
            "implemented (NOT an entity field default). Use the class/method "
            "names verbatim from the specification."
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
            "filter_lt: a method must return only rows where field is strictly "
            "less than ref_entity.ref_field, joined via fk. method = the EXACT "
            "method the specification names for this filtering (a dedicated "
            "report/filter method, NOT a generic list method); field = the entity "
            "field compared against the threshold; ref_entity/ref_field = the "
            "entity + field carrying the threshold; fk = the foreign-key field "
            "linking the rows to that entity. Use the method/field names verbatim "
            "from the specification."
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
            "aggregate_mul_sum: a method must return, grouped by fk, the sum of "
            "(a * b) over entity rows. method = the EXACT method the "
            "specification names for this aggregate; fk = the grouping "
            "foreign-key field; a = the first numeric field in the product; b = "
            "the second numeric field. Use the method/field names verbatim from "
            "the specification."
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
            "ensure_raise: a method must raise when a referenced entity does not "
            "exist and/or when a unique value is duplicated. method = the EXACT "
            "method the specification names that performs this validation; "
            "ref_entity = the referenced entity; ref_field = the parameter the "
            "method actually validates (the foreign-key/id parameter passed INTO "
            "it, NOT the entity's primary key field unless that is literally the "
            "parameter); unique_field = the field whose duplicate triggers a "
            "raise. Use the method/parameter names verbatim from the "
            "specification."
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


def rule_kind_descriptions(kinds=None) -> str:
    """Concatenated kind descriptions for the oracle's business_rules prompt.

    ``kinds`` (optional) limits the output to a subset of kind names, used by
    the split detection passes so each call only advertises its own kinds.
    """
    if kinds is None:
        selected = RULE_KINDS
    else:
        kinds_set = set(kinds)
        selected = [k for k in RULE_KINDS if k.name in kinds_set]
    return "\n".join("- " + k.description for k in selected)


def executor_for(kind: str) -> str | None:
    """Return the renderer executor function name for a kind, if registered."""
    k = _KIND_BY_NAME.get(kind)
    return k.executor if k else None
