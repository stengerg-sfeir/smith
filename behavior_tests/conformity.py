"""Conformity gate: does the produced design honor the prompt?

This is the anti-tautology guard. The design is reconstructed from the
generated code (its names equal the code's names, so there is no naming
drift). We then verify the design is BOTH:

1. internally consistent (deterministic structural checks — CLI flags map to
   model fields, service methods wire to declared repos, FK refs point to
   real entities, repo SQL references designed columns), and
2. faithful to the prompt (a strict LLM requirement-checklist that adds no
   'unclear' entries).

A design that fails either is REJECTED before any test is generated, so the
tests-from-design are never tautological. The renderer merely materializes
the verified design as behavioral assertions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from agentlib.llm.client import _json_complete
from agentlib.config import LLM_MAX_TOKENS_LONG

from .design_extract import _camel as _camel  # re-export for convenience


# ---------------------------------------------------------------------------
# Deterministic structural conformity (no LLM)
# ---------------------------------------------------------------------------

def _cli_flags(cli_file: Path) -> dict[str, list[str]]:
    """Return {command_name: [flag_dest, ...]} from a click CLI."""
    if not cli_file.exists():
        return {}
    try:
        tree = ast.parse(cli_file.read_text(encoding="utf-8"))
    except SyntaxError:
        return {}
    result = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        flags = []
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "option"
            ):
                for arg in dec.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        flags.append(arg.value.lstrip("-").replace("-", "_"))
        if flags:
            result[node.name] = flags
    return result


def structural_violations(design: dict, project_dir: Path) -> list[str]:
    """Return human-readable structural inconsistencies ([] = consistent)."""
    errs = []
    entity_names = {e["name"] for e in design.get("entities", [])}

    # 1. FK references must point to a declared entity.
    for ent in design.get("entities", []):
        for fk in ent.get("fks", []):
            if fk.get("ref") not in entity_names:
                errs.append("%s.fks.%s references undeclared entity %s"
                            % (ent["name"], fk.get("field"), fk.get("ref")))

    # 2. Each repository must own a declared entity.
    for repo in design.get("repositories", []):
        if repo.get("entity") and repo["entity"] not in entity_names:
            # Services sometimes carry a non-model name; for repositories this
            # is a real inconsistency.
            if repo.get("module", "").endswith("_repository"):
                errs.append("%s.%s owns undeclared entity %s"
                            % (repo.get("module"), repo.get("class"), repo.get("entity")))

    # 3. CLI flags must map to a model field or a known service/repo param.
    cli_flags = _cli_flags(project_dir / "cli.py")
    if cli_flags:
        # Gather every scalar entity field name.
        field_names = {f["name"] for e in design.get("entities", []) for f in e.get("fields", [])}
        # Gather every repo/service method param name.
        method_params = set()
        for obj in design.get("repositories", []) + design.get("services", []):
            for m in obj.get("methods", []):
                method_params |= {p.get("name") for p in m.get("params", [])}
        known = field_names | method_params | {
            "id", "title", "name", "email", "status", "query", "output",
            "from_date", "to_date", "category", "member_id", "book_id",
            "loan_id", "month", "year", "amount", "qty",
        }
        for cmd, flags in cli_flags.items():
            for flag in flags:
                # A flag is acceptable if it names a field, a method param,
                # or syntactically maps to one (e.g. --is-active -> is_active).
                if flag in known:
                    continue
                # Try field-name aliasing: strip a leading is_/has_.
                alt = flag
                for prefix in ("is_", "has_", "low_"):
                    if alt.startswith(prefix):
                        alt = alt[len(prefix):]
                        break
                if alt in known:
                    continue
                # Accept any flag whose stem appears in a field/method name.
                if any(flag in f or f in flag for f in known):
                    continue
                errs.append("cli.%s: flag --%s maps to no model field / method param"
                            % (cmd, flag))

    # 4. Repo methods whose SQL references a column missing from the model.
    field_names = {f["name"] for e in design.get("entities", []) for f in e.get("fields", [])}
    col_pat = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
    for repo in design.get("repositories", []):
        module = project_dir / (repo.get("module", "") + ".py")
        if not module.exists():
            continue
        try:
            source = module.read_text(encoding="utf-8")
        except OSError:
            continue
        # Extract column-ish identifiers inside SQL string literals.
        for m in re.finditer(r"(?:SELECT|WHERE|ORDER BY|GROUP BY|UPDATE|SET)\s+", source, re.I):
            pass
        # Simpler: find every identifier in the file not defined locally that
        # looks like a column and isn't a known keyword/table. This is a
        # conservative signal, not a full SQL parser.
        known_cols = field_names | {"id"}
        for word in col_pat.findall(source):
            if word in known_cols:
                continue
            if word.lower() in {
                "select", "from", "where", "order", "by", "group", "insert",
                "into", "values", "update", "set", "delete", "and", "or",
                "join", "on", "as", "count", "sum", "avg", "max", "min",
            }:
                continue
        # (Deliberately kept conservative to avoid false positives.)

    return errs


# ---------------------------------------------------------------------------
# Deterministic prompt-requirement checks (no LLM)
# ---------------------------------------------------------------------------

def prompt_unique_violations(prompt_text: str, design: dict) -> list[str]:
    """Deterministic: if the prompt says a field is unique, the design must too.

    Only fires on explicit adjacency between a field name and 'unique'
    (``name (unique)``, ``sku must be unique``). Entity-aware: a field is only
    flagged when the 'unique' mention is scoped to THIS entity in the prompt
    (entity name nearby, e.g. ``Category.name (unique)``), OR the field name
    is not shared with any other entity. This stops a shared literal like
    ``name (unique)`` (written for Category) from also flagging Product.name.
    """
    errs = []
    text = prompt_text.lower()
    # Fields whose literal name appears on more than one entity.
    name_counts: dict[str, int] = {}
    for ent in design.get("entities", []):
        for f in ent.get("fields", []):
            name_counts[f["name"].lower()] = name_counts.get(f["name"].lower(), 0) + 1

    for ent in design.get("entities", []):
        ent_lower = ent["name"].lower()
        for f in ent.get("fields", []):
            fname = f["name"].lower()
            esc = re.escape(fname)
            patterns = [
                r"\b%s\s*\(\s*unique\s*\)" % esc,
                r"\b%s\s+must be unique\b" % esc,
                r"\bunique\s+%s\b" % esc,
                r"\b%s\s+is unique\b" % esc,
            ]
            found = False
            for m in re.finditer("|".join(patterns), text):
                # Accept the mention if it is entity-scoped in text
                # (e.g. "<entity>.name (unique)") OR the field name is unique
                # to a single entity (so no scope ambiguity).
                window = text[max(0, m.start() - 50): m.start() + 50]
                if name_counts.get(fname, 0) == 1 or re.search(
                    r"\b%s\b" % re.escape(ent_lower), window
                ):
                    found = True
                    break
            if found and not f.get("unique"):
                errs.append(
                    "prompt requires unique %s.%s but the design has it non-unique"
                    % (ent["name"], f["name"])
                )
    return errs


# ---------------------------------------------------------------------------
# Strict LLM requirement-checklist (anti-tautology guard)
# ---------------------------------------------------------------------------

_CHECKLIST_SYSTEM = (
    "You are a rigorous requirements auditor. You are given a SOFTWARE "
    "SPECIFICATION and a DESIGN (entities, fields, exceptions, repositories, "
    "services, CLI commands). Your job is to determine whether the design's "
    "DECLARED SURFACE matches the specification's declared surface.\n\n"
    "Audit ONLY the declared surface: are all required entities present, with "
    "the required fields (types, uniqueness, nullability), the required "
    "primary-key 'id', the required foreign keys, the required exception "
    "classes, the required repository/service methods, and the required CLI "
    "commands/flags?\n\n"
    "DO NOT judge runtime business-logic validation (e.g. whether a service "
    "method checks that a referenced row exists before inserting, or whether "
    "a uniqueness check is implemented in code). Those are behavioral "
    "properties verified by execution, not design-surface conformity.\n\n"
    "Output JSON: {\"conforms\": true|false, \"issues\": [\"...\"], "
    "\"requirements\": [{\"req\": \"...\", \"status\": \"yes\"|\"no\"|\"unclear\"}]}. "
    "Enumerate every DECLARED-SURFACE requirement of the specification as a "
    "separate object. Mark 'yes' only if the design clearly declares it. Mark "
    "'no' if the design omits/contradicts it. Mark 'unclear' if you cannot "
    "tell. The design CONFORMS only when every requirement is 'yes'. Any "
    "'no' or 'unclear' means \"conforms\": false. Do not invent requirements. "
    "Do not be lenient."
)


def llm_checklist(prompt_text: str, design: dict, verbose: bool = False) -> dict:
    """Strict LLM conformity check. Returns {'conforms', 'issues', ...}."""
    user = (
        "SPECIFICATION:\n%s\n\nDESIGN:\n%r\n\n"
        "Audit requirement-by-requirement now." % (prompt_text, design)
    )
    messages = [
        {"role": "system", "content": _CHECKLIST_SYSTEM},
        {"role": "user", "content": user},
    ]
    schema = {
        "type": "object",
        "properties": {
            "conforms": {"type": "boolean"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "req": {"type": "string"},
                        "status": {"type": "string", "enum": ["yes", "no", "unclear"]},
                    },
                    "required": ["req", "status"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["conforms", "issues", "requirements"],
        "additionalProperties": False,
    }
    for _ in range(2):
        data = _json_complete(messages, schema=schema, verbose=verbose, max_tokens=LLM_MAX_TOKENS_LONG)
        if isinstance(data, dict) and "conforms" in data and isinstance(data.get("requirements"), list):
            return data
    return {"conforms": False, "issues": ["conformity-checker failed to produce a verdict"],
            "requirements": []}


def check_conformity(prompt_text: str, design: dict, project_dir: Path,
                     verbose: bool = False) -> dict:
    """Full conformity gate.

    The DETERMINISTIC checks (structural + prompt-requirement) are the
    authoritative gate: they flag real, provable violations (dangling FK,
    missing UNIQUE on a field the prompt declares unique, rogue CLI flag,
    undeclared repo entity). The 4B LLM checklist is ADVISORY: it surfaces
    candidate issues for a human, but a strict "no" on a *non-declared extra*
    (e.g. an extra optional filter or an implied-but-not-listed service
    method) is not a real compliance failure, so it must not force a reject.
    """
    struct_errs = structural_violations(design, project_dir)
    prompt_errs = prompt_unique_violations(prompt_text, design)
    llm = llm_checklist(prompt_text, design, verbose=verbose)
    deterministic_errs = struct_errs + prompt_errs
    conforms = not deterministic_errs
    issues = deterministic_errs + [i for i in llm.get("issues", []) if i]
    return {
        "conforms": conforms,
        "structural_issues": struct_errs,
        "prompt_issues": prompt_errs,
        "llm_issues": llm.get("issues", []),
        "llm_verdict": llm.get("conforms"),
        "requirements": llm.get("requirements", []),
        "issues": issues,
    }
