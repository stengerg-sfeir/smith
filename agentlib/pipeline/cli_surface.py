"""Deterministic CLI surface derivation from user intentions (Approach B).

The CLI command tree is derived from the SPEC text / extracted USER
INTENTIONS, then the service design is constrained to serve exactly that
surface with CLI-drivable (primitive-parameter) methods, and the CLI is
rendered deterministically. This replaces the independent LLM CLI design,
so the CLI and the service cannot diverge — the root cause of the
sanitizer dropping / stripping commands.

Priority (see CLI_FROM_INTENTS.md section 5):
1. If the spec names commands EXPLICITLY (``cli_command``), use them
   verbatim (parsed here).
2. Else derive the surface from the extracted user intentions (CRUD /
   search verbs over the designed entities).

This module is GENERATION-side (agentlib); it must never import from
``behavior_tests``.
"""
from __future__ import annotations

import re

from agentlib.config import LLM_MAX_TOKENS_LONG
from agentlib.llm.client import _json_complete
from agentlib.naming import _camel, _snake, _plural


# --- verb classification ----------------------------------------------------
# verb -> deterministic CRUD method-verb
_CRUD_VERBS = {
    "add": "add", "create": "add", "insert": "add",
    "list": "list", "view": "list", "show": "list", "display": "list",
    "fetch": "list", "read": "list", "get": "list", "retrieve": "list",
    "update": "update", "edit": "update", "modify": "update",
    "delete": "delete", "remove": "delete",
}

_SEARCH_VERBS = {"search", "query", "find"}

_VERB_RE = re.compile(
    r"\b(add|create|insert|list|view|show|display|fetch|read|get|retrieve|"
    r"update|edit|modify|delete|remove|search|query|find|report|export|"
    r"summary|aggregate|total)\b",
    re.IGNORECASE,
)

_STOP_TOKENS = {
    "python", "python3", "python3.10", "python3.11", "python3.12",
    "cli", "app", "main", "main.py", "cli.py", "click", "argparse",
    "--help", "-h",
}

_FLAG_NAME_RE = re.compile(r"(?:^|-)only$|(?:^|-)active$|(?:^|-)enabled$|low-only")


def _normalize_verb(v):
    v = (v or "").strip().lower()
    if v in _CRUD_VERBS:
        return _CRUD_VERBS[v]
    if v in _SEARCH_VERBS:
        return "search"
    if v in ("report", "export", "summary", "aggregate", "total"):
        return "report"
    return None


def _intent_entity(text, entities_by_class):
    """The designed entity an intention's text addresses, else None."""
    low = (text or "").lower()
    best_cls, best_len = None, -1
    for cls in entities_by_class:
        snake = _snake(cls)
        for tok in (snake, _plural(snake)):
            if tok in low and len(tok) > best_len:
                best_len = len(tok)
                best_cls = cls
    return entities_by_class.get(best_cls) if best_cls else None


_STOP_FALLBACK = {"a", "an", "the", "not", "be", "do", "go", "see", "make"}

def _intent_verb(text):
    """The primary verb of an intention, or None.

    First tries the known CRUD/search/report verbs. When none match (e.g. a
    state-transition spec: "can confirm an order", "can ship an order"),
    falls back to the verb right after "can"/"to" — so the derived surface
    still exposes ``confirm_order`` / ``ship_order`` / ``cancel_order``.
    """
    m = _VERB_RE.search(text or "")
    if m:
        v = _normalize_verb(m.group(1))
        if v:
            return v
    low = (text or "").lower()
    m2 = re.search(r"\b(?:can|to)\s+([a-z]+)\b", low)
    if m2:
        cand = m2.group(1)
        if cand not in _STOP_FALLBACK:
            return cand
    return None


# --- option derivation ------------------------------------------------------

def _field_option(f, required=False):
    ftype = f.get("type") or "str"
    name = f["name"]
    if ftype == "bool":
        return {
            "name": "--" + name.replace("_", "-"), "required": False,
            "type": "flag", "field": name,
        }
    if ftype == "int":
        return {
            "name": "--" + name.replace("_", "-"), "required": required,
            "type": "int", "field": name,
        }
    return {
        "name": "--" + name.replace("_", "-"), "required": required,
        "type": "str", "field": name,
    }


def _derive_options(verb, entity):
    """Options for a derived (non-explicit) command from the entity design."""
    fields = [
        f for f in (entity.get("fields") or [])
        if isinstance(f, dict) and f.get("name") and f["name"] != "id"
    ]
    if verb == "add":
        return [
            _field_option(f, required=not f.get("nullable"))
            for f in fields
            if not (f.get("auto") == "now" and f.get("type") in ("date", "datetime"))
        ]
    if verb == "list":
        lf = [
            s for s in (entity.get("list_filters") or [])
            if isinstance(s, dict) and s.get("param")
        ]
        if not lf:
            lf = [
                {"param": f["name"]} for f in fields
                if f["name"].endswith("_id")
                or f["name"] in ("status", "is_active", "active", "category")
            ]
        return [
            {"name": "--" + s["param"].replace("_", "-"), "required": False,
             "type": "str", "field": s["param"]}
            for s in lf
        ]
    if verb == "update":
        return (
            [{"name": "--id", "required": True, "type": "int", "field": "id"}]
            + [
                _field_option(f, required=False)
                for f in fields
                if not (f.get("auto") == "now" and f.get("type") in ("date", "datetime"))
            ]
        )
    if verb == "delete":
        return [{"name": "--id", "required": True, "type": "int", "field": "id"}]
    if verb == "bulk-update":
        # Bulk update: the rows to touch (multiple ids) + the fields to set.
        return [
            {"name": "--ids", "required": True, "type": "str", "field": "ids"},
        ] + [
            _field_option(f, required=False)
            for f in fields
            if not (f.get("auto") == "now" and f.get("type") in ("date", "datetime"))
        ]
    if verb == "search":
        # generic single search term; maps onto a designed service/search
        # parameter via the suffix rule (--term -> search_term)
        return [{"name": "--term", "required": True, "type": "str", "field": "term"}]
    # state-transition / domain verb (confirm, ship, cancel, approve, ...):
    # the operation is keyed by the entity id.
    return [{"name": "--id", "required": True, "type": "int", "field": "id"}]


def _crud_target(verb, ent_snake):
    if verb == "add":
        return "add_" + ent_snake
    if verb == "list":
        return "list_" + ent_snake
    if verb == "update":
        return "update_" + ent_snake
    if verb == "delete":
        return "delete_" + ent_snake
    return None


# --- LLM intention -> (entity, operation) classification --------------------

def _intent_ops_schema():
    return {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "intent_id": {"type": "string"},
                        "entity": {"type": "string"},
                        "operation": {"type": "string"},
                    },
                    "required": ["intent_id", "entity", "operation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["mappings"],
        "additionalProperties": False,
    }


_INTENT_OPS_SYSTEM = (
    "You map user intentions to (entity, operation) pairs of the designed app.\n"
    "ENTITIES:\n%s\n\n"
    "For EACH intention, choose the ONE entity it addresses and the operation "
    "it performs.\n"
    "- entity: an entity name EXACTLY from the list above.\n"
    "- operation: a snake_case verb. For CRUD/aggregate use add, list, delete, "
    "update, report, total or summary. For a domain state-transition (confirm, "
    "ship, approve, cancel, restock, calculate, export, ...) use that verb. "
    "Never invent an entity; never use a phrase.\n"
    "Return one mapping per intention (same intent_id)."
)


def classify_intentions(intentions, entities_by_class, verbose=False):
    """LLM: classify each user intention into ``{intent_id, entity,
    operation}`` semantically.

    This is the semantic bridge that replaces the fragile regex ``_intent_entity``
    / ``_intent_verb``: the model reads the intention's natural language (e.g.
    "add a product to an invoice line") and picks the real entity (InvoiceLine)
    and a verb (add). The operation is an OPEN vocabulary — any domain verb is
    accepted; only the entity is constrained to the designed set.
    """
    if not entities_by_class:
        return []
    entity_lines = "\n".join("- %s" % e for e in sorted(entities_by_class))
    messages = [
        {"role": "system", "content": _INTENT_OPS_SYSTEM % entity_lines},
        {"role": "user", "content": "\n".join(
            "[%s] %s" % (it.get("intent_id", "?"), it.get("text", ""))
            for it in (intentions or [])
        )},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=_intent_ops_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if isinstance(data, dict) and isinstance(data.get("mappings"), list):
            out = []
            for m in data["mappings"]:
                if not isinstance(m, dict):
                    continue
                ent = m.get("entity")
                op = m.get("operation")
                if not isinstance(ent, str) or ent not in entities_by_class:
                    continue
                if not isinstance(op, str) or not op.strip():
                    continue
                op = re.sub(r"[\s-]+", "_", op.strip().lower())
                if not op or not re.fullmatch(r"[a-z][a-z0-9_]*", op):
                    continue
                out.append({
                    "intent_id": m.get("intent_id"),
                    "entity": ent,
                    "operation": op,
                })
            return out
        if verbose:
            print("    [intent-ops] retrying…")
    return []


def derive_cli_from_intents(classified, entities_by_class, verbose=False):
    """Mechanically derive a CLI command design from LLM-classified
    ``(entity, operation)`` pairs.

    This is NOT a vocabulary parser. It maps a structured ``(entity, op)`` pair
    to a command via a fixed rule table: CRUD/report ops get a rich shape
    (``add_<entity>`` + fields, ``list_<entity>`` + filters, ``get_<entity>_total``
    + id, ...); any OTHER operation (confirm, ship, approve, restock, ...) gets
    the generic state-transition shape ``<op>_<entity>(id)``. Options come from
    ``_derive_options`` which falls back to ``--id`` for unknown verbs.
    """
    if not entities_by_class:
        return None
    _CORE = {
        "add", "create", "insert", "list", "view", "show", "display",
        "delete", "remove", "update", "edit", "modify",
        "report", "export", "summary", "aggregate", "total", "search",
    }
    commands = []
    seen = set()
    for m in classified or []:
        ent = entities_by_class.get(m.get("entity"))
        if not isinstance(ent, dict):
            continue
        op = str(m.get("operation") or "").strip().lower()
        op = re.sub(r"[\s-]+", "_", op)
        if not op:
            continue
        ent_snake = _snake(ent["name"])
        # synonym normalization to the closed CRUD/report core
        if op in ("create", "insert"):
            op = "add"
        elif op in ("view", "show", "display"):
            op = "list"
        elif op in ("remove",):
            op = "delete"
        elif op in ("edit", "modify"):
            op = "update"
        elif op in ("summary", "aggregate", "export"):
            op = "report"
        key = "%s/%s" % (ent_snake, op)
        if key in seen:
            continue
        seen.add(key)
        options = _derive_options(op, ent)
        if op in ("add", "list", "update", "delete", "search"):
            target = _crud_target(op, ent_snake) or ("search_" + ent_snake if op == "search" else "%s_%s" % (op, ent_snake))
        elif op in ("report", "total"):
            target = "get_%s_%s" % (ent_snake, op)
        else:
            # domain state-transition verb -> <op>_<entity>(id)
            target = "%s_%s" % (op, ent_snake)
        commands.append({
            "group": [ent_snake],
            "name": op,
            "options": options,
            "target": target,
        })
    # Seeding floor: parent-add for FK options (same as derive_cli_surface).
    for c in list(commands):
        owner = next(
            (e for cls, e in entities_by_class.items() if _snake(cls) == c.get("group", [""])[0]),
            None,
        )
        if owner is None:
            continue
        for o in c.get("options") or []:
            if not isinstance(o, dict):
                continue
            field = o.get("field") or (o.get("name") or "").lstrip("-").replace("-", "_")
            if not (isinstance(field, str) and field.endswith("_id") and field != "id"):
                continue
            parent_cls = _camel(field[: -len("_id")])
            parent = entities_by_class.get(parent_cls)
            if not isinstance(parent, dict):
                continue
            parent_snake = _snake(parent_cls)
            if any(
                cmd.get("group") == [parent_snake] and cmd.get("name") == "add"
                for cmd in commands
            ):
                continue
            commands.append({
                "group": [parent_snake],
                "name": "add",
                "options": _derive_options("add", parent),
                "target": "add_" + parent_snake,
            })
    if not commands:
        return None
    return {"commands": commands}


# --- explicit command parsing -----------------------------------------------

def _parse_explicit_command(s):
    """Parse a verbatim command string into {group, name, options, target}.

    Handles common spellings:
      'product add --sku --name --category --price --stock'
      'product list [--category] [--low-only]'
      'product update --id [--name] [--price] [---category]'
      'python main.py product add ...'
    Bracketed options are optional (``required=False``); unbracketed ones are
    required.
    """
    s = (s or "").replace("---", "--")
    # tokenize with bracket-required state
    raw = []
    in_bracket = False
    for piece in re.split(r"(\[|\])", s):
        if piece == "[":
            in_bracket = True
            continue
        if piece == "]":
            in_bracket = False
            continue
        for tok in piece.split():
            if tok:
                raw.append((tok, not in_bracket))
    # strip interpreter / entry-point tokens
    while raw and raw[0][0].lower() in _STOP_TOKENS:
        raw.pop(0)
    if not raw:
        return None
    # find the verb token (first non-option token that normalizes as a verb)
    verb_idx = None
    for idx, (tok, _) in enumerate(raw):
        if tok.startswith("-"):
            break
        if _normalize_verb(tok) is not None:
            verb_idx = idx
            break
    if verb_idx is None:
        return None
    verb = _normalize_verb(raw[verb_idx][0])
    group = [t.lower() for t, _ in raw[:verb_idx] if not t.startswith("-")]
    options = []
    seen = set()
    for tok, req in raw[verb_idx + 1:]:
        if not tok.startswith("--"):
            continue
        oname = "--" + tok[2:].replace("_", "-")
        if oname in seen:
            continue
        seen.add(oname)
        otype = "flag" if _FLAG_NAME_RE.search(oname[2:]) else "str"
        options.append({
            "name": oname, "required": req, "type": otype, "field": "",
        })
    return {"group": group, "name": verb, "options": options, "target": ""}


def _enrich_explicit_options(command, entities_by_class):
    """Fill option ``field``/``type`` from the command's owning entity."""
    group = command.get("group") or []
    if not group:
        return
    owner = next(
        (ent for cls, ent in entities_by_class.items() if _snake(cls) == group[0]),
        None,
    )
    if owner is None:
        return
    fields = {}
    for f in owner.get("fields") or []:
        if isinstance(f, dict) and isinstance(f.get("name"), str):
            fields[f["name"]] = f
    for o in command.get("options") or []:
        if o.get("type") == "flag":
            continue
        key = (o.get("name") or "").lstrip("-").replace("-", "_")
        f = fields.get(key)
        if f is None:
            # bounded suffix: --category -> category_id
            f = next(
                (v for k, v in fields.items()
                 if k.startswith(key + "_") or k.endswith("_" + key)),
                None,
            )
        if f is None:
            continue
        o["field"] = f["name"]
        ftype = f.get("type") or "str"
        if ftype == "int":
            o["type"] = "int"
        elif ftype == "bool":
            o["type"] = "flag"


def _extract_explicit_commands(intentions, entities_by_class):
    """Parse verbatim ``cli_command`` strings into command designs."""
    commands = []
    seen = set()
    for intent in intentions or []:
        cc = (intent.get("cli_command") or "").strip()
        if not cc:
            continue
        parsed = _parse_explicit_command(cc)
        if parsed is None:
            continue
        key = "/".join(parsed["group"] + [parsed["name"]])
        if key in seen:
            continue
        seen.add(key)
        _enrich_explicit_options(parsed, entities_by_class)
        commands.append(parsed)
    return commands


# --- main derivation --------------------------------------------------------

def derive_cli_surface(intentions, prompt_text, entities_by_class,
                       verbose=False):
    """Deterministic CLI command surface from the prompt's user intentions.

    Returns ``{"commands": [...]}`` or ``None``. Handles BOTH the explicit-CLI
    case (verbatim ``cli_command`` strings) and the derived case (CRUD / search
    verbs over the designed entities).
    """
    if not entities_by_class:
        return None

    commands = _extract_explicit_commands(intentions, entities_by_class)
    if commands:
        return {"commands": commands}

    commands = []
    seen = set()
    for intent in intentions or []:
        text = (intent.get("text") or "").strip()
        entity = _intent_entity(text, entities_by_class)
        verb = _intent_verb(text)
        if entity is None or verb is None:
            continue
        ent_snake = _snake(entity["name"])
        # Multi-row operations: an intention that modifies MANY rows of an
        # entity ("bulk update", "multiple products") is a DISTINCT command
        # from the single-row CRUD verb — don't collapse it into the same
        # surface (prompt 35's bulk-update was deduped into product-update,
        # leaving I5/I6 unmapped).
        low = text.lower()
        is_bulk = bool(re.search(r"\b(bulk|multiple|many)\b", low))
        if is_bulk and verb in ("update", "modify"):
            verb = "bulk-update"
        key = "%s/%s" % (ent_snake, verb)
        if key in seen:
            continue
        seen.add(key)
        options = _derive_options(verb, entity)
        if verb == "bulk-update":
            target = "bulk_update_" + ent_snake
        elif verb in _CRUD_VERBS:
            target = _crud_target(_CRUD_VERBS[verb], ent_snake)
        elif verb == "search":
            target = "search_" + ent_snake
        elif verb in (_REPORT_VERBS if False else ("report", "export", "summary", "aggregate", "total")):
            target = "get_%s_report" % ent_snake
        else:
            # state-transition / domain verb -> <verb>_<entity>(id)
            target = "%s_%s" % (verb, ent_snake)
        commands.append({
            "group": [ent_snake],
            "name": verb,
            "options": options,
            "target": target,
        })
    # Seeding floor: any command that takes an FK option (--<parent>_id) needs
    # the parent entity to EXIST first. Without a <parent>-add command the
    # facade tester cannot seed it, so inserts into the child table fail with
    # "FOREIGN KEY constraint failed" (prompt 27's reservation-add needs
    # customer-add/room-add). Synthesize missing parent create commands.
    for c in list(commands):
        owner = next(
            (e for cls, e in entities_by_class.items() if _snake(cls) == c.get("group", [""])[0]),
            None,
        )
        if owner is None:
            continue
        for o in c.get("options") or []:
            if not isinstance(o, dict):
                continue
            field = o.get("field") or (o.get("name") or "").lstrip("-").replace("-", "_")
            if not (isinstance(field, str) and field.endswith("_id") and field != "id"):
                continue
            parent_cls = _camel(field[:-3])
            parent = entities_by_class.get(parent_cls)
            if not isinstance(parent, dict):
                continue
            parent_snake = _snake(parent_cls)
            if any(
                cmd.get("group") == [parent_snake] and cmd.get("name") == "add"
                for cmd in commands
            ):
                continue
            commands.append({
                "group": [parent_snake],
                "name": "add",
                "options": _derive_options("add", parent),
                "target": "add_" + parent_snake,
            })
    if not commands:
        return None
    return {"commands": commands}


def cli_surface_constraint(surface):
    """Human-readable design constraint for the service module.

    Appended to the service-design prompt so the LLM creates exactly the
    CLI-drivable methods the surface requires (primitive parameters, one
    method per command).
    """
    if not surface:
        return ""
    lines = [
        "THIS APPLICATION EXPOSES A COMMAND-LINE INTERFACE (click). Design the "
        "service methods to serve the surface below:",
        "- ONE method per command; the method name is that command's target.",
        "- Every parameter MUST be a PRIMITIVE (str/int/bool) or "
        "Optional[primitive]. NEVER accept a whole entity object as a "
        "parameter.",
        "- Option names map to the method's parameters by field name.",
        "- Use exactly the target names below.",
        "",
        "REQUIRED CLI SURFACE:",
    ]
    for c in surface.get("commands") or []:
        group = c.get("group") or []
        name = c.get("name") or ""
        target = c.get("target") or name
        opts = []
        for o in c.get("options") or []:
            otype = o.get("type") or "str"
            field = o.get("field") or (o.get("name") or "").lstrip("-").replace("-", "_")
            req = " (required)" if o.get("required") else ""
            opts.append("%s:%s%s" % (field, otype, req))
        cmd = "/".join(group + [name])
        lines.append("  %s -> %s(%s)" % (cmd, target, ", ".join(opts)))
    return "\n".join(lines)
