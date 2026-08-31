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
    "empty list).\n"
    "- Choose values that fit the option type (int options get integers, str "
    "get text). For id / reference options you may use small integers; the "
    "tester may substitute seeded ids later.\n"
    "- Use ONLY real command names and real flags/arguments from the facade. "
    "Never invent a command or a flag.\n"
    "- If several commands could fit, pick the one whose target/name best "
    "matches the intention's verbs and objects.\n"
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
        ref_ent = fk_by_param.get(field)
        if ref_ent:
            refs.append({"flag": flag, "entity": ref_ent})
            continue
        # Targeted-PK reference: update/delete/get, or a state transition
        # (confirm/ship/cancel/approve) of an already-seeded row. A non-create
        # command that targets an entity via any id-like option (--id,
        # --<entity>_id, or a real PK field) requires that entity to exist
        # first — the executor creates it, then substitutes the real id
        # (prompt 32's order-confirm/ship/cancel).
        if (target_entity and not create_style):
            id_like = (
                field in pk_by_entity.get(target_entity, [])
                or field == _snake(target_entity) + "_id"
                or field == "id"
            )
            if id_like:
                refs.append({"flag": flag, "entity": target_entity})
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

    parts = ["python3", entry]
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
    }


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

    for i in range(len(intentions)):
        if plans[i] is None:
            plans[i] = _unmapped(intentions[i], "mapping failed after repair")
    out = []
    for p in plans:
        assert p is not None
        out.append(p)
    return out


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
