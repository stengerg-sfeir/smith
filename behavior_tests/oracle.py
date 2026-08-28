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

from .spec_schema import normalize_test_spec, test_spec_schema, v_test_spec

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
    "\"nullable\": true for optional fields and for the primary key id. Set "
    "\"unique\": true for fields the spec says are unique. Set \"auto\": "
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
    messages = [
        {"role": "system", "content": _TEST_SPEC_SYSTEM},
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
