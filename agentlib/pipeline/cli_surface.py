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
``agentlib.bench``.
"""
from __future__ import annotations

import re

from agentlib.config import LLM_MAX_TOKENS_LONG, LLM_RETRY_TEMPERATURE
from agentlib.llm.client import _json_complete
from agentlib.naming import _camel, _snake, _plural
from agentlib.pipeline.design import _command_entity


# --- verb classification ----------------------------------------------------
# verb -> deterministic CRUD method-verb
_CRUD_VERBS = {
    "add": "add", "create": "add", "insert": "add",
    "list": "list", "view": "list", "show": "list", "display": "list",
    "fetch": "list", "read": "list", "get": "get", "retrieve": "list",
    "update": "update", "edit": "update", "modify": "update",
    "delete": "delete", "remove": "delete",
}

_SEARCH_VERBS = {"search", "query", "find"}

_VERB_RE = re.compile(
    r"\b(add|create|insert|list|view|show|display|fetch|read|get|retrieve|"
    r"update|edit|modify|delete|remove|search|query|find|report|export|"
    r"summary|aggregate|total|import)\b",
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
    if v in ("report", "summary", "aggregate", "total"):
        return "report"
    if v == "export":
        return "export"
    if v == "import":
        return "import"
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

    "retrieve ... by their unique identifier" is a GET-BY-ID, not a list.
    """
    low = (text or "").lower()
    # "retrieve/get ... by (their/its/the) unique id/identifier" -> get-by-id.
    # Only "their" was matched before; other possessives ("its", "his", "her",
    # "the") fell through to a generic "list" classification, producing a
    # list command instead of a get-by-id (prompt 29 I6 "retrieve an order by
    # its unique identifier" -> order-get missing).
    if re.search(
        r"\bby\s+(?:(?:my|your|his|her|its|our|their|the)\s+)?"
        r"(?:unique\s+)?(?:id|identifier|key)\b", low
    ):
        m = _VERB_RE.search(text or "")
        if m:
            v = _normalize_verb(m.group(1))
            if v in ("list", "get"):
                return "get"
    m = _VERB_RE.search(text or "")
    if m:
        v = _normalize_verb(m.group(1))
        if v:
            return v
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


# A specification that asks for an ORDERED listing states it one of two ways:
# a sort/order verb ("list products sorted by name"), or a DIRECTION word
# ("ascending or descending") — a direction can only be stated about an
# ordering. Either is a deterministic signal, so no intent classifier and no
# domain vocabulary is needed.
_SORT_PHRASE_RE = re.compile(
    r"\bsort(?:ed|ing)?\s+by\b"
    r"|\border(?:ed|ing)?\s+by\b"
    r"|\bsorted\b"
    r"|\bsort\b",
    re.I,
)
_SORT_DIRECTION_RE = re.compile(
    r"\bascending\b|\bdescending\b|\basc\b|\bdesc\b", re.I
)


def _prompt_requests_sort(prompt_text):
    """True when the specification asks for an ordered listing."""
    text = prompt_text or ""
    return bool(
        _SORT_PHRASE_RE.search(text) or _SORT_DIRECTION_RE.search(text)
    )


def _prompt_sort_fields(prompt_text, entity):
    """The entity columns a sort request names, or every sortable column.

    The columns are read from the prompt's own "sorted by A, B or C" phrase by
    intersecting its words with the entity's own fields — an ORDER BY may only
    name a column the table HAS. When the phrase names none of them (an
    improbable wording, or a direction-only request), every non-id scalar
    column is offered instead of none: a sort command that accepts no column
    is exactly the defect being fixed.
    """
    fields = [
        f for f in (entity.get("fields") or [])
        if isinstance(f, dict) and f.get("name") and f["name"] != "id"
    ]
    scalar = [
        f["name"] for f in fields
        if (f.get("type") or "") in ("str", "int", "float")
    ]
    named = []
    for raw in re.split(r"[^a-z0-9_]+", (prompt_text or "").lower()):
        if raw and raw in scalar and raw not in named:
            named.append(raw)
    return named or scalar


def _derive_options(verb, entity, page=False, sort=None):
    """Options for a derived (non-explicit) command from the entity design.

    ``sort``: the columns this entity's list command may order by, or None.
    """
    # A field the specification DERIVES from child rows (see
    # ``_apply_derived_total_floors``) is never an option: the caller cannot
    # know a number only arithmetic on the lines produces, so offering
    # ``--total-amount`` would demand it (prompt 22/28).
    _derived = set((entity or {}).get("derived_fields") or [])
    fields = [
        f for f in (entity.get("fields") or [])
        if isinstance(f, dict) and f.get("name") and f["name"] != "id"
        and f["name"] not in _derived
    ]
    # File I/O operations (export to CSV/JSON, import from CSV/JSON) take a
    # file path, not an entity id. The old domain-verb fallback produced
    # ``--id``, and "export" was collapsed into "report" — both leaving the
    # prompt's "export all X to CSV" intent unmappable (prompt 18/19).
    if verb in ("export", "import"):
        return [{"name": "--filename", "required": True, "type": "str", "field": "filename"}]
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
        opts = [
            {"name": "--" + s["param"].replace("_", "-"), "required": False,
             "type": "str", "field": s["param"]}
            for s in lf
        ]
        # A sorted-listing spec ("list products sorted by name, price or
        # quantity, in ascending or descending order") needs --sort-by/--order
        # on the list command. Without them the sort columns were taken for
        # EQUALITY FILTERS (prompt 15: --name/--price/--quantity filtered
        # instead of ordering) and the ordering was unreachable — the command
        # always ran ORDER BY id.
        if sort:
            opts += [
                {"name": "--sort-by", "required": False, "type": "str",
                 "field": "sort_by"},
                {"name": "--order", "required": False, "type": "str",
                 "field": "order"},
            ]
        # A paginated listing spec ("The caller specifies page number and page
        # size") needs --page/--page-size on the list command (prompt 16's
        # customer-list lacked them, leaving the pagination intent unmapped).
        if page:
            opts += [
                {"name": "--page", "required": False, "type": "int", "field": "page"},
                {"name": "--page-size", "required": False, "type": "int", "field": "page_size"},
            ]
        return opts
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
        # A pure join entity has no surrogate `id` PK (PostTag: post_id +
        # tag_id). Its deterministic repository delete takes the
        # unique_together pair, so the CLI options must be the pair columns
        # (--post-id --tag-id), not a nonexistent --id. With `has_id` True the
        # repo deletes by PK, so keep the id-based shape.
        has_id = any(
            isinstance(f, dict) and f.get("name") == "id"
            for f in (entity.get("fields") or [])
        )
        if not has_id:
            pair = next(
                (
                    [str(x) for x in up]
                    for up in (entity.get("unique_together") or [])
                    if isinstance(up, list) and len(up) == 2
                ),
                None,
            )
            if pair:
                return [
                    {
                        "name": "--" + p.replace("_", "-"),
                        "required": True,
                        "type": "int",
                        "field": p,
                    }
                    for p in pair
                ]
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
    if verb == "get":
        return "get_" + ent_snake + "_by_id"
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
        out_temp = 0.0 if _ == 0 else LLM_RETRY_TEMPERATURE
        data = _json_complete(
            messages, schema=_intent_ops_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG, temperature=out_temp,
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


def derive_cli_from_intents(classified, entities_by_class, verbose=False,
                            page=False):
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
        elif op in ("summary", "aggregate"):
            op = "report"
        key = "%s/%s" % (ent_snake, op)
        if key in seen:
            continue
        seen.add(key)
        options = _derive_options(op, ent, page=page)
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
        # The command may be nested (invoice_line add -> group=["invoice_line"]),
        # so resolve the owner by scanning ALL group/name tokens, never group[0].
        owner_cls = _command_entity(c, entities_by_class)
        owner = entities_by_class.get(owner_cls) if owner_cls else None
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

_GENERIC_REPORT_VERBS = frozenset(
    ("report", "summary", "aggregate", "total", "calculate")
)


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
        # Domain-verb fallback: no CRUD/search/report verb found. Use the
        # last non-option token as the verb so state/domain commands like
        # "library overdue" or "product bulk-update" survive (previously
        # dropped because neither token normalized as a known verb).
        for idx in range(len(raw) - 1, -1, -1):
            tok = raw[idx][0]
            if tok.startswith("-"):
                continue
            if tok.lower() in _STOP_TOKENS:
                continue
            verb_idx = idx
            break
    if verb_idx is None:
        return None
    verb_raw = raw[verb_idx][0].lower()
    verb = _normalize_verb(verb_raw) or verb_raw
    # A generic report verb followed by a QUALIFIER token ("expense report
    # monthly --month", "expense report yearly --year") names the QUALIFIER
    # as the command. Collapsing both to one "report" command unions their
    # options (--month, --year) into a surface neither report can serve, and
    # the spec's own report commands disappear. Folding the qualifier in
    # yields "expense monthly"/"expense yearly", which the designed
    # get_monthly_report/get_yearly_summary already serve.
    if (
        (verb in _GENERIC_REPORT_VERBS or verb_raw in _GENERIC_REPORT_VERBS)
        and verb_idx + 1 < len(raw)
    ):
        _nxt = raw[verb_idx + 1][0]
        if not _nxt.startswith("-"):
            # Normalize the qualifier to a snake_case identifier — a raw
            # hyphenated token ("low-stock") fails the CLI command-name
            # validation, and a shape error DISABLES the whole
            # reconcile-propagation repair (every unwired command is then
            # sanitized away instead of being synthesized).
            verb = re.sub(
                r"[\s-]+", "_", _normalize_verb(_nxt) or _nxt.lower()
            )
            # Do NOT advance verb_idx: the qualifier REPLACES the generic verb
            # in the NAME only. The group must stay raw[:verb_idx] (without
            # "report"), and the qualifier token is skipped by the option loop
            # because it does not start with "--".
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
    # The command may be nested under a parent group (library book add ->
    # group=["library","book"]), so the owner is NOT group[0] — it is the
    # entity named ANYWHERE in the command (last matching group/name token).
    # Resolving with group[0] ("library", not an entity) returned early and
    # left every option un-enriched (*_id / --author / --available-only all
    # fell back to their option var names). Scan all tokens via
    # _command_entity instead.
    owner_cls = _command_entity(command, entities_by_class)
    owner = entities_by_class.get(owner_cls) if owner_cls else None
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

# A specification that does NOT enumerate its command line still ASKS for
# operations — it says so in prose. Intent extraction is LLM-based and omits
# some of them: on prompt 42 the design it produced had ``add_customer`` but no
# purchase creation at all, although the prompt says "manage customers and
# their purchases" (analysis/diagnosis_llm_vs_deterministic.md). Nothing
# deterministic put the missing operation back unless the prompt happened to
# contain the literal word "CRUD".
_MANAGE_RE = re.compile(
    r"\b(manage|manages|managing|management|administer|administers|"
    r"maintain|maintains|keep\s+track\s+of|keeps\s+track\s+of|track|tracks|"
    r"record|records)\b",
    re.IGNORECASE,
)
# Containment is the other way a specification asks for a child entity to be
# creatable: "projects contain tasks", "orders containing products". The child
# cannot be contained unless it can first be created.
_CONTAIN_RE = re.compile(
    r"\b(contain|contains|containing|including|consist(?:s|ing)?\s+of)\b",
    re.IGNORECASE,
)
# The operations the floor GUARANTEES. Creation and listing, never more: the
# defect it exists for is an entity the specification asks to manage but that
# cannot be recorded at all (prompt 42's purchase, 47's person, 49's employee).
# update/delete are NOT added here — a specification that wants them says so
# (or says "CRUD", which ``_crud_floor`` turns into the full set), and adding
# destructive commands a prompt never asked for is its own defect.
_MANAGE_OPS = ("add", "list")
_CONTAIN_OPS = ("add", "list")
# A specification opens by announcing its domain ("Build a tool for managing a
# software team's work.") and names the entities in the sentences that follow
# (prompt 47: "The team needs projects, tasks and people"), so the verb scopes
# the WHOLE prompt — the entity set is always the design's, never the prompt's,
# and only entities the prompt actually names are in scope.
_MANAGE_WIDE_OPS = _MANAGE_OPS
# Irregular plurals: the naive ``+"s"`` rule misses "people"/"children", so a
# prompt naming its entity in the plural would not be recognised as naming it
# at all (prompt 47's Person vs "people").
_IRREGULAR_PLURALS = {
    "person": "people", "child": "children", "man": "men", "woman": "women",
    "foot": "feet", "tooth": "teeth", "mouse": "mice", "goose": "geese",
}


def _named_in(text_low, snake):
    """True when the prompt names that entity, as a word, in any number.

    Word boundaries matter: a substring test would match "library" inside a
    longer word, and give a command to an entity the prompt never named.
    """
    for token in (snake, _plural(snake), _IRREGULAR_PLURALS.get(snake)):
        if token and re.search(r"\b%s\b" % re.escape(token), text_low):
            return True
    return False


def _managed_ops_floor(commands, prompt_text, entities_by_class):
    """Ensure the operations a NON-ENUMERATING prompt asks for in prose exist.

    A specification that enumerates its command line IS its surface: adding to
    it is a conformity failure, so this floor never touches one (the guard is
    the same reader the conformity gate uses). Otherwise, for every sentence
    that uses a management verb on an entity the prompt names, the operations
    that verb implies are guaranteed — so an LLM omission (a designed entity in
    read-only shape) can no longer reach the CLI as a missing command.

    Only entities the prompt actually NAMES are in scope, and only the verbs
    the prompt actually uses: a read-only specification ("search by name,
    filter by category") has no management verb and is left untouched.
    """
    text = prompt_text or ""
    if not text or not entities_by_class:
        return commands
    try:
        # Imported here, not at module scope: this module is imported by the
        # design phase, and cli_spec imports the design phase back.
        from agentlib.pipeline.cli_spec import build_prompt_cli_surface

        if build_prompt_cli_surface(text, entities_by_class) is not None:
            return commands
    except Exception:  # noqa: BLE001 - a guard must never break generation
        return commands
    seen = {
        ((c.get("group") or [""])[0], c.get("name"))
        for c in (commands or [])
        if isinstance(c, dict)
    }
    expanded = list(commands or [])

    def add(snake, ent, op):
        if (snake, op) in seen:
            return
        seen.add((snake, op))
        expanded.append({
            "group": [snake],
            "name": op,
            "options": _derive_options(op, ent),
            "target": _crud_target(op, snake),
        })

    whole = text.lower()
    manages = bool(_MANAGE_RE.search(whole))
    contains = bool(_CONTAIN_RE.search(whole))
    for sentence in re.split(r"(?<=[.?!;])\s+|\n+", text):
        low = sentence.lower()
        if not low.strip():
            continue
        if _MANAGE_RE.search(low):
            local = _MANAGE_OPS
        elif _CONTAIN_RE.search(low):
            local = _CONTAIN_OPS
        else:
            local = ()
        for cls, ent in entities_by_class.items():
            snake = _snake(cls)
            if not _named_in(low, snake):
                continue
            for op in local:
                add(snake, ent, op)
    # The widened (whole-prompt) scope: creation and listing for every entity
    # the prompt names, whenever the prompt manages or contains anything.
    if manages or contains:
        wide = _MANAGE_WIDE_OPS if manages else _CONTAIN_OPS
        for cls, ent in entities_by_class.items():
            snake = _snake(cls)
            if not _named_in(whole, snake):
                continue
            for op in wide:
                add(snake, ent, op)
    return expanded


# A specification that says ONE ENTITY CONTAINS ANOTHER ("Customers can place
# orders containing products") is stating that the user must be able to put the
# contained thing INTO the container. A design that models this with a LINE
# entity (OrderItem: order_id, product_id, quantity) leaves the containment
# uncreatable, because the join floor below skips every entity that carries a
# surrogate id — a pure join has no data of its own, a line does — and no other
# floor gives the line a command. Measured: prompt 53's `order add` took only
# --customer-id and no command named a product.
_CONTAIN_LINE_RE = re.compile(
    r"\bcontain(?:s|ing|ed)?\b"
    r"|\bquantit(?:y|ies)\b|\bqty\b",
    re.IGNORECASE,
)


def _contained_line_floor(commands, prompt_text, entities_by_class):
    """Give the LINE entity of a stated containment its add/list commands.

    Structural only: the line entity (an entity with a surrogate id) mentions
    two designed entities by foreign key, BOTH of which the prompt names, and
    the prompt states a containment or a quantity. Then the line is creatable
    and listable — the minimum a containment needs to be usable at all.

    It never invents a line: the entity has to be in the design already. It
    never touches a pure join entity (no id): that is the other floor's case.
    """
    text = prompt_text or ""
    if not text or not entities_by_class:
        return commands
    if not _CONTAIN_LINE_RE.search(text):
        return commands
    low = text.lower()
    seen = {
        ((c.get("group") or [""])[0], c.get("name"))
        for c in (commands or [])
        if isinstance(c, dict)
    }
    expanded = list(commands or [])
    for cls, ent in entities_by_class.items():
        if not isinstance(ent, dict):
            continue
        if not any(
            isinstance(f, dict) and f.get("name") == "id"
            for f in (ent.get("fields") or [])
        ):
            continue  # a pure join entity belongs to the other floor
        refs = {
            _camel(str(f.get("name"))[: -len("_id")])
            for f in (ent.get("fields") or [])
            if isinstance(f, dict) and isinstance(f.get("name"), str)
            and f["name"].endswith("_id") and f["name"] != "id"
        }
        refs = {ref for ref in refs if ref in entities_by_class}
        if len(refs) < 2:
            continue
        # Every entity the line points at must be NAMED by the prompt: the
        # containment the specification states is what puts them in scope.
        if not all(_named_in(low, _snake(ref)) for ref in refs):
            continue
        snake = _snake(cls)
        for op in ("add", "list"):
            if (snake, op) in seen:
                continue
            seen.add((snake, op))
            expanded.append({
                "group": [snake],
                "name": op,
                "options": _derive_options(op, ent),
                "target": _crud_target(op, snake),
            })
    return expanded


def _crud_floor(commands, prompt_text, entities_by_class):
    """Expand a prompt's explicit CRUD into full add/list/update/delete.

    The spec says "Provide CRUD operations for customers and orders". Intent
    extraction is LLM-based and may miss a verb (e.g. "update a customer"
    isn't always emitted as a separate intention even though CRUD requires
    it), but the word CRUD is a deterministic contract. For every designed
    entity the prompt actually names, ensure add/list/update/delete all
    exist so no required command can silently disappear from the surface
    (prompt 21's I7 "update a customer's information" -> customer-update).
    """
    low = (prompt_text or "").lower()
    if not re.search(r"\bcrud\b", low):
        return commands
    seen = {
        ((c.get("group") or [""])[0], c.get("name"))
        for c in (commands or [])
        if isinstance(c, dict)
    }
    expanded = list(commands or [])
    for cls, ent in entities_by_class.items():
        snake = _snake(cls)
        # Only entities the prompt names are in scope for the CRUD contract.
        if not _named_in(low, snake):
            continue
        for op in ("add", "list", "update", "delete"):
            if (snake, op) in seen:
                continue
            seen.add((snake, op))
            expanded.append({
                "group": [snake],
                "name": op,
                "options": _derive_options(op, ent),
                "target": _crud_target(op, snake),
            })
    return expanded


def derive_cli_surface(intentions, prompt_text, entities_by_class,
                       verbose=False):
    """Deterministic CLI command surface from the prompt's user intentions.

    Returns ``{"commands": [...]}`` or ``None``. Handles BOTH the explicit-CLI
    case (verbatim ``cli_command`` strings) and the derived case (CRUD / search
    verbs over the designed entities).
    """
    if not entities_by_class:
        return None

    explicit = _extract_explicit_commands(intentions, entities_by_class)
    commands = list(explicit)
    seen = set()
    for c in commands:
        seen.add("%s/%s" % (
            "/".join(str(g) for g in (c.get("group") or [])),
            str(c.get("name") or ""),
        ))
    # When the prompt names CLI commands explicitly, the deterministic path
    # must ONLY supplement with domain-verb / get-by-id commands the explicit
    # surface missed (overdue, bulk-update, get, authenticate). Running the
    # full CRUD/search/report derivation on top inflates the service design
    # with methods no command needs (prompt 38's login()/create_document(),
    # library's add/list/borrow duplicates), which forces the LLM fill to
    # retry on wrong signatures.
    explicit_mode = bool(explicit)
    # Paginated-listing detection: "page number", "page size", "pagination" in
    # the spec are a deterministic contract that list commands expose
    # --page/--page-size (prompt 16's customer-list lacked them, leaving the
    # "retrieve customers paginated" intent unmapped).
    paginated = bool(
        re.search(r"\b(page|pagina\w*)\b", (prompt_text or "").lower())
    )
    # Sorted-listing detection: a sort/order phrase (or a direction word) in
    # the spec is a deterministic contract that its list command exposes
    # --sort-by/--order (prompt 15's product-list sorted by nothing).
    wants_sort = _prompt_requests_sort(prompt_text)
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
        options = _derive_options(
            verb, entity, page=paginated,
            sort=(
                _prompt_sort_fields(prompt_text, entity)
                if (wants_sort and verb == "list") else None
            ),
        )
        if verb == "bulk-update":
            target = "bulk_update_" + ent_snake
        elif verb in _CRUD_VERBS:
            target = _crud_target(_CRUD_VERBS[verb], ent_snake)
        elif verb == "search":
            target = "search_" + ent_snake
        elif verb in ("report", "summary", "aggregate", "total"):
            target = "get_%s_report" % ent_snake
        else:
            # state-transition / domain verb -> <verb>_<entity>(id)
            target = "%s_%s" % (verb, ent_snake)
        if explicit_mode and verb in (
            "add", "list", "update", "delete", "search", "report"
        ):
            # Explicit-CLI mode: skip standard CRUD/search/report — the
            # explicit commands already cover them, and re-deriving them
            # inflates the service design (LLM-fill retry-storm root cause).
            continue
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
        # The command may be nested under a parent group (library book add ->
        # group=["library","book"]), so resolve the owner by scanning ALL
        # group/name tokens, never group[0] ("library", not an entity).
        owner_cls = _command_entity(c, entities_by_class)
        owner = entities_by_class.get(owner_cls) if owner_cls else None
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
    # Join-entity delete floor: "remove <T> from <E>" detaches a relationship
    # between two entities (prompt 23: "remove a tag from a post" ->
    # post_tag-delete). The deterministic intent-verb regex maps this to a
    # delete on the "container" entity (post-delete), colliding with a real
    # "delete a post" intention. Detect it here and synthesize the join-entity
    # delete command with the unique_together pair options instead.
    for intent in intentions or []:
        text = (intent.get("text") or "").strip()
        m = re.search(
            r"\b(remove|delete|detach|unlink)\b\s+(.+?)\s+from\s+(.+)\b",
            text,
            re.IGNORECASE,
        )
        if not m:
            continue
        # Group 1 is the verb; group 2 the removed entity; group 3 the
        # container. The regex is (VERB) (removed) from (container).
        removed_txt, container_txt = m.group(2), m.group(3)
        removed_ent = _intent_entity(removed_txt, entities_by_class)
        container_ent = _intent_entity(container_txt, entities_by_class)
        if not removed_ent or not container_ent:
            continue
        removed_cls = removed_ent["name"]
        container_cls = container_ent["name"]
        if removed_cls == container_cls:
            continue
        # Find a join entity that FKs to BOTH the removed and container.
        # The design may not populate ``fks`` until reconciliation, so fall
        # back to unique_together columns ending in _id (post_id -> Post,
        # tag_id -> Tag) to detect the join relationship.
        join_cls = None
        for cls, ent in entities_by_class.items():
            fk_refs = {
                fk.get("ref")
                for fk in (ent.get("fks") or [])
                if isinstance(fk, dict) and fk.get("ref")
            }
            if not fk_refs:
                for up in ent.get("unique_together") or []:
                    if isinstance(up, list):
                        for col in up:
                            if (
                                isinstance(col, str)
                                and col.endswith("_id")
                                and col != "id"
                            ):
                                fk_refs.add(_camel(col[: -len("_id")]))
            if not fk_refs:
                # Field-name fallback: any ``_id`` field names a referenced
                # entity (post_id -> Post, tag_id -> Tag). Robust even when
                # the design hasn't populated fks/unique_together yet.
                for f in ent.get("fields") or []:
                    if isinstance(f, dict) and isinstance(f.get("name"), str):
                        col = f["name"]
                        if col.endswith("_id") and col != "id":
                            fk_refs.add(_camel(col[: -len("_id")]))
            if removed_cls in fk_refs and container_cls in fk_refs:
                join_cls = cls
                break
        if not join_cls:
            continue
        join_ent = entities_by_class[join_cls]
        join_snake = _snake(join_cls)
        if any(
            c.get("group") == [join_snake] and c.get("name") == "delete"
            for c in commands
        ):
            continue
        commands.append({
            "group": [join_snake],
            "name": "delete",
            "options": _derive_options("delete", join_ent),
            "target": "delete_" + join_snake,
        })
    # Join-entity completeness floor: a pure join entity (no surrogate id,
    # unique_together pair) linking two entities named in the prompt needs
    # both <join>-add and <join>-delete — the "add a tag to a post" / "remove
    # a tag from a post" pair (prompt 23). Intent extraction may drop one of
    # the two verbs, so synthesize both deterministically from the entity
    # design instead of relying on a fragile intent-text match.
    prompt_low = (prompt_text or "").lower()
    for jcls, jent in entities_by_class.items():
        if any(
            isinstance(f, dict) and f.get("name") == "id"
            for f in (jent.get("fields") or [])
        ):
            continue  # not a pure join entity (has surrogate id)
        pair = next(
            (
                [str(x) for x in up]
                for up in (jent.get("unique_together") or [])
                if isinstance(up, list) and len(up) == 2
            ),
            None,
        )
        if not pair:
            continue
        refs = {
            _camel(col[: -len("_id")])
            for col in pair
            if isinstance(col, str) and col.endswith("_id") and col != "id"
        }
        if len(refs) < 2:
            continue
        if not all(
            _snake(r) in prompt_low or _plural(_snake(r)) in prompt_low
            for r in refs
        ):
            continue
        j_snake = _snake(jcls)
        for op in ("add", "delete"):
            if any(
                c.get("group") == [j_snake] and c.get("name") == op
                for c in commands
            ):
                continue
            commands.append({
                "group": [j_snake],
                "name": op,
                "options": _derive_options(op, jent),
                "target": ("add_" if op == "add" else "delete_") + j_snake,
            })
    # Cross-entity list filter floor: "view/list <E> that have/by <T>" filters
    # E through a join entity J (prompt 23: "view all posts that have a
    # specific tag" -> post-list --tag-id). The join entity's FK column that
    # references T becomes a filter option on E's list command, so the prompt's
    # "posts searched by tag" is CLI-drivable instead of unmapped.
    for intent in intentions or []:
        text = (intent.get("text") or "").strip()
        entity = _intent_entity(text, entities_by_class)
        if not entity:
            continue
        ent_snake = _snake(entity["name"])
        list_cmd = next(
            (
                c for c in commands
                if c.get("group") == [ent_snake] and c.get("name") == "list"
            ),
            None,
        )
        if not list_cmd:
            continue
        existing_opts = {
            o.get("name") for o in list_cmd.get("options", [])
        }
        for cls, other in entities_by_class.items():
            if cls == entity["name"]:
                continue
            o_snake = _snake(cls)
            if o_snake not in text.lower() and _plural(o_snake) not in text.lower():
                continue
            # Find a join entity J that links E and T. The design may not
            # populate ``fks`` yet, so fall back to unique_together columns
            # ending in _id to detect the relationship.
            for jcls, jent in entities_by_class.items():
                fk_refs = {
                    fk.get("ref")
                    for fk in (jent.get("fks") or [])
                    if isinstance(fk, dict) and fk.get("ref")
                }
                if not fk_refs:
                    for up in jent.get("unique_together") or []:
                        if isinstance(up, list):
                            for ucol in up:
                                if (
                                    isinstance(ucol, str)
                                    and ucol.endswith("_id")
                                    and ucol != "id"
                                ):
                                    fk_refs.add(_camel(ucol[: -len("_id")]))
                if entity["name"] not in fk_refs or cls not in fk_refs:
                    continue
                col = next(
                    (
                        fk.get("field")
                        for fk in jent.get("fks") or []
                        if isinstance(fk, dict) and fk.get("ref") == cls
                    ),
                    None,
                )
                if not col:
                    # Fall back to the unique_together column that names T.
                    col = next(
                        (
                            ucol for up in jent.get("unique_together") or []
                            if isinstance(up, list)
                            for ucol in up
                            if (
                                isinstance(ucol, str)
                                and ucol.endswith("_id")
                                and ucol != "id"
                                and _camel(ucol[: -len("_id")]) == cls
                            )
                        ),
                        None,
                    )
                if not col:
                    continue
                flag = "--" + col.replace("_", "-")
                if flag in existing_opts:
                    continue
                list_cmd.setdefault("options", []).append({
                    "name": flag,
                    "required": False,
                    "type": "int",
                    "field": col,
                })
                existing_opts.add(flag)
                break
    # Derived-total floor: an entity whose total the specification says is
    # CALCULATED FROM ITS LINES gets a command that computes it — the value is
    # no longer an input, so the capability needs its own entry point ("Provide
    # CRUD operations and calculate the total order amount", prompt 22; "The
    # invoice total must be calculated from its lines", prompt 28).
    for _cls, _ent in (entities_by_class or {}).items():
        if not isinstance(_ent, dict) or not _ent.get("derived_total"):
            continue
        _e_snake = _snake(_cls)
        if any(
            c.get("group") == [_e_snake] and c.get("name") == "calculate-total"
            for c in commands
        ):
            continue
        commands.append({
            "group": [_e_snake],
            "name": "calculate-total",
            "options": [
                {"name": "--id", "required": True, "type": "int", "field": "id"},
            ],
            "target": "calculate_%s_total" % _e_snake,
        })
    # CRUD-completeness floor: the spec's explicit "CRUD" word is a
    # deterministic contract. Intent extraction may drop a verb ("update a
    # customer"), but CRUD always means add/list/update/delete for every
    # entity the prompt names, so any missing operation is re-added here.
    commands = _crud_floor(commands, prompt_text, entities_by_class)
    # Management/containment floor: for a specification that does NOT enumerate
    # its command line, the operations its own prose asks for must exist. The
    # LLM omitting the creation of an entity it designed read-only is exactly
    # the defect this catches — and the literal word "CRUD" is no longer the
    # only thing that can put it back
    # (analysis/diagnosis_llm_vs_deterministic.md).
    commands = _managed_ops_floor(commands, prompt_text, entities_by_class)
    # Containment stated in prose ("orders containing products") must reach the
    # LINE entity the design built for it, or the containment is not creatable.
    commands = _contained_line_floor(commands, prompt_text, entities_by_class)
    if not commands:
        return None
    return {"commands": commands}


def _merge_cli_surfaces(primary, secondary):
    """Union two CLI surfaces by (group, name), keeping the primary's options.

    ``derive_cli_from_intents`` is LLM-classification-driven and can
    occasionally drop a CRUD command when the classifier misses an intention
    (e.g. prompt 21's ``I7 update a customer`` -> ``customer-update``).
    ``derive_cli_surface`` is a deterministic regex derivation that never
    misses a verb+entity the prompt names. Unioning the two guarantees every
    command the prompt's intentions require is present in the surface, so a
    single dropped classification cannot silently remove a required command.
    The primary (LLM, richer options) wins on collisions.
    """
    if not primary and not secondary:
        return None
    if not secondary:
        return primary
    if not primary:
        return secondary
    merged = {"commands": []}
    seen = set()
    for c in primary.get("commands", []):
        key = (tuple(c.get("group") or []), c.get("name"))
        seen.add(key)
        merged["commands"].append(c)
    for c in secondary.get("commands", []):
        key = (tuple(c.get("group") or []), c.get("name"))
        if key in seen:
            # A cross-entity filter added by the deterministic floor on the
            # same command (e.g. post-list --tag-id) must survive the merge.
            # Union the secondary's extra options into the primary command
            # (primary wins on duplicate flag names, so its option types/shapes
            # stay authoritative).
            primary_cmd = next(
                (m for m in merged["commands"]
                 if (tuple(m.get("group") or []), m.get("name")) == key),
                None,
            )
            if primary_cmd is not None:
                existing = {
                    o.get("name") for o in primary_cmd.get("options", [])
                }
                for o in c.get("options", []):
                    if o.get("name") not in existing:
                        primary_cmd.setdefault("options", []).append(o)
                        existing.add(o.get("name"))
            continue
        seen.add(key)
        merged["commands"].append(c)
    return merged


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


# --- repository design-time constraint --------------------------------------

def repo_spec_constraint(prompt_text, ent_snake):
    """The SPECIFICATION's own responsibility bullet for this repository.

    The repository design is bounded by the CLI surface (``repo_surface_
    constraint``), but a specification states repository duties the CLI list
    never reaches: expense's ``BudgetRepository — … check if a category has
    exceeded its budget`` has no CLI command of its own, so once the
    over-generated ``budget check`` command is gone the repository design stops
    producing ``check_budget_status`` and the spec's own requirement silently
    disappears. Feed the specification's matching bullet so the design still
    covers it. Structural: match the entity's ``<entity>repository`` token in a
    prompt line, strip the bullet/heading decoration, return the line verbatim.
    """
    if not prompt_text or not ent_snake:
        return ""
    needle = re.sub(r"[^a-z0-9]", "", (str(ent_snake) + "repository").lower())
    if not needle:
        return ""
    for line in prompt_text.splitlines():
        flat = re.sub(r"[^a-z0-9]", "", line.lower())
        if needle in flat:
            clean = line.strip().lstrip("0123456789.-*# ").strip()
            if clean:
                return clean
    return ""


def repo_surface_constraint(cli_surface, ent_snake):
    """Human-readable design constraint for a repository design call.

    The repository design is otherwise the ONE unconstrained phase: it only
    sees the spec + model field graph and freely enumerates every filter
    combination (library_system's book_repository ~55 methods). Passing the
    CLI surface here bounds the design to the capabilities the CLI-driven
    service layer actually needs — the design-time analogue of
    ``cli_surface_constraint`` for services. A command targets ``ent_snake``
    when its group names it OR its target mentions it. Returns '' when no
    command applies, so a repo with no CLI surface is left unconstrained
    (its CRUD + spec-named methods still render deterministically).
    """
    if not cli_surface or not ent_snake:
        return ""
    cmds = []
    for c in cli_surface.get("commands") or []:
        if not isinstance(c, dict):
            continue
        grp = [str(g) for g in (c.get("group") or [])]
        tgt = str(c.get("target") or "")
        if ent_snake not in grp and ent_snake not in tgt:
            continue
        name = str(c.get("name") or "")
        tgt_label = tgt or name
        opts = []
        for o in c.get("options") or []:
            if isinstance(o, dict) and o.get("name"):
                opts.append(str(o.get("name")))
        cmds.append("%s %s -> %s(%s)" % (
            "/".join(grp), name, tgt_label, ", ".join(opts)))
    if not cmds:
        return ""
    return (
        "THIS APPLICATION EXPOSES A COMMAND-LINE INTERFACE (click). The service "
        "layer will serve these commands; design ONLY the repository custom "
        "methods they need.\n"
        "REQUIRED CAPABILITIES FOR %s:\n"
        "  %s\n"
        "Do NOT enumerate every combination of filter fields — a filtered "
        "listing is a single list() driven by the entity's declared "
        "list_filters, never one method per field combination, and never a "
        "chain of multiple 'and'/'with' relationships in one method name. The "
        "bound is what the service needs, not every possible query."
        % (ent_snake, "\n  ".join(cmds))
    )
