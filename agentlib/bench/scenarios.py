"""Requirement → test generation (the redesign).

Replaces the closed "rule kind" / assertion-kind vocabulary with an open,
two-phase flow that generates an executable test from a requirement and the
actual code, then gates it with a deterministic reference check and an LLM
semantic critic:

1. ``extract_business_requirements`` — read the prompt only, emit natural
   language requirements (one per invariant). NO kind choice.
2. ``generate_test`` — read the requirement + the real design (names only, as
   vocabulary) and emit a structured test: ``setup`` (seed rows with known
   values), ``action`` (one real method call), ``assertion`` (a Python boolean
   expression over ``result`` and ``@handle.field`` values).
3. ``generate_expectation`` — a SEPARATE prose sentence describing what this
   test verifies (kept apart to keep each LLM step's cognitive load low).
4. ``validate_test_structure`` — DETERMINISTIC: every entity/field/method/
   class referenced (including every ``@handle`` / ``@handle.field`` in the
   assertion) must exist in the design reconstructed from the code; any
   hallucinated reference is rejected.
5. ``validate_expectation_semantic`` — an LLM critic comparing the PROSE
   expectation vs the PROSE requirement → ok/ko, with a repair loop.

The design spec is supplied as NAMING VOCABULARY only (never rule existence),
so the model binds to real names instead of inventing fields like
``total_stock_value``, and stays an independent oracle rather than a
tautological echo of the implementation.
"""

from __future__ import annotations

import ast
import re

from agentlib.config import LLM_MAX_TOKENS_LONG
from agentlib.llm.client import _json_complete
from agentlib.naming import _camel, _snake


# ---------------------------------------------------------------------------
# JSON schemas (fed to the schema-constrained LLM client)
# ---------------------------------------------------------------------------

def requirements_schema():
    """Schema for the prose business-requirement extraction pass."""
    return {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement_id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["requirement_id", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    }


def test_schema():
    """Schema for a single generated test (setup + action + assertion)."""
    return {
        "type": "object",
        "properties": {
            "requirement_id": {"type": "string"},
            "setup": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity": {"type": "string"},
                        "ref": {"type": "string"},
                        "fields": {"type": "object"},
                    },
                    "required": ["entity", "ref", "fields"],
                    "additionalProperties": False,
                },
            },
            "action": {
                "type": "object",
                "properties": {
                    "module": {"type": "string"},
                    "class": {"type": "string"},
                    "method": {"type": "string"},
                    "args": {"type": "array"},
                },
                "required": ["method"],
                "additionalProperties": False,
            },
            "assertion": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["requirement_id", "setup", "action", "assertion"],
        "additionalProperties": False,
    }


def expectation_schema():
    """Schema for the prose test-expectation (separate generation)."""
    return {
        "type": "object",
        "properties": {
            "requirement_id": {"type": "string"},
            "expectation": {"type": "string"},
        },
        "required": ["requirement_id", "expectation"],
        "additionalProperties": False,
    }


def semantic_schema():
    """Schema for the LLM critic verdict (anchored 3-level scale)."""
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string",
                        "enum": ["fully", "partially", "does_not_verify"]},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "reason"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Design context (naming vocabulary for the model)
# ---------------------------------------------------------------------------

def _design_context(design_spec: dict | None) -> str:
    """A compact line-list of the design's ACTUAL entity/field/method names.

    This is naming vocabulary ONLY. It tells the model which real names exist
    so it binds tests to them instead of inventing fields or methods. It does
    NOT drive which requirements exist (that stays the prompt's job), keeping
    the oracle independent rather than a tautological echo.
    """
    if not design_spec:
        return ""
    lines = []
    for ent in design_spec.get("entities", []):
        fields = ", ".join(
            "%s:%s" % (f["name"], f.get("type", ""))
            for f in ent.get("fields", [])
        )
        fks = ", ".join(
            "(%s->%s)" % (f["field"], f["ref"])
            for f in ent.get("fks", [])
        )
        lines.append(
            "ENTITY %s{fields: %s%s}"
            % (ent["name"], fields, "; fks: " + fks if fks else "")
        )
    for key in ("services", "repositories"):
        for obj in design_spec.get(key, []):
            meths = ", ".join(
                "%s(%s) -> %s" % (m["name"], ",".join(p["name"] for p in m.get("params", [])), m.get("returns", "?"))
                for m in obj.get("methods", [])
            )
            lines.append(
                "CLASS %s.%s{methods: %s}"
                % (obj.get("module", ""), obj.get("class", ""), meths)
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pass 1: prose requirement extraction
# ---------------------------------------------------------------------------

_REQ_SYSTEM = (
    "You are an expert software tester. Given a software specification, list "
    "the BUSINESS RULES / INVARIANTS it implies, one per requirement. Emit "
    "each as a short natural-language sentence.\n\n"
    "- Emit ONLY invariants the spec explicitly states or clearly implies, "
    "written so a test could verify them (e.g. \"invoice.total equals the sum "
    "of line quantity * unit_price\", \"a low-stock report returns only "
    "products whose stock_qty is below their category's reorder_threshold\").\n"
    "- One requirement per invariant. Do NOT emit requirements for plain CRUD, "
    "schema definitions, or simple field presence.\n"
    "- Do NOT describe entities/fields/services as a data model — only the "
    "verifiable invariants.\n"
    "- If the spec implies no verifiable invariant, emit an empty list.\n"
)


def extract_business_requirements(prompt_text: str, verbose: bool = False) -> list[dict]:
    """Return a list of ``{requirement_id, text}`` prose requirements.

    Reads ONLY the prompt (never the design/code) so the requirement set is an
    independent, non-tautological oracle.
    """
    user = "SPECIFICATION:\n%s\n\nExtract the business requirements now." % prompt_text
    messages = [
        {"role": "system", "content": _REQ_SYSTEM},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=requirements_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if isinstance(data, dict) and isinstance(data.get("requirements"), list):
            out = []
            for i, r in enumerate(data["requirements"]):
                if isinstance(r, dict) and isinstance(r.get("text"), str) and r["text"].strip():
                    rid = r.get("requirement_id")
                    if not isinstance(rid, str) or not rid:
                        rid = "req_%04d" % (i + 1)
                    out.append({"requirement_id": rid, "text": r["text"].strip()})
            return out
        if verbose:
            print("    [scenario-oracle] requirement extraction retrying…")
    return []


# ---------------------------------------------------------------------------
# Pass 2: test generation per requirement
# ---------------------------------------------------------------------------

_SCENARIO_SYSTEM = (
    "You are an expert software tester. Given a REQUIREMENT (natural language) "
    "and the system's actual design, emit ONE concrete test as JSON.\n\n"
    "SCHEMA:\n"
    "- requirement_id: the requirement id you were given.\n"
    "- setup: a list of seed steps, in order. Each step is {entity, ref, "
    "fields}. `ref` is a local handle used to reference that row's values later "
    "(as \"@handle\"). `fields` maps a field name to a concrete primitive "
    "value.\n"
    "CRITICAL: every \"@handle\" you write MUST match a `ref` of a row you "
    "seeded EARLIER in setup. If an entity has an FK field, seed the referenced "
    "parent entity FIRST, then use its \"@handle\" for the FK value. NEVER "
    "write a \"@handle\" for a row you did not seed — it will be rejected.\n"
    "- action: {module (optional), class (optional), method, args}. `args` is "
    "the list of positional arguments; an arg of the form \"@handle.field\" "
    "references that field's value, \"@handle\" references the row id. Booleans "
    "are JSON true/false, NOT the strings \"true\"/\"false\".\n"
    "- assertion: a Python BOOLEAN expression the test will run. Use `result` "
    "for the action's return value. Use \"@handle.field\" for a seeded field's "
    "value and \"@handle.id\" for a row id. Numbers and + - * / are literal. "
    "For \"must raise\", write `raises(<ExceptionName>)`. For \"contains\", "
    "write e.g. `\"SKU-1\" in result`. For length, write `len(result) == 2`.\n"
    "- rationale: 1-2 sentences explaining how `assertion` derives from the "
    "requirement and the setup values.\n\n"
    "EXAMPLES:\n"
    "1) 'invoice.total equals sum of line qty*price': {\"requirement_id\": \"1\", "
    "\"setup\": [{\"entity\": \"Customer\", \"ref\": \"cust\", \"fields\": {\"name\": "
    "\"A\", \"email\": \"a@x.com\"}}, {\"entity\": \"Product\", \"ref\": \"prod\", "
    "\"fields\": {\"name\": \"Widget\", \"price\": 10}}, {\"entity\": \"Invoice\", \"ref\": "
    "\"inv\", \"fields\": {\"customer_id\": \"@cust\", \"total_amount\": 0}}, {\"entity\": "
    "\"InvoiceLine\", \"ref\": \"l1\", \"fields\": {\"invoice_id\": \"@inv\", "
    "\"product_id\": \"@prod\", \"quantity\": 2, \"unit_price\": 3}}, {\"entity\": "
    "\"InvoiceLine\", \"ref\": \"l2\", \"fields\": {\"invoice_id\": \"@inv\", "
    "\"product_id\": \"@prod\", \"quantity\": 4, \"unit_price\": 5}}], \"action\": "
    "{\"class\": \"InvoiceService\", \"method\": \"get_invoice_with_lines\", \"args\": "
    "[\"@inv.id\"]}, \"assertion\": \"result.total_amount == @l1.quantity * @l1.unit_price "
    "+ @l2.quantity * @l2.unit_price\", \"rationale\": \"total = 2*3 + 4*5 = 26.\"}\n"
    "2) 'stock value per category': {\"requirement_id\": \"2\", \"setup\": [{\"entity\": "
    "\"Category\", \"ref\": \"cat\", \"fields\": {\"name\": \"Electronics\"}}, {\"entity\": "
    "\"Product\", \"ref\": \"p1\", \"fields\": {\"category_id\": \"@cat\", \"price_cents\": "
    "100, \"stock_qty\": 2}}, {\"entity\": \"Product\", \"ref\": \"p2\", \"fields\": "
    "{\"category_id\": \"@cat\", \"price_cents\": 50, \"stock_qty\": 1}}], \"action\": "
    "{\"class\": \"InventoryService\", \"method\": \"stock_value_by_category\", \"args\": "
    "[]}, \"assertion\": \"sum(result.values()) == @p1.price_cents * @p1.stock_qty + "
    "@p2.price_cents * @p2.stock_qty\", \"rationale\": \"category value = 100*2 + 50*1 = 250.\"}\n"
    "3) 'raise on missing reference': {\"requirement_id\": \"3\", \"setup\": [...], \"action\": "
    "{\"method\": \"get_invoice\", \"args\": [999999]}, \"assertion\": \"raises(InvoiceNotFoundError)\", "
    "\"rationale\": \"no invoice id 999999 exists.\"}\n\n"
    "RULES:\n"
    "- Use ONLY entity/class/method/field names from the design below.\n"
    "- `assertion` MUST be a Python expression the test engine can evaluate with "
    "the real seeded values after setup. Never hardcode a literal not derivable "
    "from the setup.\n"
    "- When the action returns a dict (a per-group aggregate), do NOT assert "
    "exact equality on the whole dict (`result == {...}`): the key form (id vs "
    "name) is indeterminate. Check the VALUE instead, e.g. "
    "`sum(result.values()) == ...` or `result.get(@handle.id) == ...`.\n"
    "- An FK field value MUST be a \"@handle\" reference to a parent you seeded, "
    "never a literal id or plain string. ALWAYS seed the referenced parent "
    "entity first.\n"
    "- Never reference a \"@handle\" you did not seed in setup.\n"
    "- Booleans are JSON true/false, never the strings \"true\"/\"false\".\n"
    "- If the requirement cannot be exercised deterministically, emit an empty "
    "\"assertion\": \"\" and explain why in rationale.\n"
    "- Emit exactly ONE test.\n\n"
)


def generate_test(requirement: dict, design_spec: dict | None = None,
                  verbose: bool = False, repair: bool = False,
                  errors: list[str] | None = None) -> dict | None:
    """Return a test dict ``{requirement_id, setup, action, assertion}`` for one
    requirement, or None on failure. ``repair=True`` appends a hint plus the
    specific rejection ``errors`` so the model knows exactly what to fix."""
    design_block = _design_context(design_spec)
    system = _SCENARIO_SYSTEM + "DESIGN (real names — bind ONLY to these):\n" + design_block
    if repair:
        system += "\n\nREPAIR: your previous test was rejected. Re-emit a correct one."
        if errors:
            system += "\nThe previous test had these PROBLEMS to fix:\n- " + "\n- ".join(errors)
        system += (
            "\nEnsure every entity/field/method name exists in the design above, "
            "every @handle is defined in setup, and `assertion` is a valid Python "
            "boolean expression over `result` and @handle.field values."
        )
    user = (
        "REQUIREMENT:\n[%s] %s\n\nEmit the test JSON now."
        % (requirement.get("requirement_id", "?"), requirement.get("text", ""))
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=test_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if not isinstance(data, dict):
            continue
        data = _normalize_test(data)
        if data.get("requirement_id") and isinstance(data.get("setup"), list) \
                and isinstance(data.get("action"), dict) \
                and isinstance(data.get("assertion"), str):
            return data
        if verbose:
            print("    [test-oracle] test validation retrying…")
    return None


_EXPECT_SYSTEM = (
    "You are an expert software tester. Given a REQUIREMENT and a TEST (setup, "
    "action, assertion), write ONE prose sentence describing what the test "
    "VERIFIES — the test's meaning/expectation, in natural language. Do not "
    "restate the test mechanics; state the invariant it checks.\n\n"
    "Output JSON {\"requirement_id\": \"...\", \"expectation\": \"...\"}."
)


def generate_expectation(test: dict, requirement: dict,
                         design_spec: dict | None = None,
                         verbose: bool = False,
                         reason: str | None = None) -> str | None:
    """Return a prose expectation (what the test verifies), generated separately
    from the test to keep each LLM step's cognitive load low. ``reason`` (when a
    previous expectation was rejected) prefixes the rejection so the model knows
    what to fix."""
    design_block = _design_context(design_spec)
    user = (
        "REQUIREMENT:\n[%s] %s\n\nTEST:\n%s\n\nDESIGN:\n%s\n\n"
        "Write the test expectation (prose) now."
        % (requirement.get("requirement_id", "?"), requirement.get("text", ""),
           _test_to_text(test), design_block)
    )
    if reason:
        user = ("The previous expectation was rejected because: %s\n\n" % reason) + user
    messages = [
        {"role": "system", "content": _EXPECT_SYSTEM},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=expectation_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if isinstance(data, dict) and isinstance(data.get("expectation"), str) \
                and data["expectation"].strip():
            return data["expectation"].strip()
        if verbose:
            print("    [expectation-oracle] retrying…")
    return None


def _normalize_test(test):
    """Snake-case field names, camel-case entity/class names in a test."""
    if not isinstance(test, dict):
        return test
    for row in test.get("setup", []) or []:
        if not isinstance(row, dict):
            continue
        if isinstance(row.get("entity"), str):
            row["entity"] = _camel(row["entity"])
        if isinstance(row.get("ref"), str):
            row["ref"] = _snake(row["ref"])
        fields = row.get("fields")
        if isinstance(fields, dict):
            row["fields"] = {_snake(k): v for k, v in fields.items()}
    action = test.get("action")
    if isinstance(action, dict):
        if isinstance(action.get("class"), str):
            action["class"] = _camel(action["class"])
        if isinstance(action.get("method"), str):
            action["method"] = _snake(action["method"])
    return test


def _test_to_text(test: dict) -> str:
    """A compact human-readable rendering of a test for the critic."""
    lines = []
    lines.append("setup:")
    for row in test.get("setup", []) or []:
        lines.append("  %s %s = %s"
                     % (row.get("entity"), row.get("ref"),
                        row.get("fields", {})))
    action = test.get("action", {}) or {}
    lines.append("action: %s.%s(%s)"
                 % (action.get("class", "?"), action.get("method", "?"),
                    ", ".join(map(str, action.get("args", [])))))
    lines.append("assertion: %s" % test.get("assertion", ""))
    lines.append("rationale: %s" % test.get("rationale", ""))
    return "\n".join(lines)


def _assertion_py_source(assertion: str) -> str:
    """Return a parseable form of an assertion for Python-syntax checking.

    The raw assertion contains '@handle' / '@handle.field' tokens (invalid
    Python) that are only substituted at render time. Replace them with a
    neutral numeric literal so the surrounding expression can be parsed.
    """
    return re.sub(
        r"@[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?",
        "0",
        assertion,
    )


# ---------------------------------------------------------------------------
# Pass 3: deterministic structural / reference validation
# ---------------------------------------------------------------------------

def validate_test_structure(test: dict, design_spec: dict | None) -> list[str]:
    """Return human-readable reference issues ([] = sound).

    Every entity/field/method/class referenced by the setup/action/assertion
    must exist in the design (which is reconstructed from the actual code, so
    names match the code by construction). A missing reference means the test
    hallucinated a name and is rejected.
    """
    if not design_spec:
        return ["no design spec to validate against"]
    errs = []
    entities = {e["name"]: e for e in design_spec.get("entities", [])}

    # --- setup rows ---
    seen_refs = set()
    setup = test.get("setup", []) or []
    if not setup:
        errs.append("test has empty setup (nothing to seed)")
    for idx, row in enumerate(setup):
        if not isinstance(row, dict):
            errs.append("setup[%d]: row not an object" % idx)
            continue
        ent_name = row.get("entity")
        ref = row.get("ref")
        if ent_name not in entities:
            errs.append("setup[%d].%s: unknown entity %r" % (idx, ref, ent_name))
            continue
        if ref in seen_refs:
            errs.append("setup[%d]: duplicate ref %r" % (idx, ref))
        seen_refs.add(ref)
        ent = entities[ent_name]
        ent_fields = {f["name"] for f in ent.get("fields", [])}
        fk_fields = {f["field"] for f in ent.get("fks", [])}
        for fname, fval in (row.get("fields", {}) or {}).items():
            if fname not in ent_fields:
                errs.append("setup[%d].%s: field %r not on %s"
                            % (idx, ref, fname, ent_name))
            elif fname in fk_fields:
                # An FK field MUST be a @handle reference to a previously
                # seeded parent row. A literal id (999, 1) is a dangling
                # reference the test cannot guarantee — reject it.
                if not (isinstance(fval, str) and fval.startswith("@")):
                    errs.append("setup[%d].%s: FK %r must be a @handle reference, got %r"
                                % (idx, ref, fname, fval))
                else:
                    target = fval[1:].split(".")[0]
                    if target not in seen_refs:
                        errs.append("setup[%d].%s: FK %r references unknown @%s"
                                    % (idx, ref, fname, target))

    # --- duplicate unique-field seed detection ---
    # Two setup rows for the same entity must not set the same value on a field
    # the design declares UNIQUE — a duplicate raises a constraint error during
    # seeding and makes the test meaningless (generator bug, not an app bug).
    unique_vals = {}  # (entity, field) -> (set_of_values, first_ref)
    for idxx, row in enumerate(setup):
        if not isinstance(row, dict):
            continue
        ent_name = row.get("entity")
        if ent_name not in entities:
            continue
        ent = entities[ent_name]
        for fname, fval in (row.get("fields", {}) or {}).items():
            fdef = next((f for f in ent.get("fields", []) if f.get("name") == fname), None)
            if fdef is None or not fdef.get("unique"):
                continue
            if isinstance(fval, str) and fval.startswith("@"):
                continue  # FK/derived value — not comparable pre-resolution
            key = (ent_name, fname)
            seen, first_ref = unique_vals.get(key, (set(), None))
            if fval in seen:
                errs.append("setup[%d].%s: duplicate unique value for %s.%s (same as %s)"
                            % (idxx, row.get("ref"), ent_name, fname, first_ref))
            else:
                seen.add(fval)
                if first_ref is None:
                    first_ref = row.get("ref")
                unique_vals[key] = (seen, first_ref)

    # --- action ---
    action = test.get("action", {}) or {}
    method_name = action.get("method")
    cls_name = action.get("class")
    if not method_name:
        errs.append("action: missing method")
    else:
        declared = []
        for obj in design_spec.get("services", []) + design_spec.get("repositories", []):
            for m in obj.get("methods", []):
                declared.append((m.get("name"), obj.get("class"), obj.get("module")))
        found = False
        for mname, cname, _mod in declared:
            if mname == method_name and (cls_name is None or cname == cls_name):
                found = True
                break
        if not found:
            if cls_name:
                errs.append("action: method %r not declared on %s"
                            % (method_name, cls_name))
            else:
                errs.append("action: method %r not declared on any service/repository"
                            % method_name)

    # --- assertion @refs ---
    assertion = test.get("assertion", "")
    if not isinstance(assertion, str) or not assertion.strip():
        errs.append("assertion: missing or empty (requirement not testable)")
    else:
        for m in re.finditer(r"@([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?",
                             assertion):
            handle = m.group(1)
            field = m.group(2)
            if handle not in seen_refs:
                errs.append("assertion: unknown @%s" % handle)
            elif field and field != "id":
                row = next((r for r in setup if r.get("ref") == handle), None)
                if row is not None:
                    ent = entities.get(row.get("entity"))
                    if ent is not None and field not in {f["name"] for f in ent.get("fields", [])}:
                        errs.append("assertion: field %r not on entity %s"
                                    % (field, row.get("entity")))

    # --- assertion result.<field> ---
    # `result` is the action's return. If the design declares a scalar/entity
    # return, verify no hallucinated attribute access on it.
    result_fields = set()
    return_type = ""
    for obj in design_spec.get("services", []) + design_spec.get("repositories", []):
        if cls_name and obj.get("class") != cls_name:
            continue
        for m in obj.get("methods", []):
            if m.get("name") == method_name:
                return_type = m.get("returns", "") or ""
                break
    # An action that returns None cannot be dereferenced: `result.<field>` on a
    # None-returning method is a broken assertion (e.g. add_product -> None).
    if re.fullmatch(r"None|NoneType", return_type or "") and re.search(r"result\s*\.", assertion):
        errs.append("assertion: result.<field> on a None-returning method")
    # A returns like "Optional[Invoice]" / "Invoice" / "Dict[str, int]" → the
    # attribute name after `result.` must be a field on the entity if it is one.
    ent_name = re.search(r"Optional\[([A-Za-z_][A-Za-z0-9_]*)\]|^([A-Za-z_][A-Za-z0-9_]*)$",
                         return_type or "")
    if ent_name:
        e_name = ent_name.group(1) or ent_name.group(2)
        ent = entities.get(e_name)
        if ent is not None:
            result_fields = {f["name"] for f in ent.get("fields", [])}
        if result_fields:
            for m in re.finditer(r"result\.([A-Za-z_][A-Za-z0-9_]*)", assertion):
                if m.group(1) not in result_fields:
                    errs.append("assertion: result.%s not on entity %s"
                                % (m.group(1), e_name))

    # --- raises(...) must reference a declared exception ---
    declared_excs = {e.get("name") for e in design_spec.get("exceptions", [])}
    if declared_excs:
        for m in re.finditer(r"raises\(([A-Za-z_][A-Za-z0-9_]*)\)", assertion):
            exc_name = m.group(1)
            if exc_name not in declared_excs:
                errs.append("assertion: raises(%s) not a declared exception (declared: %s)"
                            % (exc_name, ", ".join(sorted(declared_excs))))

    # --- assertion must be valid Python (a JS-style expression is invalid) ---
    if isinstance(assertion, str) and assertion.strip():
        js = []
        if "&&" in assertion:
            js.append("'&&' (use 'and')")
        if "||" in assertion:
            js.append("'||' (use 'or')")
        if re.search(r"!(?!=)", assertion):
            js.append("'!' (use 'not')")
        if js:
            errs.append("assertion: invalid Python operator(s): %s" % ", ".join(js))
        else:
            try:
                ast.parse(_assertion_py_source(assertion), mode="eval")
            except SyntaxError as exc:
                errs.append("assertion: not valid Python: %s" % exc)

    # --- reject brittle exact-equality on a name/string-keyed result dict ---
    # `result == {<name>: ...}` pins the dict's key FORM (name vs id), which the
    # code may not match (e.g. stock_value_by_category keys by category id, not
    # name). Prefer checking the VALUES or a specific key via .get().
    m_eq = re.search(r"result\s*==\s*\{(.*?)\}\s*$", assertion or "", re.S)
    if m_eq:
        body = m_eq.group(1)
        name_keyed = bool(re.search(r"['\"][^'\"]*['\"]\s*:", body))
        field_keyed = False
        for km in re.finditer(
            r"@([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*:", body
        ):
            if km.group(2) != "id":
                field_keyed = True
                break
        if name_keyed or field_keyed:
            errs.append(
                "assertion: exact-equality on a dict pins an ambiguous key form "
                "(name vs id). Use `sum(result.values()) == ...` or "
                "`result.get(<id-key>) == ...` so the value invariant is checked "
                "without assuming the dict's key type."
            )

    return errs


# ---------------------------------------------------------------------------
# Pass 4: LLM semantic critic (prose vs prose)
# ---------------------------------------------------------------------------

_SEMANTIC_SYSTEM = (
    "You are a critical test reviewer. Given a REQUIREMENT (what must be true) "
    "and a TEST EXPECTATION (what the generated test checks, in prose), judge "
    "how faithfully the test verifies the requirement.\n\n"
    "verdict is one of:\n"
    "- fully: the test checks EXACTLY the invariant the requirement states.\n"
    "- partially: the test checks a related but weaker/different aspect — "
    "still useful, but not the full invariant.\n"
    "- does_not_verify: the test checks something unrelated, or contradicts "
    "the requirement.\n\n"
    "\"reason\" explains the verdict concisely. Output ONLY JSON "
    "{\"verdict\": \"fully|partially|does_not_verify\", \"reason\": \"...\"}."
)


def validate_expectation_semantic(requirement: dict, expectation: str,
                                  design_spec: dict | None = None,
                                  verbose: bool = False) -> tuple[str, str]:
    """Return ``(verdict, reason)`` from an LLM critic comparing the PROSE
    expectation against the PROSE requirement.

    ``verdict`` is one of ``fully``, ``partially``, ``does_not_verify``.
    ``fully``/``partially`` are accepted (a test is kept); ``does_not_verify``
    is rejected (triggers a repair).
    """
    user = (
        "REQUIREMENT:\n[%s] %s\n\nTEST EXPECTATION:\n%s\n\n"
        "Judge the test expectation against the requirement. "
        "Emit the verdict JSON now."
        % (requirement.get("requirement_id", "?"), requirement.get("text", ""),
           expectation)
    )
    messages = [
        {"role": "system", "content": _SEMANTIC_SYSTEM},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=semantic_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if isinstance(data, dict) and isinstance(data.get("verdict"), str):
            v = data["verdict"]
            if v not in ("fully", "partially", "does_not_verify"):
                v = "does_not_verify"
            return v, str(data.get("reason", ""))
        if verbose:
            print("    [expectation-critic] verdict retrying…")
    return "does_not_verify", "semantic critic failed to return a verdict"
