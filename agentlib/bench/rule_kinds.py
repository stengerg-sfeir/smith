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
            "joined via fk_field. Use when a parent's STORED total field must "
            "equal the sum over its children (e.g. invoice.total = z line.quantity "
            "x line.unit_price). Do NOT use for a report METHOD (use "
            "aggregate_mul_sum / sum_mul_joined). Fields: parent_entity, "
            "parent_total_field, child_entity, child_amount_fields (list), fk_field."
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
            "stub. ONLY for real callable methods on a service/repository class; NEVER for a "
            "model field/attribute or a default value. Fields: class, methods (list)."
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
            "filter_lt: the dedicated zero-argument filter method (e.g. a low-stock report) "
            "must return only rows of entity whose field is strictly less than the threshold "
            "ref_entity.ref_field, related through fk. ALL SIX FIELDS ARE REQUIRED: entity = the "
            "entity whose rows are filtered; field = the compared field on entity (e.g. stock_qty); "
            "ref_entity = the entity that holds the threshold (e.g. Category); ref_field = the "
            "threshold field on ref_entity (e.g. reorder_threshold); fk = the FK on entity pointing "
            "to ref_entity (e.g. category_id); method = the zero-arg method returning the filtered "
            "rows. A rule missing any of these is not expressible and must be reported "
            "as unexpressed."
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
            "aggregate_mul_sum: the zero-arg method on the service must return, "
            "grouped by fk, the sum of (a * b) over entity rows. Use ONLY for a "
            "report method that returns a GROUPED mapping {group: sum(a*b)} (e.g. "
            "stock value per category). Do NOT use for a stored parent total field "
            "(use sum_equals) or a single scalar total (use sum_mul_joined). "
            "Fields: entity, method, fk, a, b."
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
            "fk": str,
        },
        description=(
            "ensure_raise: ONLY when the spec explicitly says the method validates/raises "
            "(e.g. 'validates the X exists', 'raises if not found', 'rejects a duplicate'). "
            "Do NOT infer validation from a description like 'lists filtered by X'. The method "
            "must raise when ref_entity.ref_field does not exist (inject via fk, the method "
            "parameter that carries the referenced id; fall back to ref_field), and/or raise when "
            "unique_field is duplicated. Fields: method, entity, ref_entity, ref_field, fk, "
            "unique_field."
        ),
        executor="_test_ensure_raise",
    ),
    RuleKind(
        name="count_group_by",
        fields={
            "entity": str,
            "method": str,
            "fk": str,
            "ref_entity": str,
            "field": str,
        },
        description=(
            "count_group_by: the zero-arg method on the service must return the number of "
            "rows of entity grouped by fk (e.g. number of sales per product). Fields: entity "
            "= the counted row entity; method = the zero-arg method returning the grouped "
            "counts; fk = the FK on entity that groups; ref_entity = the group owner entity; "
            "field = the counted field (optional, default 'id' = count rows)."
        ),
        executor="_test_count_group_by",
    ),
    RuleKind(
        name="sum_mul_joined",
        fields={
            "entity": str,
            "method": str,
            "fk": str,
            "ref_entity": str,
            "child_field": str,
            "ref_field": str,
        },
        description=(
            "sum_mul_joined: the zero-arg method on the service must return a scalar equal "
            "to the sum over entity rows of (child_field * ref_field), where ref_field lives "
            "on ref_entity and is reached via fk (e.g. total sales amount = quantity * "
            "product price). Fields: entity, method, fk, ref_entity, child_field, ref_field."
        ),
        executor="_test_sum_mul_joined",
    ),
    RuleKind(
        name="ensure_raise_with_comparison",
        fields={
            "method": str,
            "entity": str,
            "fk": str,
            "ref_entity": str,
            "ref_field": str,
            "aggregate_field": str,
            "comparator": str,
            "exception": str,
        },
        description=(
            "ensure_raise_with_comparison: the method raises the named exception when an "
            "aggregate across entity rows (sum of aggregate_field, reached via fk to "
            "ref_entity) crosses the threshold ref_entity.ref_field, compared by comparator "
            "(lt/lte/gt/gte). Use ONLY when the spec explicitly says the method validates/raises "
            "on such a comparison (e.g. 'checks if budget exceeded after insertion' -> "
            "BudgetExceededException). Do NOT use for a missing-reference or duplicate "
            "validation (use ensure_raise). Fields: method, entity, fk, ref_entity, ref_field, "
            "aggregate_field, comparator, exception."
        ),
        executor="_test_ensure_raise_with_comparison",
    ),
    RuleKind(
        name="sum_compare_status",
        fields={
            "entity": str,
            "method": str,
            "fk": str,
            "ref_entity": str,
            "ref_field": str,
            "aggregate_field": str,
            "over_status": str,
        },
        description=(
            "sum_compare_status: the method returns, per group, a status/flag computed by "
            "comparing the SUM of entity.aggregate_field (grouped via fk) against the threshold "
            "ref_entity.ref_field; over_status is the status string/flag to return when the sum "
            "exceeds the threshold (e.g. 'budget status on_track/warning/exceeded per category' "
            "where over_status='exceeded'). Fields: entity, method, fk, ref_entity, ref_field, "
            "aggregate_field, over_status."
        ),
        executor="_test_sum_compare_status",
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
