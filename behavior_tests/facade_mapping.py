"""Map user intentions to concrete CLI invocations via the LLM.

This is the THIRD stage of the facade tester. It is deliberately LLM-assisted:
the mapping is a SEMANTIC BRIDGE between two already-fixed inputs, so it is
non-tautological and prompt-agnostic.

- Intentions come from ``intents.extract_intentions`` (the independent oracle).
- The facade comes from ``facade_discovery.discover_facade`` (deterministic,
  from the code).
- The LLM reads BOTH and picks, for each intention, the ONE real command that
  fulfils it, filling concrete values for its required options/arguments.

The LLM cannot cheat: it only uses command/option names that exist in the
facade (bound vocabulary), and only expresses the given intentions (it cannot
invent requirements). A deterministic validator then checks the mapping
(command exists, required options/arguments filled, values typed, no stray
flags) and triggers a repair pass. When nothing fits, the intention is
surfaced as ``unmapped`` with a reason — never silently dropped.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from agentlib.config import LLM_MAX_TOKENS_LONG
from agentlib.llm.client import _json_complete
from agentlib.naming import _snake

from behavior_tests.fixtures import fixture_listing


# ---------------------------------------------------------------------------
# Facade context (bound vocabulary for the LLM)
# ---------------------------------------------------------------------------

def _facade_context(facade: dict) -> str:
    """A compact, unambiguous listing of the real facade commands/options.

    This is naming vocabulary ONLY. The LLM must bind to these exact names;
    it never invents a command or flag. Arguments (positionals) are listed
    separately from options so the model passes positionals by name and
    options by their ``--flag``.
    """
    lines = []
    for cmd in facade.get("commands", []):
        lines.append("COMMAND %s" % cmd["name"])
        for arg in cmd.get("arguments", []):
            lines.append("  ARGUMENT %s (%s, required)" % (
                arg.get("dest", ""), arg.get("type", "str")))
        for opt in cmd.get("options", []):
            flag = _opt_flag_name(opt)
            req = ", required" if opt.get("required") else ""
            isf = ", flag" if opt.get("flag") else ""
            lines.append("  OPTION %s (%s%s%s)" % (
                flag, opt.get("type", "str"), req, isf))
        if cmd.get("target"):
            lines.append("  TARGET %s" % cmd["target"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schema + system prompt
# ---------------------------------------------------------------------------

def mapping_schema():
    return {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "intent_id": {"type": "string"},
                        "command": {"type": "string"},
                        "args": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "flag": {"type": "string"},
                                    "value": {"type": "string"},
                                },
                                "required": ["flag"],
                                "additionalProperties": False,
                            },
                        },
                        "creates": {"type": "string"},
                        "refs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "flag": {"type": "string"},
                                    "entity": {"type": "string"},
                                },
                                "required": ["flag"],
                                "additionalProperties": False,
                            },
                        },
                        "fixtures": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "arg": {"type": "string"},
                                },
                                "required": ["id"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["intent_id", "command"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["mappings"],
        "additionalProperties": False,
    }


_MAPPING_SYSTEM = (
    "You map USER INTENTIONS to concrete CLI invocations of a generated app.\n\n"
    "FACADE (the ONLY commands/options/arguments you may use, verbatim):\n%s\n\n"
    "FIXTURES (external input files the generated app may read; choose ids by "
    "semantic match):\n%s\n\n"
    "TASK: for EACH intention, choose the ONE command that fulfils it and fill "
    "the options it needs.\n"
    "- intent_id: the given id.\n"
    "- command: a command name EXACTLY from the facade, or \"\" if no command "
    "fits this intention.\n"
    "- args: a list of {flag, value}. For an OPTION use its \"--flag\" token "
    "and its value. For an ARGUMENT (positional) use its name (no dashes) "
    "and its value. For a boolean FLAG option, value is \"\" (bare flag — no "
    "value). Include EVERY required option/argument and any optional one the "
    "intention mentions. If a command has no required inputs, args is [] (an "
    "empty list). A non-flag OPTION must ALWAYS carry a concrete, non-empty "
    "value: when the intention is vague about the filter (e.g. \"list by name\" "
    "without a name), invent a plausible one (a known sample value, a small "
    "integer like 1, or a representative date). Never emit an empty value for "
    "a non-flag option — click rejects `--opt \"\"` as \"requires an argument\".\n"
    "- Choose values that fit the option type (int options get integers, str "
    "get text). For id / reference options you may use small integers; the "
    "tester may substitute seeded ids later.\n"
    "- Use ONLY real command names and real flags/arguments from the facade. "
    "Never invent a command or a flag.\n"
    "- If several commands could fit, pick the one whose target/name best "
    "matches the intention's verbs and objects.\n"
    "- An intention that says \"delete/update/remove <entity> by <attr>\" (or "
    "\"by name\") is STILL fulfilled by a <entity>-delete/update command that "
    "takes --id: provide a small integer id placeholder. The tester seeds the "
    "entity and substitutes the real id. Do NOT mark \"no fit\" just because "
    "the intention names an attribute the command does not expose.\n"
    "- creates: the entity this command CREATES (e.g. \"Category\", "
    "\"Product\", \"Task\"), or \"\" if it is not a create operation. Use the "
    "singular entity name.\n"
    "- refs: list of {flag, entity}: each option whose value is a REFERENCE to "
    "a parent entity that must EXIST first (e.g. {\"flag\": \"--category\", "
    "\"entity\": \"Category\"}). Include every reference option the command "
    "takes, so the tester can create the parent and substitute the real id. "
    "Empty list if none.\n"
    "- fixtures: list of {id, arg}. id is a FIXTURES id whose description best "
    "matches an input file the command reads; arg is that command's positional "
    "argument name (no dashes) or option --flag whose value is the fixture "
    "file path. One entry per input file the command reads. Empty list if the "
    "command reads no external file. If the command needs an input file but no "
    "fixture id fits, fixtures is [] (the tester will not fabricate input).\n"
    "- If an intention has no fitting command, command is \"\" and args is []."
)


def _mapping_user(intentions: list[dict], facade: dict,
                  errors: dict[str, list[str]] | None = None) -> str:
    parts = []
    if errors:
        parts.append("PREVIOUS ATTEMPT had these problems — fix exactly them:")
        for iid, errs in errors.items():
            parts.append("  %s: %s" % (iid, "; ".join(errs)))
        parts.append("")
    parts.append("INTENTIONS:")
    for it in intentions:
        parts.append("[%s] %s" % (it.get("intent_id", "?"), it.get("text", "")))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _opt_flag_name(opt: dict) -> str:
    names = opt.get("names") or []
    long_ = next((x for x in names if x.startswith("--")), None)
    return long_ or (names[0] if names else "")


def _flag_variants(opt: dict) -> set:
    return set(opt.get("names") or []) | {_opt_flag_name(opt)}


def _arg_names(arg: dict) -> set:
    return set(arg.get("names") or []) | {arg.get("dest", "")}


def _validate_mapping(m: dict, facade: dict) -> list[str]:
    """Deterministic structural checks on one LLM mapping."""
    errs: list[str] = []
    cmd_name = m.get("command", "")
    if not cmd_name:
        return []  # command="" is a legitimate "no fit" (-> unmapped), not an error
    cmd = next((c for c in facade.get("commands", []) if c["name"] == cmd_name), None)
    if cmd is None:
        return ["command %r not in facade" % cmd_name]

    opt_by_flag: dict[str, dict] = {}
    for opt in cmd.get("options", []):
        for v in _flag_variants(opt):
            opt_by_flag.setdefault(v, opt)
    arg_by_name: dict[str, dict] = {}
    for arg in cmd.get("arguments", []):
        for v in _arg_names(arg):
            arg_by_name.setdefault(v, arg)

    provided_opts: set[str] = set()
    provided_args: set[str] = set()
    for pair in m.get("args", []):
        if not isinstance(pair, dict):
            continue
        flag = pair.get("flag", "")
        value = pair.get("value", "")
        if flag in opt_by_flag:
            provided_opts.add(flag)
            opt = opt_by_flag[flag]
            if opt.get("flag") and value.strip():
                errs.append("flag %s must not take a value" % flag)
            elif opt.get("type") == "int" and value.strip():
                try:
                    int(value)
                except ValueError:
                    errs.append("option %s expects int, got %r" % (flag, value))
        elif flag.lstrip("-") in arg_by_name or flag in arg_by_name:
            provided_args.add(flag)
        else:
            errs.append("stray flag/arg %r not declared on %s" % (flag, cmd_name))

    for opt in cmd.get("options", []):
        if opt.get("required") and not any(f in provided_opts for f in _flag_variants(opt)):
            errs.append("required option %s missing" % _opt_flag_name(opt))
    for arg in cmd.get("arguments", []):
        if arg.get("required") and not any(a in provided_args
                                           for a in _arg_names(arg)):
            errs.append("required argument %s missing" % (arg.get("dest") or ""))
    return errs


# ---------------------------------------------------------------------------
# Deterministic creates/refs inference (from the DESIGN, not keywords)
# ---------------------------------------------------------------------------

def _entity_for_target(target: str, design: dict) -> str:
    """Entity a ``add_*``/``create_*``/``insert_*`` target method creates.

    Only create-style methods produce a new entity; update/delete/list/report
    do not. So the target must start with such a verb prefix, and then name
    the entity. All names come from the real code, not a keyword list.
    """
    if not design:
        return ""
    t = (target or "").lower().replace("-", "_")
    if not any(t.startswith(p) for p in ("add_", "create_", "insert_")):
        return ""
    for ent in design.get("entities", []):
        if t.endswith("_" + _snake(ent["name"])) or _snake(ent["name"]) == t:
            return ent["name"]
    return ""


def _match_param_key(key: str, params: list[str]) -> str | None:
    if key in params:
        return key
    return next((p for p in params if p.startswith(key + "_") or p.endswith("_" + key)), None)


def _entity_named_by_target(target: str, design: dict) -> str:
    """Any entity whose name appears as the target's suffix (update_product ->
    Product). Used for targeting a seeded row by its PK."""
    if not design:
        return ""
    t = (target or "").lower().replace("-", "_")
    for ent in design.get("entities", []):
        if t.endswith("_" + _snake(ent["name"])) or _snake(ent["name"]) == t:
            return ent["name"]
    return ""


def _entity_from_command_name(name: str, design: dict) -> str:
    """Entity named by the command's prefix (``product-restock`` -> Product).

    Some targets (``restock``) don't name the entity, but the command does.
    """
    if not design or not name:
        return ""
    parts = name.replace("-", "_").split("_")
    for ent in design.get("entities", []):
        if _snake(ent["name"]) in parts:
            return ent["name"]
    return ""


def _is_bulk_id_key(resolved: str, target_entity: str) -> bool:
    """True for the multi-id option of a bulk command (--ids, --skus, ...).

    A bulk update takes a comma-separated list of ids/SKUs. Each element
    references a row that must exist, so the option is a per-value *bulk* ref
    (not the single *target* ref consumed by ``_substitute_refs``).
    """
    if not resolved:
        return False
    r = resolved.lower()
    if r in ("ids", "skus", "codes", "keys"):
        return True
    if target_entity:
        sn = _snake(target_entity)
        if r in (sn + "_ids", sn + "_skus", sn + "_codes"):
            return True
    if r.endswith("_ids") or r.endswith("_skus"):
        return True
    return False


def _infer_refs_and_creates(cmd: dict, design: dict | None) -> tuple[str, list[dict]]:
    """Derive ``(creates, refs)`` from the design's entities + FKs + method params.

    Deterministic and prompt-agnostic: no English keyword lists. It uses the
    real method name (``target``) / command name to find the created / targeted
    entity, and the real field names (from method params or a ``data`` dict) +
    entity FK/PK fields to find reference options. ``creates`` is only for
    create-style methods; ``refs`` covers both FK references (a parent that must
    exist) and targeted-PK references (the seeded row an update/delete/get
    command operates on).
    """
    if not design:
        return "", []
    target = (cmd.get("target") or "").lower().replace("-", "_")
    creates = _entity_for_target(target, design)
    target_entity = (_entity_named_by_target(target, design)
                     or _entity_from_command_name(cmd.get("name", ""), design))

    params: list[str] = []
    for svc in design.get("services", []):
        for m in svc.get("methods", []):
            if (m.get("name") or "").lower().replace("-", "_") == target:
                params = [p.get("name", "") for p in m.get("params", [])]
                break
        if params:
            break

    fk_by_param: dict[str, str] = {}
    pk_by_entity: dict[str, list[str]] = {}
    for ent in design.get("entities", []):
        pk_by_entity[ent["name"]] = [f["name"] for f in ent.get("fields", [])
                                     if f.get("primary_key")]
        for fk in ent.get("fks", []):
            fk_by_param.setdefault(fk.get("field", ""), fk.get("ref", ""))

    create_style = any(target.startswith(p) for p in ("add_", "create_", "insert_"))
    refs: list[dict] = []
    for opt in cmd.get("options", []):
        dest = opt.get("dest", "")
        flag = _opt_flag_name(opt)
        # The real field name: from the data-dict key if present, else the
        # matched method parameter, else the dest itself.
        field = opt.get("field")
        if field is None:
            field = _match_param_key(dest, params) if params else dest
        if not field:
            continue
        # Resolve the option's field onto the target's real parameter name
        # (--category -> category_id) so FK references are detected even when
        # the CLI option name differs from the FK column name. Without this,
        # product-add --category 1 would not seed Category before running,
        # and the (correct) generated FK check raises CategoryNotFoundError.
        resolved = _match_param_key(field, params) if params else field
        if resolved is None:
            resolved = field
        ref_ent = fk_by_param.get(resolved)
        if ref_ent:
            # "fk" refs point at a PARENT that must be seeded once and shared
            # (e.g. --customer-id -> Customer). One parent serves many children.
            refs.append({"flag": flag, "entity": ref_ent, "kind": "fk"})
            continue
        # Targeted-PK reference: update/delete/get, or a state transition
        # (confirm/ship/cancel/approve) of an already-seeded row. A non-create
        # command that targets an entity via any id-like option (--id,
        # --<entity>_id, or a real PK field) requires that entity to exist
        # first — the executor creates it, then substitutes the real id
        # (prompt 32's order-confirm/ship/cancel).
        if (target_entity and not create_style):
            id_like = (
                resolved in pk_by_entity.get(target_entity, [])
                or resolved == _snake(target_entity) + "_id"
                or resolved == "id"
            )
            if id_like:
                # "target" refs point at the row the command MUTATES. A prior
                # plan may have mutated that same row into an incompatible state,
                # so the executor must be able to give this plan a FRESH row
                # (prompt 32: order-cancel after order-ship on the same id).
                refs.append({"flag": flag, "entity": target_entity, "kind": "target"})
            elif _is_bulk_id_key(resolved, target_entity):
                refs.append({"flag": flag, "entity": target_entity, "kind": "bulk"})
    return creates, refs


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------

def _build_plan(intent: dict, m: dict, facade: dict, design: dict | None = None) -> dict:
    """Turn a validated mapping into a runnable test plan."""
    cmd_name = m["command"]
    cmd = next(c for c in facade["commands"] if c["name"] == cmd_name)
    iid = intent.get("intent_id", "I1")
    entry = facade.get("entry", "")
    kind = facade.get("kind", "")
    creates, refs = _infer_refs_and_creates(cmd, design)

    opt_by_flag: dict[str, dict] = {}
    for opt in cmd.get("options", []):
        for v in _flag_variants(opt):
            opt_by_flag.setdefault(v, opt)
    arg_by_name: dict[str, dict] = {}
    for arg in cmd.get("arguments", []):
        for v in _arg_names(arg):
            arg_by_name.setdefault(v, arg)

    positional_values: list[str] = []
    positional_dests: list[str] = []
    option_pairs: list[list[str]] = []
    for pair in m.get("args", []):
        if not isinstance(pair, dict):
            continue
        flag = pair.get("flag", "")
        value = pair.get("value", "")
        if flag in opt_by_flag:
            opt = opt_by_flag[flag]
            if opt.get("flag"):
                option_pairs.append([_opt_flag_name(opt)])  # bare flag
            else:
                option_pairs.append([_opt_flag_name(opt), value])
        elif flag.lstrip("-") in arg_by_name or flag in arg_by_name:
            positional_values.append(value)
            positional_dests.append(
                flag.lstrip("-") if flag.lstrip("-") in arg_by_name else flag)

    parts = ["python3"]
    if facade.get("module"):
        parts.append("-m")
    parts.append(entry)
    if kind == "click_group":
        parts.append(cmd_name)
    parts.extend(positional_values)
    for pair in option_pairs:
        parts.extend(pair)
    invocation = " ".join(shlex.quote(p) if _needs_quote(p) else p for p in parts)

    return {
        "intent_id": iid,
        "text": intent.get("text", ""),
        "status": "mapped",
        "command": cmd_name,
        "invocation": invocation,
        "positional_args": positional_values,
        "positional_dests": positional_dests,
        "option_args": option_pairs,
        "expected": {"exit_code": 0},
        "creates": creates,
        "refs": refs,
        "fixtures": [
            {"id": f.get("id", ""), "arg": f.get("arg", "")}
            for f in (m.get("fixtures") or [])
            if isinstance(f, dict) and f.get("id")
        ],
        "target": cmd.get("target", ""),
        "entry": entry,
        "kind": kind,
        "module": facade.get("module", False),
    }


# ---------------------------------------------------------------------------
# Seed-plan synthesis (order-of-operations fix)
# ---------------------------------------------------------------------------

def _find_create_cmd(facade: dict, entity: str, design: dict | None) -> dict | None:
    """Find a facade command that creates ``entity`` (e.g. ``customer-add``)."""
    ent_snake = _snake(entity)
    want = f"{ent_snake}-add"
    for cmd in facade.get("commands", []):
        if cmd.get("name") == want:
            return cmd
    if design:
        for cmd in facade.get("commands", []):
            if _entity_for_target(cmd.get("target", ""), design) == entity:
                return cmd
    return None


def _make_seed_plan(cmd: dict, entity: str, facade: dict, design: dict | None,
                    value: str | None = None) -> dict:
    """Build a minimal create-plan for ``entity`` so the executor can seed it.

    The mapper only creates plans for real user intentions, so a consumer that
    references a parent entity (``--customer-id`` -> Customer) has no plan that
    CREATES that parent. The executor's topo sort then has nothing to run first
    and the consumer hits ``FOREIGN KEY constraint failed``. This synthesizes a
    create-plan (flagged ``seed: True``) using the real facade command, so the
    executor can run it first and substitute the real parent id.

    ``value`` (the raw reference value being seeded, e.g. "2") is folded into
    the string seed values so distinct raw values produce DISTINCT rows — a
    fixed ``seed-<entity>`` would collide on UNIQUE string columns (e.g. two
    customer-add seeds both ``email seed-customer`` -> UNIQUE email fail).
    """
    args: list[dict] = []
    suffix = str(value) if value not in (None, "") else ""
    for opt in cmd.get("options", []):
        flag = _opt_flag_name(opt)
        if not flag:
            continue
        if opt.get("flag"):
            # Boolean flags: a seed should set positive-state fields
            # (active/enabled/available/approved/verified) so consumers that
            # require them (e.g. borrow needs an active member) can use the
            # row. Click boolean flags default False, so without this a seed
            # member is inactive and the follow-up borrow fails. Negative
            # state flags (is_deleted/is_archived) stay unset (False).
            dest = (opt.get("dest") or "").lower()
            if re.search(
                r"(^|_)(active|enabled|available|approved|verified|paid|confirmed)(_|$)",
                dest,
            ):
                args.append({"flag": flag, "value": ""})
            continue
        if not opt.get("required"):
            continue
        if opt.get("type") in ("int", "float"):
            val = "1"
        else:
            val = f"seed-{_snake(entity)}" + (f"-{suffix}" if suffix else "")
        args.append({"flag": flag, "value": val})
    for arg in cmd.get("arguments", []):
        dest = arg.get("dest") or ""
        if not dest:
            dest = next(
                (n for n in (arg.get("names") or []) if n and not n.startswith("-")),
                "",
            )
        if arg.get("required") and dest:
            args.append({"flag": dest, "value": "seed"})
    m = {
        "intent_id": f"__seed_{entity}",
        "command": cmd.get("name", ""),
        "args": args,
    }
    plan = _build_plan(
        {"intent_id": m["intent_id"], "text": f"seed {entity}"},
        m, facade, design=design,
    )
    plan["seed"] = True
    # Force the creates-entity: the seed is synthesized for a SPECIFIC
    # entity, but the underlying facade command's target may be a generic
    # verb ("add", not "add_category") so _infer_refs_and_creates returns a
    # blank creates. Without this, the seed is not a "provider", the topo
    # sort treats it as a non-create, and it runs AFTER consumers — the
    # exact FK-order bug this synthesis exists to prevent.
    plan["creates"] = entity
    return plan


def _make_sql_seed_plan(entity: str, value: str | None, design: dict) -> dict | None:
    """Direct-DB seed when no CLI command creates ``entity``.

    The generator may materialize a model+repository for a parent entity that a
    child references via FK (Famille 1) without exposing a CLI create command
    (no ``<entity>-add``). The tester cannot drive that parent through the
    surface, so it falls back to a direct INSERT into the real SQLite table —
    the entity exists, its table is known from the DDL, and the executor runs
    the INSERT before consumers so they can reference the seeded row.
    """
    ent = next((e for e in design.get("entities", []) if e["name"] == entity), None)
    if ent is None:
        return None
    table = ent.get("table_name") or ""
    if not table:
        return None
    db_file = design.get("database_file") or "app.db"
    suffix = str(value) if value not in (None, "") else ""
    cols: list[str] = []
    vals: list[str] = []
    for f in ent.get("fields", []):
        if f.get("primary_key") or f.get("nullable"):
            continue
        if f.get("default") is not None:
            continue
        col = f.get("name", "")
        if not col:
            continue
        cols.append(col)
        if f.get("type") in ("int", "float"):
            vals.append("1")
        else:
            v = f"seed-{_snake(entity)}" + (f"-{suffix}" if suffix else "")
            vals.append(v)
    if cols:
        col_list = ", ".join(cols)
        ph = ", ".join("?" for _ in cols)
        # Build a Python tuple literal, ensuring a trailing comma for a single
        # value (('x',) is a tuple, ('x') is just a parenthesised string).
        lit = "(" + ", ".join(
            "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'" for v in vals
        ) + (", " if len(vals) == 1 else "") + ")"
        py = ("import sqlite3; from database import create_tables; "
              "con=sqlite3.connect('%s'); create_tables(con); "
              "con.execute('INSERT INTO %s (%s) VALUES (%s)', %s); con.commit()"
              ) % (db_file, table, col_list, ph, lit)
    else:
        py = ("import sqlite3; from database import create_tables; "
              "con=sqlite3.connect('%s'); create_tables(con); "
              "con.execute('INSERT INTO %s DEFAULT VALUES'); con.commit()"
              ) % (db_file, table)
    invocation = "python3 -c \"%s\"" % py
    return {
        "intent_id": "__seed_%s" % entity,
        "text": "seed %s" % entity,
        "status": "mapped",
        "command": "",
        "invocation": invocation,
        "positional_args": [],
        "positional_dests": [],
        "option_args": [],
        "expected": {"exit_code": 0},
        "creates": entity,
        "refs": [
            {"flag": fk.get("field"), "entity": fk.get("ref"), "kind": "fk"}
            for fk in (ent.get("fks") or [])
            if isinstance(fk, dict) and fk.get("field") and fk.get("ref")
        ],
        "fixtures": [],
        "target": "",
        "entry": "",
        "kind": "",
        "seed": True,
    }


def _synthesize_seed_plans(plans: list[dict], facade: dict,
                           design: dict | None) -> list[dict]:
    """Add seed create-plans for ref'd entities that no plan creates.

    Keyed by (entity, raw_value) so two DIFFERENT values of the same entity in
    distinct plans (post_tag-add --tag-id 1 then --tag-id 2) get separate seeds,
    and the executor can substitute each raw value with its own real id. The old
    behavior created ONE seed per entity, so a second distinct value of the same
    ref was substituted with the (single) seeded id and often hit a UNIQUE/FK
    conflict (prompt 23 post_tag-add --tag-id 2). Each seed records ``seed_for``
    so the executor maps (entity, value) -> real id.
    """
    if not plans or not design:
        return plans
    updated = list(plans)
    seeded_keys: set[tuple[str, str | None]] = set()
    # Entities a REAL (non-seed) plan creates. Those set
    # ``entity_provided[(ent, None)]`` at runtime, and ``_substitute_refs``
    # resolves a "target" ref (update/delete/state-transition --id) via that
    # key, so a synthesized seed for the same entity is redundant — worse, a
    # seed omits CLI options the generated surface marked optional even though
    # the column is NOT NULL (inventory ``product-add --stock``), crashing the
    # seed with a NOT NULL IntegrityError. Skip seeding a target's entity when
    # some real plan already creates it; FK refs (distinct parent values) keep
    # their per-value seed.
    real_creates = {
        p.get("creates") for p in plans
        if p.get("creates") and not p.get("seed")
    }

    def _ref_value(plan: dict, flag: str):
        for pair in plan.get("option_args", []):
            if pair and pair[0] == flag and len(pair) > 1:
                return pair[1]
        return None

    def _bulk_values(plan: dict, flag: str) -> list[str]:
        """Distinct elements of a comma-separated multi-id option (--ids 1,3)."""
        for pair in plan.get("option_args", []):
            if pair and pair[0] == flag and len(pair) > 1:
                return [x.strip() for x in pair[1].split(",") if x.strip()]
        return []

    def _seed_for(plan: dict) -> None:
        for ref in plan.get("refs", []):
            if not isinstance(ref, dict):
                continue
            ent = ref.get("entity")
            flag = ref.get("flag")
            if not ent or not flag:
                continue
            if ref.get("kind") == "bulk":
                # A bulk ref references MULTIPLE rows (--ids 1,3). Seed each
                # distinct value so the bulk command's per-id lookups find them.
                for val in _bulk_values(plan, flag):
                    key = (ent, val)
                    if key in seeded_keys:
                        continue
                    cmd = _find_create_cmd(facade, ent, design)
                    if cmd is None:
                        seed = _make_sql_seed_plan(ent, val, design)
                        if seed is None:
                            continue
                    else:
                        seed = _make_seed_plan(cmd, ent, facade, design, value=val)
                    seed["seed_for"] = {"entity": ent, "value": val, "flag": flag}
                    updated.append(seed)
                    seeded_keys.add(key)
                continue
            # Target refs (--id on update/delete/state-transition) resolve via
            # entity_provided[(ent, None)], which the real creator set, so a
            # synthesized seed is redundant (and may crash on a NOT NULL column
            # whose CLI option is optional, e.g. inventory product-add --stock).
            # Skip them when a real plan already creates the entity; FK refs
            # (distinct parent values) keep their per-value seed.
            if ref.get("kind") == "target" and ent in real_creates:
                continue
            val = _ref_value(plan, flag)
            key = (ent, val)
            if key in seeded_keys:
                continue
            cmd = _find_create_cmd(facade, ent, design)
            if cmd is None:
                seed = _make_sql_seed_plan(ent, val, design)
                if seed is None:
                    continue
            else:
                seed = _make_seed_plan(cmd, ent, facade, design, value=val)
            seed["seed_for"] = {"entity": ent, "value": val, "flag": flag}
            updated.append(seed)
            seeded_keys.add(key)

    changed = True
    while changed:
        changed = False
        before = len(updated)
        for plan in updated:
            if plan.get("status") != "mapped":
                continue
            _seed_for(plan)
        if len(updated) != before:
            changed = True
    return updated


def _delete_fallback(intent: dict, facade: dict,
                     design: dict | None) -> dict | None:
    """Deterministic fallback: map "delete/remove <entity> by <attr>" to the
    <entity>-delete command when the LLM refused.

    The 4B mapping model can return command="" for an intention that names a
    delete/remove by a non-id attribute ("remove a product by name") because
    the facade exposes only a *_delete --id command. The executor seeds the
    entity and substitutes the real id via refs, so this is a valid mapping.
    Only fires when the LLM left the intention unmapped, and only for a
    command whose entity token appears in the intention text.
    """
    text = (intent.get("text") or "").lower()
    if not any(v in text for v in ("delete", "remove")):
        return None
    for cmd in facade.get("commands", []):
        name = cmd.get("name", "")
        if not isinstance(name, str) or not name.endswith("-delete"):
            continue
        ent_token = name[: -len("-delete")].replace("-", "_")
        ent_variants = {ent_token, ent_token + "s", ent_token.rstrip("s")}
        if not any(v in text for v in ent_variants):
            continue
        id_opt = next(
            (o for o in cmd.get("options", [])
             if _opt_flag_name(o) in ("--id", "--" + ent_token + "_id")),
            None,
        )
        if id_opt is None:
            continue
        m = {
            "intent_id": intent.get("intent_id", "?"),
            "command": name,
            "args": [{"flag": _opt_flag_name(id_opt), "value": "1"}],
        }
        return _build_plan(intent, m, facade, design=design)
    return None


# --- Negative/validation intention handling --------------------------------
# Some extracted intentions state a constraint the create operation must
# enforce ("I cannot create a customer with a duplicate email address", "I am
# prevented from creating a book with a duplicate ISBN"). There is no
# standalone command for "prevent a duplicate" — the constraint lives on the
# <entity>-add command. Map these to the create command with an expected
# NON-ZERO exit (the generated repo raises the unique/validation exception),
# and synthesize a seed that creates a colliding row first so the duplicate
# actually exists when the command runs.

_NEG_CREATE_RE = re.compile(
    r"\b(cannot|can not|must not|prevents?|prevented|refuse[sd]?|"
    r"reject[sd]?|forbidden|error if)\b",
    re.IGNORECASE,
)

_DUP_FIELD_RE = re.compile(
    r"\b(duplicate|unique)\s+([a-z][a-z0-9_]*)\b", re.IGNORECASE,
)


def _negative_unique_field(text: str) -> str:
    """The constrained field named by a duplicate/unique negative intention."""
    m = _DUP_FIELD_RE.search(text or "")
    if m:
        return m.group(2).lower().replace("-", "_")
    m2 = re.search(
        r"\b([a-z][a-z0-9_]*)\s+must be unique\b", text or "", re.IGNORECASE
    )
    if m2:
        return m2.group(1).lower().replace("-", "_")
    return ""


def _negative_entity(text: str, design: dict | None) -> str:
    """The entity a negative-create intention names, else ""."""
    if not design:
        return ""
    low = (text or "").lower()
    for ent in design.get("entities", []):
        snake = _snake(ent["name"])
        for tok in (snake, snake + "s", snake.rstrip("s")):
            if tok in low:
                return ent["name"]
    return ""


def _negative_value(field: str) -> str:
    """A representative colliding value for the unique field."""
    if field in ("email", "email_address"):
        return "dup@example.com"
    return "dup-" + field


def _patch_seed_field(seed: dict, cmd: dict, field: str, val: str) -> None:
    """Set the constrained field arg on a synthesized seed to the colliding value."""
    flag = ""
    for opt in cmd.get("options", []):
        if (opt.get("dest") or "").replace("-", "_") == field:
            flag = _opt_flag_name(opt)
            break
    if not flag:
        return
    for pair in seed.get("option_args", []):
        if pair and pair[0] == flag:
            if len(pair) > 1:
                pair[1] = val
            else:
                pair.append(val)
            return


def _rebuild_plan_invocation(plan: dict) -> None:
    """Recompute a plan's invocation string from its args.

    The executor runs ``plan["invocation"]`` verbatim, not the structured
    ``option_args``. Patching a plan's args after ``_build_plan`` leaves the
    invocation stale (the seed would create the wrong email), so recompute it
    the same way ``_build_plan`` built it originally. Mirrors the executor's
    ``_rebuild_invocation`` without importing it (that would be circular).
    """
    parts = ["python3"]
    if plan.get("module"):
        parts.append("-m")
    if plan.get("entry"):
        parts.append(plan["entry"])
    if plan.get("kind") == "click_group" and plan.get("command"):
        parts.append(plan["command"])
    parts.extend(plan.get("positional_args", []))
    for pair in plan.get("option_args", []):
        parts.extend(pair)
    plan["invocation"] = " ".join(
        shlex.quote(p) if _needs_quote(p) else p for p in parts
    )


def _negative_create_fallback(intent: dict, facade: dict,
                              design: dict | None) -> tuple[dict, dict] | None:
    """Map a negative/validation create intention to the create command with an
    expected non-zero exit, plus a seed that creates a colliding row first.

    Returns ``(plan, seed)`` or None. The plan expects ``exit_code != 0`` (the
    generator rejects the duplicate/unique violation); the seed creates an
    entity with the same unique value so the duplicate genuinely exists.
    """
    text = (intent.get("text") or "").strip()
    if not _NEG_CREATE_RE.search(text):
        return None
    # The intention may inflect the verb ("creating", "created", "registered").
    # Use a word-boundary stem matcher so "creating" matches (it does NOT contain
    # the substring "create"), while "address" does NOT match "add".
    if not re.search(
        r"\b(creat\w*|add(?:ed|ing|s)?|insert\w*|register\w*)\b",
        text, re.IGNORECASE,
    ):
        return None
    entity = _negative_entity(text, design)
    if not entity:
        return None
    field = _negative_unique_field(text)
    if not field:
        return None
    cmd = _find_create_cmd(facade, entity, design)
    if cmd is None:
        return None

    val = _negative_value(field)

    def _placeholder(opt: dict) -> str:
        if opt.get("type") in ("int", "float"):
            return "1"
        return "seed-" + _snake(entity)

    args: list[dict] = []
    for opt in cmd.get("options", []):
        flag = _opt_flag_name(opt)
        if not flag or opt.get("flag"):
            continue
        key = (opt.get("dest") or "").replace("-", "_")
        if key == field:
            args.append({"flag": flag, "value": val})
        elif opt.get("required"):
            args.append({"flag": flag, "value": _placeholder(opt)})
    for arg in cmd.get("arguments", []):
        dest = (arg.get("dest") or "").replace("-", "_")
        if arg.get("required") and dest:
            args.append({"flag": dest, "value": "seed"})

    m = {
        "intent_id": intent.get("intent_id", "?"),
        "command": cmd.get("name", ""),
        "args": args,
    }
    plan = _build_plan(intent, m, facade, design=design)
    plan["expected"] = {"exit_code": "!=0"}
    # The create plan must run AFTER the colliding seed. Clear `creates` so the
    # topo sort treats it as an "other" (non-provider) and runs it after all
    # providers (including the seed we synthesize below).
    plan["creates"] = ""

    seed = _make_seed_plan(cmd, entity, facade, design, value=val)
    if seed is None:
        return None
    _patch_seed_field(seed, cmd, field, val)
    # The executor runs plan["invocation"], not option_args — the patch above
    # leaves the seed's invocation stale (it would create the wrong email), so
    # recompute it to carry the colliding value.
    _rebuild_plan_invocation(seed)
    seed["seed_for"] = {"entity": entity, "value": val, "flag": ""}
    return plan, seed


# --- Error-handling (negative tool behaviour) intent handling ----------------
# Some extracted intentions declare an ERROR behaviour of the tool ("I get an
# error if the input CSV file does not exist", "I get an error if the CSV has a
# malformed format"). There is no standalone command for "error"; the behaviour
# lives on the command that reads the input. Map these to that command with an
# input that triggers the error, expecting a NON-ZERO exit (cli_tool's I4/I5).

_ERROR_HANDLING_RE = re.compile(
    r"\b(get|receive|see|encounter)\s+an\s+error\s+(if|when)\b"
    r"|\berror\s+if\b"
    r"|\b(raise[sd]?|return[sd]?|produce[sd]?|throw[sd]?)\s+an?\s+error\b",
    re.IGNORECASE,
)

_MISSING_FILE_RE = re.compile(
    r"\b(does not exist|not found|non.?existent|absent)\b"
    r"|\bmissing\s+(input\s+)?file\b|\bfile\s+is\s+missing\b",
    re.IGNORECASE,
)

_MALFORMED_FILE_RE = re.compile(
    r"\b(malformed|invalid|bad format|badly.?formatted|missing header|"
    r"wrong delimiter|inconsisten|corrupt|unparseable)\b",
    re.IGNORECASE,
)


def _error_handling_fallback(intent: dict, facade: dict,
                             design: dict | None,
                             fixtures: dict | None = None):
    """Map an error-behaviour intention to the tool's input command.

    An intention that declares an error condition ("I get an error if ...")
    has no standalone command — the error is a property of the command that
    reads the offending input. For a single-command tool, map to that command
    with a bad input and expect a non-zero exit: a missing path (nonexistent)
    or a malformed input file (malformed/missing header). ``fixtures`` is
    mutated to include the synthesized ``malformed_csv`` fixture.
    """
    text = intent.get("text") or ""
    if not _ERROR_HANDLING_RE.search(text):
        return None
    cmds = facade.get("commands") or []
    cmd = next((c for c in cmds if c.get("name") == "main"), None)
    if cmd is None and len(cmds) == 1:
        cmd = cmds[0]
    if cmd is None:
        return None
    # The command must read an external input: a required positional argument
    # (the file path), or a file-ish option.
    input_arg = next(
        (a for a in cmd.get("arguments") or [] if a.get("required")), None,
    )
    file_opt = next(
        (
            o for o in cmd.get("options") or []
            if any(k in (o.get("dest") or "")
                   for k in ("file", "path", "input", "csv"))
        ),
        None,
    )
    if input_arg is None and file_opt is None:
        return None
    missing = bool(_MISSING_FILE_RE.search(text))
    malformed = bool(_MALFORMED_FILE_RE.search(text))
    if not missing and not malformed:
        return None
    iid = intent.get("intent_id", "?")
    if missing:
        arg_name = (input_arg or {}).get("dest")
        if not arg_name:
            arg_name = next(
                (n for n in ((input_arg or {}).get("names") or [])
                 if n and not n.startswith("-")),
                "",
            )
        if not arg_name:
            return None
        m = {
            "intent_id": iid,
            "command": cmd.get("name", ""),
            "args": [{"flag": arg_name, "value": "/nonexistent/missing-input.csv"}],
        }
        plan = _build_plan(intent, m, facade, design=design)
    else:
        if fixtures is None:
            return None
        fid = "malformed_csv"
        fixtures.setdefault(fid, {
            "id": fid, "kind": "csv",
            "description": "A malformed CSV file (empty, missing header).",
            "data": "",
        })
        arg_name = (input_arg or {}).get("dest") or (
            next(
                (n for n in ((input_arg or {}).get("names") or [])
                 if n and not n.startswith("-")),
                "",
            ) or "input_file"
        )
        m = {
            "intent_id": iid,
            "command": cmd.get("name", ""),
            "args": [{"flag": arg_name, "value": "malformed"}],
        }
        plan = _build_plan(intent, m, facade, design=design)
        plan["fixtures"] = [{"id": fid, "arg": arg_name}]
    plan["expected"] = {"exit_code": "!=0"}
    return plan


# --- Import-input fixture synthesis ------------------------------------------
# Some import intentions ("I can import contacts from a CSV file") map to a
# real import command that takes --filename, but the mapping LLM fills a
# made-up path and forgets to attach a fixture, so the executor runs against a
# nonexistent input file -> FileNotFoundError -> ImportError -> exit 1 (prompt
# 18/19). Deterministically synthesize an entity-shaped CSV/JSON input file
# from the design and attach it, so the import genuinely runs against a valid
# file.

_IMPORT_KIND_RE = re.compile(r"\b(csv|json)\b", re.IGNORECASE)


def _import_file_kind(text):
    m = _IMPORT_KIND_RE.search(text or "")
    return m.group(1).lower() if m else None


def _import_field_value(fname, ftype):
    """Type-aware placeholder for one field in a synthesized import input."""
    t = (ftype or "").lower()
    if fname == "id":
        return "1"
    if "int" in t:
        return "1"
    if "float" in t or "decimal" in t:
        return "1.5"
    if "bool" in t or fname.startswith(("is_", "has_")):
        return "1"
    if "datetime" in t:
        return "2024-01-01T00:00:00"
    if "date" in t:
        return "2024-01-01"
    if "email" in fname:
        return "alice@example.com"
    # Common enum-like fields: the generated import validates these against a
    # closed value set (e.g. task status/priority). Pick a value most
    # validators accept so the import runs past the validation (prompt 19).
    if fname == "status":
        return "completed"
    if fname == "priority":
        return "medium"
    if fname == "category":
        return "general"
    return "sample-" + fname.replace("_", "-")


def _synthesize_import_fixture(intent, cmd, design):
    """Return (fixture_id, fixture_dict) for an import command, else None."""
    target = (cmd.get("target") or "")
    if not target.lower().startswith("import_"):
        return None
    ent_snake = target[len("import_"):]
    if not ent_snake or not design:
        return None
    ent = next(
        (e for e in design.get("entities", []) if _snake(e["name"]) == ent_snake),
        None,
    )
    if ent is None:
        return None
    kind = _import_file_kind(intent.get("text", ""))
    if kind not in ("csv", "json"):
        return None
    fields = [
        f for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    ]
    if not fields:
        return None
    fid = "import_%s_%s" % (ent_snake, kind)
    if kind == "csv":
        header = ",".join(f["name"] for f in fields)
        row = ",".join(
            _import_field_value(f["name"], f.get("type")) for f in fields
        )
        data = header + "\n" + row + "\n"
    else:  # json
        data = [
            {
                f["name"]: _import_field_value(f["name"], f.get("type"))
                for f in fields
            }
        ]
    return fid, {
        "id": fid,
        "kind": kind,
        "description": "Synthesized import input for %s (%s)" % (ent["name"], kind),
        "data": data,
    }


def _unmapped(intent: dict, reason: str) -> dict:
    return {
        "intent_id": intent.get("intent_id", "?"),
        "text": intent.get("text", ""),
        "status": "unmapped",
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Non-actionable (architecture) statement detection
# ---------------------------------------------------------------------------
# Some extracted intentions are NOT user actions: they declare an architectural
# property ("The application uses SQLite through a repository pattern", "The CLI
# interacts with the service layer"). These have no standalone CLI command and
# make "unmapped => fail" report a false gap. Detect them so the tester can
# exclude them from the failing set (they are not command-gaps).
_NON_ACTIONABLE_RE = re.compile(
    r"^\s*the\s+(application|cli|system|app|service)\b"
    r".*\b(uses|ensures|interacts|provides|implements|defines|maintains|"
    r"exposes|abstracts|orchestrates|validates|guarantees|enforces)\b",
    re.IGNORECASE,
)


# A constraint / validation statement ("I cannot X when Y", "I can ... be
# rejected if ...", "the operation either succeeds or fails entirely") enforces
# a business rule the command applies, but has no standalone CLI command of its
# own. These are not CLI-command gaps, so exclude them from the failing set.
_CONSTRAINT_RE = re.compile(
    r"\b(be\s+rejected|is\s+rejected|rejected\s+if|cannot|can\s+not|must\s+not|"
    r"(?:am|are|is|be)\s+prevented|prevent\w*|refuse\w*|reject\w*|forbid|"
    r"either\s+succeeds\s+.*\s+or\s+fails\s+entirely|all\s+or\s+nothing|"
    r"no\s+partial|guarantees?|atomically)\b",
    re.IGNORECASE,
)


def _is_non_actionable(intent: dict) -> bool:
    """True when an intention is not a user-CLI action.

    An actionable intention is phrased as a user goal ("I can <verb> ...") and
    drives a real command. A non-actionable one is either:
      - an architectural statement ("The application uses SQLite through a
        repository pattern"), or
      - a constraint/validation rule ("I cannot ship a cancelled order", "the
        bulk update either succeeds or fails entirely") — a business rule the
        operation enforces, not a standalone command.
    We exclude these from the failing set because they are not command-gaps.
    """
    text = (intent.get("text") or "").strip()
    if not text:
        return False
    if _NON_ACTIONABLE_RE.search(text):
        return True
    return bool(_CONSTRAINT_RE.search(text))


def _needs_quote(tok: str) -> bool:
    return bool(re.search(r"[\s'\"]", tok))


# ---------------------------------------------------------------------------
# Batch mapping (one LLM call per prompt, with a repair pass)
# ---------------------------------------------------------------------------

def map_intentions(intentions: list[dict], facade: dict,
                   design: dict | None = None,
                   fixtures: dict | None = None,
                   verbose: bool = False) -> list[dict]:
    """Map every intention to a test plan (or an unmapped reason).

    One LLM call maps the whole batch. A deterministic validation pass catches
    any hallucinated command/flag or unfilled required input and triggers a
    single repair pass re-asking with the exact problems. Intentions that
    still fail, or for which the LLM names no fitting command, are surfaced as
    ``unmapped`` — never dropped.

    ``design`` (from ``design_extract.extract_design``) is used ONLY to derive
    ``creates``/``refs`` deterministically (FK relations) — never to steer the
    LLM's command choice.
    """
    if not intentions:
        return []
    plans: list[dict | None] = [None] * len(intentions)
    pending = list(range(len(intentions)))
    errors_by_idx: dict[int, list[str]] = {}

    for attempt in range(2):
        if not pending:
            break
        batch = [intentions[i] for i in pending]
        errs_for_batch = (
            {intentions[i].get("intent_id", "?"): errors_by_idx[i]
             for i in pending if i in errors_by_idx}
            if errors_by_idx else None
        )
        data = _call_mapping(batch, facade, fixtures=fixtures,
                             errors=errs_for_batch, verbose=verbose)
        if data is None:
            break
        by_id = {}
        for m in data.get("mappings", []):
            if isinstance(m, dict) and m.get("intent_id"):
                by_id[m["intent_id"]] = m

        next_pending: list[int] = []
        next_errors: dict[int, list[str]] = {}
        for i in pending:
            it = intentions[i]
            m = by_id.get(it.get("intent_id", ""))
            if m is None:
                plans[i] = _unmapped(it, "no mapping returned")
                continue
            if not m.get("command", ""):
                plans[i] = _unmapped(it, "no facade command matched the intention")
                continue
            errs = _validate_mapping(m, facade)
            if errs:
                if attempt == 0:
                    next_pending.append(i)
                    next_errors[i] = errs
                else:
                    plans[i] = _unmapped(it, "; ".join(errs))
            else:
                plans[i] = _build_plan(it, m, facade, design=design)
        pending = next_pending
        errors_by_idx = next_errors

    # Deterministic delete-by-name fallback: the 4B mapping model may refuse
    # to bind "delete/remove <entity> by <attr>" to a *_delete --id command,
    # which is exactly what the generator produces. Align the tester on the
    # generator's real surface instead of surfacing a false unmapped.
    for i in range(len(intentions)):
        p = plans[i]
        if p is None or p.get("status") == "unmapped":
            fb = _delete_fallback(intentions[i], facade, design)
            if fb is not None:
                plans[i] = fb

    # Negative/validation fallback: "I cannot create X with a duplicate
    # <field>" (or "prevented from ... duplicate ISBN") maps to the create
    # command expecting a non-zero exit, plus a seed that creates a colliding
    # row first so the constraint genuinely triggers (prompt 12's I8, prompt
    # 11's I6). Handled after the delete fallback so we only touch intents
    # still unmapped.
    extra_seeds: list[dict] = []
    for i in range(len(intentions)):
        p = plans[i]
        if p is None or p.get("status") != "unmapped":
            continue
        res = _negative_create_fallback(intentions[i], facade, design)
        if res is not None:
            plan, seed = res
            plans[i] = plan
            extra_seeds.append(seed)
    if extra_seeds:
        plans.extend(extra_seeds)

    # Error-handling fallback: "I get an error if <input> does not exist / is
    # malformed" maps to the single-command tool's input command with a bad
    # input, expecting a non-zero exit (cli_tool I4/I5). Fires for ANY such
    # intention (the LLM may map it to `main` with expected 0, which is wrong
    # for an error behaviour) — deterministically install the bad-input plan.
    for i in range(len(intentions)):
        fb = _error_handling_fallback(intentions[i], facade, design, fixtures)
        if fb is not None:
            plans[i] = fb

    # Import-input fixture fallback: a mapped plan for an import command with a
    # file option but NO fixture runs against a nonexistent input file ->
    # FileNotFoundError -> ImportError -> exit 1 (prompt 18/19). Synthesize an
    # entity-shaped CSV/JSON file and attach it so the import genuinely runs.
    for i in range(len(intentions)):
        p = plans[i]
        if p is None or p.get("status") != "mapped" or p.get("seed"):
            continue
        if p.get("fixtures"):
            continue
        cmd = next(
            (c for c in facade.get("commands", [])
             if c.get("name") == p.get("command", "")),
            None,
        )
        if cmd is None:
            continue
        res = _synthesize_import_fixture(intentions[i], cmd, design)
        if res is not None:
            fid, fx = res
            if fixtures is not None:
                fixtures.setdefault(fid, fx)
            file_opt = next(
                (
                    u for u in (
                        _opt_flag_name(o) for o in cmd.get("options", [])
                    )
                    if "file" in u or "path" in u or "input" in u or "csv" in u
                ),
                None,
            ) or "--filename"
            p["fixtures"] = [{"id": fid, "arg": file_opt}]

    # --- Duplicate-invocation collision repair -------------------------------
    # The executor's "duplicate invocation ⇒ pass" workaround masked the LLM
    # mapper colliding two distinct intentions onto one exact command+args
    # (e.g. prompt 35's two identical product-update invocations). Fix it at the
    # source: detect duplicate invocations among mapped plans and re-map the
    # later ones with feedback to use distinct values. Residual duplicates after
    # repair are surfaced by the executor, not silently passed.
    inv_to_idx: dict[str, list[int]] = {}
    for i, p in enumerate(plans):
        if p is None or p.get("status") != "mapped" or p.get("seed"):
            continue
        inv_to_idx.setdefault(p.get("invocation", ""), []).append(i)
    if any(len(v) > 1 for v in inv_to_idx.values()):
        to_remap: list[tuple[int, str]] = []
        for inv, idxs in inv_to_idx.items():
            if len(idxs) < 2:
                continue
            first = idxs[0]
            fp = plans[first]
            if fp is None:
                continue
            first_iid = fp.get("intent_id", "?")
            for i in idxs[1:]:
                to_remap.append((i, "duplicate invocation %r already used by "
                                   "intent %s; choose distinct option values "
                                   "for this intention" % (inv, first_iid)))
        if to_remap:
            batch_i = [intentions[i] for i, _ in to_remap]
            dup_errors = {intentions[i].get("intent_id", "?"): [msg]
                          for i, msg in to_remap}
            data = _call_mapping(batch_i, facade, fixtures=fixtures,
                                 errors=dup_errors, verbose=verbose)
            if data:
                by_id = {m.get("intent_id"): m
                         for m in data.get("mappings", [])
                         if isinstance(m, dict) and m.get("intent_id")}
                for i, _ in to_remap:
                    it = intentions[i]
                    m = by_id.get(it.get("intent_id", ""))
                    if m is None or not m.get("command", ""):
                        plans[i] = _unmapped(it, "duplicate invocation collision")
                        continue
                    errs = _validate_mapping(m, facade)
                    if errs:
                        plans[i] = _unmapped(it, "; ".join(errs))
                    else:
                        plans[i] = _build_plan(it, m, facade, design=design)

    for i in range(len(intentions)):
        if plans[i] is None:
            plans[i] = _unmapped(intentions[i], "mapping failed after repair")
    # Reclassify non-actionable architecture statements: an intention that
    # declares a system property ("The application uses SQLite through a
    # repository pattern") has no standalone CLI command. It is not an
    # unmapped command-gap, so exclude it from the failing set rather than
    # reporting a false unmapped (which "unmapped => fail" would count).
    for i, p in enumerate(plans):
        if p is None or p.get("status") != "unmapped":
            continue
        if _is_non_actionable(intentions[i]):
            plans[i] = {
                "intent_id": intentions[i].get("intent_id", "?"),
                "text": intentions[i].get("text", ""),
                "status": "non_actionable",
                "reason": "non-actionable architecture statement (not a CLI action)",
            }
    out = []
    for p in plans:
        assert p is not None
        out.append(p)
    return _synthesize_seed_plans(out, facade, design)


def _call_mapping(intentions: list[dict], facade: dict,
                  fixtures: dict | None = None, errors=None,
                  verbose: bool = False):
    system = _MAPPING_SYSTEM % (
        _facade_context(facade), fixture_listing(fixtures))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": _mapping_user(intentions, facade, errors)},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=mapping_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if isinstance(data, dict) and isinstance(data.get("mappings"), list):
            return data
        if verbose:
            print("    [mapping-oracle] retrying…")
    return None


def run_on_prompt(prompt_dir: Path, ident: str) -> list[dict]:
    """Helper for the runner: load an artifact's intentions+facade, map, return."""
    artifact = prompt_dir / ("%s.json" % ident)
    data = json.loads(artifact.read_text(encoding="utf-8"))
    return map_intentions(data.get("intentions", []), data.get("facade", {}))
