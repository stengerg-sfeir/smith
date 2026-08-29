"""Behavioral test spec extraction (the test oracle).

This module is the ONLY LLM pass in the behavioral pipeline. It reads the
prompt specification TEXT and produces a schema-constrained ``test_spec``
JSON object that declares what the generated application must *do*
(entities, fields, FK references, exceptions, business rules, and the
service/repository API surface). It deliberately does not look at the
generated code or the design manifest, so the resulting tests are an
independent oracle and not a tautological echo of the implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentlib.config import LLM_MAX_TOKENS_LONG
from agentlib.llm.client import _json_complete

from .spec_schema import (
    business_rules_schema,
    normalize_business_rules,
    normalize_test_spec,
    test_spec_schema,
    v_business_rules,
    v_test_spec,
)
from .rule_kinds import rule_kind_descriptions

# The oracle is a SPECIFICATION read: it infers the declared domain and its
# invariants. It must not encode any implementation detail. We ask for a
# compact JSON describing the domain model, exceptions, business rules and
# the public API surface the spec demands.
_TEST_SPEC_SYSTEM = (
    "You are an expert software tester. You will be given a software "
    "specification. Your job is to produce a BEHAVIORAL TEST SPEC: a JSON "
    "object that precisely captures what behaviors the finished program must "
    "exhibit. You do NOT write code. You capture the CONTRACT.\n\n"
    "Produce a JSON object with these fields:\n"
    "- \"database_file\": the SQLite database file name the spec names, or "
    "\"app.db\" if it names none.\n"
    "- \"entities\": an array. Each entity is an object: {\"name\": "
    "\"PascalCase\", \"table_name\": \"snake_case_plural\", \"fields\": "
    "[{\"name\", \"type\", \"nullable\", \"unique\", \"auto\"}], "
    "\"unique_together\": [[\"field\", ...], ...], \"fks\": "
    "[{\"field\": \"<field ending in _id>\", \"ref\": \"PascalCase\"}]}. "
    "Types are primitives: str, int, float, bool, date, datetime. Set "
    "\"nullable\": true for optional fields. Set "
    "\"unique\": true for fields the spec says are unique. Set \"auto\": "
    "\"autoincrement\" for the auto-incremented primary key id, and \"auto\": "
    "\"now\" for creation-timestamps the spec implies. \"unique_together\" "
    "holds table-level unique pairs. \"fks\" holds foreign-key fields and "
    "the entity they reference.\n"
    "- \"exceptions\": an array of {\"name\": \"PascalCase\", \"trigger\": "
    "one of \"not_found\", \"validation\", \"conflict\", \"constraint\", "
    "\"custom\"}. Only list exceptions the spec implies.\n"
    "- \"business_rules\": an array of {\"id\": \"snake_case\", \"kind\": "
    "one of \"overlap_conflict\", \"sum_equals\", \"unique_pair\", "
    "\"no_stub\", plus the relevant fields}. \"overlap_conflict\" uses "
    "\"entity\", \"start_field\", \"end_field\", \"scope_field\". "
    "\"sum_equals\" uses \"parent_entity\", \"parent_total_field\", "
    "\"child_entity\", \"child_amount_fields\", \"fk_field\". "
    "\"unique_pair\" uses \"entity\", \"fields\". Only include rules the "
    "spec states.\n"
    "- \"repositories\": an array of {\"module\", \"class\", \"entity\", "
    "\"methods\": [{\"name\", \"params\": [{\"name\", \"type\"}], "
    "\"returns\"}]}. Basic CRUD (create/get_by_id/list/update/delete) is "
    "generated automatically, so list ONLY the project-specific methods.\n"
    "- \"services\": same shape, the public service-layer methods.\n\n"
    "Do NOT invent behaviors the spec does not state. Do NOT reference any "
    "implementation. Output ONLY the JSON."
)


def extract_test_spec(prompt_text: str, verbose: bool = False) -> dict | None:
    """Return a normalized, validated test spec for ``prompt_text``."""
    user = "SPECIFICATION:\n%s\n\nEmit the behavioral test spec JSON now." % prompt_text
    system = (
        _TEST_SPEC_SYSTEM
        + "\n\nAVAILABLE RULE KINDS (you may ONLY emit these kinds):\n"
        + rule_kind_descriptions()
        + "\n\n"
        + _VERBATIM_NOTE
        + "\n\nCoverage: after business_rules, if the SPECIFICATION describes "
          "business logic/validation that you could NOT express with the kinds "
          "above, set \"business_logic_coverage\" to \"partial\" or \"none\" and "
          "list each unexpressible rule in \"unexpressed_rules\". If you expressed "
          "everything, set \"business_logic_coverage\" to \"full\" and "
          "\"unexpressed_rules\" to []."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=test_spec_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if not isinstance(data, dict):
            continue
        data = normalize_test_spec(data)
        errs = v_test_spec(data)
        if not errs:
            return data
        if verbose:
            for e in errs:
                print("    [test-oracle] spec issue: %s" % e)
    return None


def generate_test_spec(prompt_path: Path, out_path: Path | None = None,
                       verbose: bool = False) -> dict | None:
    """Read a prompt file, extract its test spec, and optionally write JSON."""
    prompt_text = prompt_path.read_text(encoding="utf-8")
    spec = extract_test_spec(prompt_text, verbose=verbose)
    if spec is not None and out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return spec


# ---------------------------------------------------------------------------
# Dedicated business-rule (kind) detection pass.
#
# A focused LLM call that reads ONLY the prompt and outputs just
# business_rules + coverage. Isolating kind detection from the full spec
# (entities/repositories/services) lowers the model's cognitive load so it is
# far less likely to miss the business rules a prompt actually implies.
# Descriptions stay abstract/shape-only: no concrete entity/field examples,
# to avoid a small model "copying" example names into unrelated prompts.
# ---------------------------------------------------------------------------

_KIND_DETECT_SYSTEM = (
    "You are an expert software tester. Given a software specification, your "
    "ONLY task is to identify which BUSINESS RULES it requires, expressed with "
    "the available rule KINDS. Do NOT describe the data model, repositories, "
    "services or exceptions — those are handled elsewhere. Output ONLY a JSON "
    "object with three keys:\n"
    "- \"business_rules\": an array of {\"id\": \"snake_case\", \"kind\": one "
    "of the kinds below, plus ONLY the fields that kind uses}.\n"
    "- \"business_logic_coverage\": \"full\" if you expressed every business "
    "rule in the specification, \"partial\" if some are not expressible with "
    "these kinds, \"none\" if none are expressible.\n"
    "- \"unexpressed_rules\": one string per rule you could NOT express "
    "([] if none).\n\n"
    "Match the SHAPE of the specification to a kind; do not invent rules the "
    "spec does not state, and do not copy example entity/field names from "
    "elsewhere."
)

_VERBATIM_NOTE = (
    "All entity/field/method/parameter names MUST be taken verbatim from the "
    "specification. Never invent a name that the specification does not state."
)


def extract_business_rules(prompt_text: str, verbose: bool = False) -> dict | None:
    """Return a normalized business-rules-only spec via a focused kind pass.

    The per-kind descriptions now carry semantic mapping guidance (which
    method / parameter the kind refers to), and a "verbatim" note forces the
    model to use the specification's exact names. The strict per-kind schema
    guarantees every emitted rule is complete.
    """
    user = "SPECIFICATION:\n%s\n\nEmit the business-rule JSON now." % prompt_text
    system = (
        _KIND_DETECT_SYSTEM
        + "\n\nAVAILABLE RULE KINDS (you may ONLY emit these kinds):\n"
        + rule_kind_descriptions()
        + "\n\n"
        + _VERBATIM_NOTE
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=business_rules_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if not isinstance(data, dict):
            continue
        data = normalize_business_rules(data)
        errs = v_business_rules(data)
        if not errs:
            return data
        if verbose:
            for e in errs:
                print("    [kind-oracle] issue: %s" % e)
    return None
