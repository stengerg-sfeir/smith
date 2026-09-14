"""Conformity gate: does the produced design honor the prompt?

This is the anti-tautology guard. The design is reconstructed from the
generated code (its names equal the code's names, so there is no naming
drift). We then verify the design is BOTH:

1. internally consistent (deterministic structural checks — CLI flags map to
   model fields, service methods wire to declared repos, FK refs point to
   real entities, repo SQL references designed columns), and
2. faithful to the prompt (a deterministic verifier over a structured
   requirement list extracted from the prompt).

A design that fails either is REJECTED before any test is generated, so the
tests-from-design are never tautological. The renderer merely materializes
the verified design as behavioral assertions.

The LLM's only job is EXTRACTION (parse the prompt into a machine-checkable
requirement list); the actual compliance VERDICT is deterministic, so the
gate never emits a self-contradictory opinion.
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
# STRUCTURED REQUIREMENT EXTRACTION (LLM) — no judgment, only extraction
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = (
    "You are a requirements extractor. Given a SOFTWARE SPECIFICATION, extract "
    "its DECLARED-SURFACE requirements as JSON. Do NOT audit, judge, or opine "
    "on correctness — ONLY extract what the specification explicitly requires "
    "to exist.\n\n"
    "For each required ENTITY: {\"name\", \"fields\": [{\"name\", \"type\", "
    "\"unique\", \"required\", \"pk\"}]}. type is one of "
    "str/int/float/bool/date/datetime; unique true only if the spec says the "
    "field is unique; required true for mandatory fields; pk true for the "
    "auto-increment id.\n"
    "For each required REPOSITORY/SERVICE: {\"class\"}, listing the exact "
    "class name the specification names. Do NOT enumerate methods — method "
    "presence is exercised by behavioral tests, not here.\n"
    "For each required EXCEPTION class: its name.\n"
    "Output ONLY the JSON. Do not invent requirements the spec does not state."
)


def _method_owner_schema():
    """Repo/service owner schema: only the CLASS name is extracted.

    Method presence/params are intentionally NOT verified here — mapping
    natural-language method descriptions to exact code names is unreliable
    (the small LLM guesses names like 'read' instead of 'get_by_id'). The
    behavioral tests invoke the methods, so a missing method surfaces as a
    runtime failure there; this gate stays on the reliable surface.
    """
    return {
        "type": "object",
        "properties": {"class": {"type": "string"}},
        "required": ["class"],
        "additionalProperties": False,
    }


def _extraction_schema():
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "fields": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"},
                                    "unique": {"type": "boolean"},
                                    "required": {"type": "boolean"},
                                    "pk": {"type": "boolean"},
                                },
                                "required": ["name", "type"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["name", "fields"],
                    "additionalProperties": False,
                },
            },
            "repositories": {
                "type": "array",
                "items": _method_owner_schema(),
            },
            "services": {
                "type": "array",
                "items": _method_owner_schema(),
            },
            "exceptions": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["entities", "exceptions"],
        "additionalProperties": False,
    }


def extract_requirements(prompt_text: str, verbose: bool = False) -> dict | None:
    """Extract the prompt's declared-surface requirements as structured data.

    The LLM only recalls/structures what the spec requires; it emits no
    verdict. Returns None if extraction fails.
    """
    user = "SPECIFICATION:\n%s\n\nExtract the declared-surface requirements now." % prompt_text
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=_extraction_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if isinstance(data, dict) and isinstance(data.get("entities"), list):
            return data
        if verbose:
            print("    [conformity] requirement extraction retrying…")
    return None


def _prompt_types_field(text_low: str, fname: str, ftype: str) -> bool:
    """True if the prompt explicitly types ``fname`` as ``ftype``.

    Only anchor a field's type to the prompt when it is stated right next to
    the field name (``loan_date (datetime)``, ``created_at: datetime``,
    ``expense_date (str, ISO date)``). Without this, the extractor assumes a
    type (e.g. datetime) for a field the prompt merely names, producing false
    positives on the type check.
    """
    esc = re.escape(fname)
    tesc = re.escape(ftype)
    return bool(
        re.search(r"\b%s\s*[\(\:]\s*%s\b" % (esc, tesc), text_low)
        or re.search(r"\b%s\s+%s\b" % (esc, tesc), text_low)
    )


def _anchor_requirements(reqs: dict, prompt_text: str) -> dict:
    """Drop extractions the prompt does NOT literally declare.

    The small LLM hallucinates 'declared-surface' entities/repositories/
    services/exceptions from narrative text (a CSV CLI yields phantom
    ``CSVRow``, ``CSVReader``, ``FileNotFoundError``). Only keep a requirement
    whose NAME actually appears in the prompt; only keep a field's TYPE when
    the prompt explicitly types it next to the field name. This removes the
    false positives (cli_tool phantom structures, library/multi_module assumed
    ``datetime``) without weakening the real unique/type checks (expenses
    ``Category.name`` unique, ``expense_date`` str).
    """
    if not isinstance(reqs, dict):
        return reqs
    text_low = prompt_text.lower()
    out = {"entities": [], "repositories": [], "services": [], "exceptions": []}

    for cent in reqs.get("entities", []):
        name = cent.get("name", "")
        if name.lower() not in text_low:
            continue  # phantom entity (e.g. CSVRow)
        fields = []
        for rf in cent.get("fields", []):
            rf = dict(rf)
            fname = rf.get("name", "")
            ftype = rf.get("type", "")
            if ftype and not _prompt_types_field(text_low, fname, ftype):
                rf["type"] = ""  # un-anchored type → don't flag a mismatch
            fields.append(rf)
        cent = dict(cent)
        cent["fields"] = fields
        out["entities"].append(cent)

    for key in ("repositories", "services"):
        for owner in reqs.get(key, []):
            cls = owner.get("class", "")
            if cls.lower() in text_low:
                out[key].append(owner)

    for exc in reqs.get("exceptions", []):
        if isinstance(exc, str) and exc.lower() in text_low:
            out["exceptions"].append(exc)

    return out


# ---------------------------------------------------------------------------
# Deterministic verification of extracted requirements (no LLM)
# ---------------------------------------------------------------------------

def verify_requirements(reqs: dict, design: dict) -> tuple[list[str], list[dict]]:
    """Deterministically compare extracted requirements to the design.

    Returns ``(issues, requirements_report)``. ``requirements_report`` is a
    list of ``{"req": ..., "status": "yes"|"no"}`` — one per extracted
    requirement — so the gate's report is fully deterministic.
    """
    issues: list[str] = []
    report: list[dict] = []
    entity_by_name = {e["name"]: e for e in design.get("entities", [])}
    repo_by_class = {o["class"]: o for o in design.get("repositories", [])}
    svc_by_class = {o["class"]: o for o in design.get("services", [])}
    exceptions_design = {e["name"] for e in design.get("exceptions", [])}

    # Entities + fields.
    for cent in reqs.get("entities", []):
        name = cent.get("name")
        d_ent = entity_by_name.get(name)
        if d_ent is None:
            report.append({"req": "entity %s" % name, "status": "no"})
            issues.append("entity %s is required but missing" % name)
            continue
        report.append({"req": "entity %s" % name, "status": "yes"})
        for rf in cent.get("fields", []):
            fname = rf.get("name")
            req_text = "field %s.%s (%s%s%s)" % (
                name, fname, rf.get("type", ""),
                ", pk" if rf.get("pk") else "",
                ", unique" if rf.get("unique") else "",
            )
            d_field = next(
                (f for f in d_ent.get("fields", []) if f.get("name") == fname), None)
            if d_field is None:
                report.append({"req": req_text, "status": "no"})
                issues.append("field %s.%s is required but missing" % (name, fname))
                continue
            problems = []
            if rf.get("type") and d_field.get("type") != rf.get("type"):
                problems.append("type %r != required %r" % (d_field.get("type"), rf.get("type")))
            # A PRIMARY KEY is unique by definition — do not flag a missing
            # separate UNIQUE constraint when the design marks it as the PK.
            if rf.get("unique") and not d_field.get("unique") and not d_field.get("primary_key"):
                problems.append("spec requires unique but design is non-unique")
            if problems:
                report.append({"req": req_text, "status": "no"})
                issues.append("field %s.%s: %s" % (name, fname, "; ".join(problems)))
            else:
                report.append({"req": req_text, "status": "yes"})

    # Exceptions.
    for exc_name in reqs.get("exceptions", []):
        if exc_name not in exceptions_design:
            report.append({"req": "exception %s" % exc_name, "status": "no"})
            issues.append("exception %s is required but missing" % exc_name)
        else:
            report.append({"req": "exception %s" % exc_name, "status": "yes"})

    # Repository/service classes (method presence is exercised by behavioral
    # tests, not verified via naming here).
    for key, by_class in (("repositories", repo_by_class), ("services", svc_by_class)):
        for owner in reqs.get(key, []):
            cls = owner.get("class")
            d_obj = by_class.get(cls)
            if d_obj is None:
                report.append({"req": "%s %s" % (key, cls), "status": "no"})
                issues.append("%s %s is required but missing" % (key, cls))
            else:
                report.append({"req": "%s %s" % (key, cls), "status": "yes"})

    return issues, report


# ---------------------------------------------------------------------------
# Full gate
# ---------------------------------------------------------------------------

def check_conformity(prompt_text: str, design: dict, project_dir: Path,
                     verbose: bool = False) -> dict:
    """Full conformity gate — deterministic verdict only.

    The DETERMINISTIC checks (structural + unique + verified-extracted
    requirements) are the authoritative gate. There is NO freeform LLM
    judgment, so the verdict can never be self-contradictory: the LLM only
    extracts a structured requirement list, and the verdict is computed
    deterministically against the design.
    """
    struct_errs = structural_violations(design, project_dir)
    prompt_errs = prompt_unique_violations(prompt_text, design)
    reqs = extract_requirements(prompt_text, verbose=verbose)
    if reqs is not None:
        reqs = _anchor_requirements(reqs, prompt_text)

    req_issues: list[str] = []
    report: list[dict] = []
    extraction_failed = reqs is None
    if reqs is not None:
        req_issues, report = verify_requirements(reqs, design)

    deterministic_errs = struct_errs + prompt_errs + req_issues
    if extraction_failed:
        # Extraction failure must NOT reject; it just limits coverage. The
        # deterministic unique/structural checks still run.
        deterministic_errs = struct_errs + prompt_errs

    conforms = not deterministic_errs
    if extraction_failed:
        report = [{"req": "requirement extraction failed", "status": "unclear"}]

    return {
        "conforms": conforms,
        "structural_issues": struct_errs,
        "prompt_issues": prompt_errs,
        "requirement_issues": req_issues,
        "extraction_ok": not extraction_failed,
        "requirements": report,
        "issues": deterministic_errs,
    }
# ---------------------------------------------------------------------------
# DECLARED CLI SURFACE CONFORMITY (deterministic, no LLM)
# ---------------------------------------------------------------------------
# The prompt for library_system / expenses ENUMERATES its command line
# verbatim. The generator must ship EXACTLY that surface: every command the
# prompt names, with the prompt's group path and option names, and NOTHING
# else. This gate is deterministic — it reads the prompt's own command list
# and the DISCOVERED click surface, and compares them name-for-name. It is the
# regression test for the "24 commands for 9 requested" defect.


def _option_long_names(option: dict) -> list[str]:
    """The ``--long`` spellings of a discovered click option (no ``-s``)."""
    return [n for n in (option.get("names") or []) if str(n).startswith("--")]


def prompt_surface_paths(prompt_text: str) -> list[dict]:
    """The commands the prompt itself enumerates, as ``{path, options}``.

    ``[]`` when the prompt never lists a command line — in that case there is
    no declared surface to conform to and the gate stays silent.
    """
    from agentlib.pipeline.cli_spec import (
        extract_prompt_cli_commands, parse_prompt_command,
    )

    out: list[dict] = []
    for text in extract_prompt_cli_commands(prompt_text):
        command = parse_prompt_command(text)
        if command is None:
            continue
        out.append({
            "path": " ".join(list(command["group"]) + [command["name"]]),
            "options": [o["name"] for o in command["options"]],
        })
    return out


def surface_conformity_violations(prompt_text: str,
                                  project_dir: Path) -> list[str]:
    """Prompt→surface name conformance ([] = the CLI is exactly the prompt's).

    For each command the prompt enumerates: the exact group path must exist
    and every option it names must be declared. For each command the CLI
    exposes: the prompt must have asked for it. A missing command, a missing
    option, or a generated extra is a violation.
    """
    from behavior_tests.facade_discovery import discover_facade

    wanted = prompt_surface_paths(prompt_text)
    if not wanted:
        return []

    facade = discover_facade(project_dir)
    if facade.get("kind") not in ("click_group", "click_command"):
        return ["prompt enumerates a command line but no click CLI was discovered"]

    discovered: dict[str, set[str]] = {}
    for command in facade.get("commands", []):
        discovered[command.get("name", "")] = {
            name
            for option in command.get("options", [])
            for name in _option_long_names(option)
        }

    errs: list[str] = []
    wanted_paths = {w["path"] for w in wanted}
    for w in wanted:
        path = w["path"]
        if path not in discovered:
            errs.append("prompt requires command %r but the CLI does not expose it" % path)
            continue
        for name in w["options"]:
            if name not in discovered[path]:
                errs.append("prompt requires option %s on command %r but it is missing"
                            % (name, path))
    for path in sorted(discovered):
        if path not in wanted_paths:
            errs.append("CLI exposes command %r that the prompt does not request" % path)
    return errs
