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
        if not flag or opt.get("flag"):
            continue  # boolean flags are never required by the surface
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
        "refs": [],
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

    def _seed_for(plan: dict) -> None:
        for ref in plan.get("refs", []):
            if not isinstance(ref, dict):
                continue
            ent = ref.get("entity")
            flag = ref.get("flag")
            if not ent or not flag:
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


def _unmapped(intent: dict, reason: str) -> dict:
    return {
        "intent_id": intent.get("intent_id", "?"),
        "text": intent.get("text", ""),
        "status": "unmapped",
        "reason": reason,
    }


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
