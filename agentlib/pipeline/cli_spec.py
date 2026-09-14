"""Prompt-CLI-block surface derivation (the CLI the SPEC enumerates).

Why this module exists. For a prompt that ENUMERATES its command line
verbatim (``library book add --title --isbn ...``), the CLI surface is not a
design problem: the specification already states it. The pipeline ran an LLM
CLI design on top of that list and unioned the two, so the shipped tree
carried commands the spec never asked for (library_system: 24 commands for 9
requested; expenses: 22 for 14) under group names the spec never used
(``category add`` instead of ``expense category add``) with option names the
spec never used (``--amount-cents`` instead of ``--amount``). A user
following the specification got ``exit=2`` (``No such command 'category'``).

This module reads the specification's own command list and turns it into the
surface, so the CLI is EXACTLY what the spec wrote — no more, no less:

  * group path and command name are taken POSITIONALLY from the command
    string (everything before the first ``--option`` is the path, the last
    token is the name, the rest is the group chain) — never inferred from the
    entity design, never flattened;
  * option names are the spec's, verbatim; a bracketed ``[--opt]`` is
    optional, an unbracketed ``--opt`` is required;
  * every option is bound to the service parameter that will carry it — the
    owning entity's field when the option names one, else the target method's
    own parameter (``--from-date`` -> ``start_date``, ``--output`` ->
    ``file_path``) — so the rendered call passes the value the user typed;
  * the service method a command targets is resolved against the methods the
    SPECIFICATION declares (already extracted, evidence-closed, by
    ``service_contract``), falling back to the canonical CRUD/aggregate name
    the deterministic service renderer already knows how to serve.

Nothing here invents a command, an option, or a target: an unresolvable
target falls back to the canonical name so the deterministic delegation
covers it, and an unresolvable option keeps its own variable name.
"""
from __future__ import annotations

import re

from agentlib.naming import _camel, _plural, _snake
from agentlib.pipeline.design import _command_entity

# The specification introduces its command line with a heading naming the CLI
# framework; the commands are the bracketed spans of the bullet list under it.
_CLI_HEADING_RE = re.compile(r"\bCLI\b|\bcommand[- ]line\b", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_INTERPRETER_TOKENS = {
    "python", "python3", "python3.9", "python3.10", "python3.11",
    "python3.12", "python3.13", "sh", "bash", "zsh", "./",
}
_FLAG_NAME_RE = re.compile(
    r"(?:^|-)only$|(?:^|-)active$|(?:^|-)enabled$|(?:^|-)recursive$"
)

# An INLINE enumeration of command names — "... exposes commands: add, list,
# update, delete, and show." The specification names the commands but writes
# no bullet line, no group and no option, so the bullet reader below finds
# nothing and the LLM CLI design ran unconstrained: it shipped a group the
# specification never wrote (``task add`` for a prompt that asked for ``add``)
# and a user following the specification got ``No such command 'add'``.
_INLINE_COMMANDS_RE = re.compile(
    r"\bcommands?\b[^:\n]*:[ \t]*([^\n]+)", re.IGNORECASE
)
# Words that JOIN a list rather than name a command.
_INLINE_STOPWORDS = frozenset({
    "and", "or", "the", "a", "an", "with", "for", "to", "of", "plus",
})

# Semantic option -> parameter aliases. A specification freely names an option
# by its USER-facing word (``--from-date``, ``--output``) while the service
# signature uses the domain word (``start_date``, ``file_path``). Both sides
# are the prompt's; only the binding is the generator's job.
_ALIAS_GROUPS = (
    (("from", "start", "since", "begin", "after", "min"),
     ("start", "from", "begin", "since")),
    (("to", "end", "until", "before", "max"),
     ("end", "until", "to")),
    (("output", "file", "filename", "path", "destination", "dest"),
     ("file", "filename", "path", "output")),
    (("query", "term", "text", "keyword", "search"),
     ("query", "term", "keyword", "search", "text")),
)


def extract_prompt_cli_commands(prompt_text):
    """The specification's own command strings, verbatim, in order.

    Returns ``[]`` when the specification never enumerates a command line, so
    a prompt that only says "use click" keeps the open-ended LLM design.
    """
    lines = (prompt_text or "").splitlines()
    start = None
    for idx, line in enumerate(lines):
        if _CLI_HEADING_RE.search(line):
            start = idx
            break
    if start is None:
        return []
    commands = []
    in_list = False
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        bullet = _BULLET_RE.match(stripped)
        if bullet is None:
            if in_list:
                break
            continue
        in_list = True
        body = bullet.group(1).strip()
        span = _BACKTICK_RE.search(body)
        candidate = (span.group(1) if span else body).strip()
        if not candidate:
            continue
        first = candidate.split()[0].lower()
        if not re.fullmatch(r"[a-z][a-z0-9_.-]*", first):
            continue
        commands.append(candidate)
    return commands


def extract_prompt_inline_commands(prompt_text):
    """Bare command names from an inline ``commands: a, b, c`` enumeration.

    Returns ``[]`` unless the enumeration really is a command list: at least
    two names, every name a single lowercase word, and at least one of them a
    canonical CLI verb — so a sentence that merely mentions "commands:" in
    prose does not become a CLI surface. The names come back FLAT (no group):
    the specification wrote no group, so the surface must render them at the
    root (``add``, not ``task add``).
    """
    for match in _INLINE_COMMANDS_RE.finditer(prompt_text or ""):
        body = re.split(r"[.;\n]", match.group(1))[0]
        names = []
        for token in re.split(r"[\s,]+", body):
            token = token.strip().lower()
            if not re.fullmatch(r"[a-z][a-z0-9_-]*", token):
                continue
            if token in _INLINE_STOPWORDS or token in names:
                continue
            names.append(token)
        if len(names) < 2:
            continue
        if not any(name in _CANONICAL for name in names):
            continue
        return names
    return []


def _options_from_params(param_dicts, pairs):
    """One click option per target-method parameter.

    A specification that names a command without naming its options
    ("exposes commands: add, list, ...") still requires the command to be
    usable: the option set is then the target method's OWN signature — the
    same signature the deterministic service renderer serves — so every
    parameter the command has to supply has a way in. An optional parameter
    renders as an optional option, a required one as a required option; a
    bool parameter renders as a flag. Nothing is invented: the names, the
    types and the optionality are all the design's.
    """
    optional = set()
    for param in param_dicts or []:
        if not isinstance(param, dict):
            continue
        name = param.get("name")
        if not name:
            continue
        ptype = str(param.get("type") or "").strip()
        low = ptype.split("=")[0].strip().lower()
        if (
            low.startswith("optional")
            or "none" in low
            or param.get("nullable")
            or "default" in param
        ):
            optional.add(name)
    options = []
    for name, ptype in pairs or []:
        declared = str(ptype or "").strip().split("=")[0].strip().lower()
        if "bool" in declared:
            otype = "flag"
        elif "int" in declared or "float" in declared:
            otype = "int"
        else:
            otype = "str"
        if name in optional or declared.startswith("optional") or "none" in declared:
            required = False
        else:
            required = otype != "flag"
        options.append({
            "name": "--" + str(name).replace("_", "-"),
            "required": required,
            "type": otype,
            "field": name,
        })
    return options


def parse_prompt_command(command):
    """Positional parse of one verbatim command into a command design.

    The group chain is everything before the first ``--option``; the last
    path token is the command name. Bracketed options are optional. Returns
    ``None`` when the string names no path of at least ``group + name``.
    """
    text = (command or "").strip()
    if not text:
        return None
    raw = []
    in_bracket = False
    for piece in re.split(r"(\[|\])", text):
        if piece == "[":
            in_bracket = True
            continue
        if piece == "]":
            in_bracket = False
            continue
        for token in piece.split():
            if token:
                raw.append((token, not in_bracket))
    while raw and raw[0][0].lower() in _INTERPRETER_TOKENS:
        raw.pop(0)
    path = []
    idx = 0
    while idx < len(raw) and not raw[idx][0].startswith("-"):
        path.append(raw[idx][0].lower())
        idx += 1
    if len(path) < 2:
        return None
    for token in path:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", token):
            return None
    options = []
    seen = set()
    for token, required in raw[idx:]:
        if not token.startswith("--"):
            continue
        # Normalise the dash count: specifications write the occasional
        # ``---flag`` typo (prompt_inventory's ``[---category]``). The option
        # the spec MEANS is the ``--flag`` one, so a doubled dash must not
        # become a distinct ``---category`` option.
        name = "--" + token.lstrip("-").replace("_", "-")
        if name in seen:
            continue
        seen.add(name)
        options.append({
            "name": name,
            "required": required,
            "type": "flag" if _FLAG_NAME_RE.search(name[2:]) else "str",
            "field": "",
        })
    return {
        "group": path[:-1],
        "name": path[-1],
        "options": options,
        "target": "",
    }


def _entity_field_map(ent):
    return {
        f["name"]: f
        for f in ((ent or {}).get("fields") or [])
        if isinstance(f, dict) and isinstance(f.get("name"), str)
    }


def _entity_field_for(key, ent):
    """The owner entity's field an option names, or None.

    Exact first, then the bounded prefix/suffix rule the model/CLI renderers
    already use (``--copies`` -> ``available_copies``, ``--amount`` ->
    ``amount_cents``), so the option binds the column the spec describes.
    """
    fields = _entity_field_map(ent)
    if key in fields:
        return fields[key]
    cands = [
        f for name, f in fields.items()
        if name != "id" and (name.startswith(key + "_") or name.endswith("_" + key))
    ]
    return cands[0] if len(cands) == 1 else None
def _opt_key(option):
    """The snake_case variable a click option binds (``--from-date`` ->
    ``from_date``)."""
    return re.sub(r"[- ]", "_", (option.get("name") or "").lstrip("-"))


def _match_param_local(key, params):
    """Exact, then bounded prefix/suffix, then the FK stem rule — the same
    binding the CLI renderer applies to a click option."""
    key = re.sub(r"[- ]", "_", str(key or "").lstrip("-"))
    if not key:
        return None
    if key in params:
        return key
    hit = next(
        (p for p in params if p.startswith(key + "_") or p.endswith("_" + key)),
        None,
    )
    if hit:
        return hit
    if key.endswith("_id"):
        stem = key[: -len("_id")]
        if stem in params:
            return stem
        return next(
            (p for p in params if p.startswith(stem + "_") or p.endswith("_" + stem)),
            None,
        )
    return None


def _alias_match(key, params):
    """Bind a user-facing option name to the domain parameter it supplies.

    ``--from-date`` -> ``start_date``, ``--to-date`` -> ``end_date``,
    ``--output`` -> ``file_path``, ``--query`` -> ``search_term``. Both names
    come from the specification; only the correspondence is resolved here.
    """
    tokens = set(str(key or "").split("_"))
    if not tokens:
        return None
    for triggers, wanted in _ALIAS_GROUPS:
        if not (tokens & set(triggers)):
            continue
        for param in params:
            if set(str(param).split("_")) & set(wanted):
                return param
    return None


def _bind_option(option, params):
    """The service parameter an option supplies, or None when nothing fits."""
    params = list(params or [])
    if not params:
        return None
    key = option.get("field") or _opt_key(option)
    bound = _match_param_local(key, params)
    if bound:
        return bound
    declared = option.get("field")
    if declared:
        bound = _match_param_local(_opt_key(option), params)
        if bound:
            return bound
    return _alias_match(key, params)


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _name_tokens(name):
    return set(_TOKEN_RE.findall(str(name or "").lower()))


def _entity_names_in(name, entities_by_class):
    """Designed entity classes a method name mentions (Book, Expense, ...)."""
    tokens = _name_tokens(name)
    found = set()
    for cls in entities_by_class or {}:
        snake = _snake(cls)
        if snake in tokens or _plural(snake) in tokens:
            found.add(cls)
    return found


def _path_tokens(command, entities_by_class):
    """The command's path tokens that are NOT entity names (its verbs and
    qualifiers: ``report``, ``monthly``, ``history``, ``detect``)."""
    out = []
    path = list(command.get("group") or []) + [command.get("name") or ""]
    for token in path:
        if _camel(str(token)) in (entities_by_class or {}):
            continue
        out.append(str(token).lower())
    return out


def _score_candidate(command, cand_name, cand_params, entities_by_class):
    """How well a candidate service method serves this command (None = no)."""
    name = str(command.get("name") or "").lower()
    tokens = _name_tokens(cand_name)
    if name not in tokens and not cand_name.startswith(name + "_"):
        return None
    cmd_entity = _command_entity(command, entities_by_class)
    cand_entities = _entity_names_in(cand_name, entities_by_class)
    if cmd_entity is not None and cand_entities and cmd_entity not in cand_entities:
        return None
    score = 4
    for token in _path_tokens(command, entities_by_class):
        if token in tokens:
            score += 1
    if cmd_entity is not None and cmd_entity in cand_entities:
        score += 3
    non_flag = 0
    covered = 0
    for option in command.get("options") or []:
        if not isinstance(option, dict) or option.get("type") == "flag":
            continue
        non_flag += 1
        if _bind_option(option, cand_params):
            covered += 1
    score += 2 * covered
    if cmd_entity is None and non_flag and covered < non_flag:
        # A command with no entity of its own (``library borrow``) is
        # identified by the parameters it has to satisfy.
        return None
    return score


# The canonical CRUD/aggregate name the deterministic service renderer knows
# how to serve, for a command the specification does not itself name.
_CANONICAL = {
    "add": "add_%s", "create": "add_%s", "insert": "add_%s",
    "list": "list_%s",
    # A command named show/view/get asks for ONE row, not a listing: the
    # deterministic renderer serves ``get_<entity>_by_id`` as a single-row
    # read, so ``show`` must not degrade into the list command — both would
    # then print the same listing and an id would have nowhere to go.
    "get": "get_%s_by_id", "show": "get_%s_by_id", "view": "get_%s_by_id",
    "search": "search_%s", "find": "search_%s",
    "update": "update_%s", "edit": "update_%s",
    "delete": "delete_%s", "remove": "delete_%s",
    "history": "get_%s_history",
}


def _command_context(command, entities_by_class):
    """``command`` with its entity hint folded into the group chain.

    A command the specification wrote FLAT (``show``) carries no entity token
    of its own, so every entity-sensitive helper — target resolution, the
    canonical CRUD name, a declared parameter list — needs the entity the
    surface resolved for it. The hint is used for RESOLUTION only; the
    rendered path stays flat.
    """
    hint = command.get("entity_hint")
    if not hint:
        return command
    ctx = dict(command)
    ctx["group"] = [hint] + list(ctx.get("group") or [])
    return ctx


def _declared_params_for_target(command, entities_by_class):
    """Parameters for a canonical target method the design never declared.

    ``get_<entity>_by_id`` takes the entity's id — the deterministic service
    renderer already knows how to serve exactly that call
    (``self.<entity>_repo.get_by_id(id)``). Returns ``None`` for any other
    name, so the caller keeps its option-derived parameter list.
    """
    cls = _command_entity(
        _command_context(command, entities_by_class), entities_by_class
    )
    if cls is None:
        return None
    if (command.get("target") or "") == "get_%s_by_id" % _snake(cls):
        return [{"name": "id", "type": "int"}]
    return None


def _canonical_target(command, entities_by_class):
    cls = _command_entity(command, entities_by_class)
    if cls is None:
        return ""
    template = _CANONICAL.get(str(command.get("name") or "").lower())
    return template % _snake(cls) if template else ""


def _surface_target_name(command, entities_by_class):
    """A deterministic method name for a command no designed method serves.

    ``product report low-stock`` names no CRUD verb, so no canonical template
    applies — but the command still has to exist. Build the name from the
    command's OWN path: the owning entity plus its qualifier tokens
    (``product_report_low_stock``). Deterministic and entity-scoped.
    """
    tokens = [
        str(t).replace("-", "_").lower()
        for t in (command.get("group") or []) + [command.get("name") or ""]
    ]
    tokens = [t for t in tokens if re.fullmatch(r"[a-z][a-z0-9_]*", t)]
    if not tokens:
        return ""
    cls = _command_entity(command, entities_by_class)
    ent = _snake(cls) if cls else ""
    if ent and ent not in tokens:
        tokens = [ent] + tokens
    return "_".join(tokens)


def resolve_target(command, entities_by_class, candidates=None):
    """The best service method for a command among ``candidates``.

    Candidates are ``{method_name: [param names]}`` — the methods the
    SPECIFICATION declares (phase A) or the methods the service design shipped
    (phase B). The best match wins; when nothing matches, the canonical
    CRUD/aggregate name is used so the deterministic delegation still serves
    the command. Never returns a command name that does not at least share the
    command's verb token.
    """
    best_name, best_score = None, -1
    for name, params in (candidates or {}).items():
        score = _score_candidate(command, name, params, entities_by_class)
        if score is None:
            continue
        if score > best_score:
            best_score, best_name = score, name
    if best_name is not None:
        return best_name
    return _canonical_target(command, entities_by_class)


def _resolve_option_fields(command, entities_by_class):
    """Bind each option to its OWNING ENTITY's field and type, in place.

    ``--copies`` -> ``available_copies`` (int), ``--recurring`` ->
    ``is_recurring`` (flag), ``--category`` -> ``category_id`` (int). An
    option naming a designed entity's id (``--member-id``) is a foreign key by
    construction. Anything the entity cannot explain keeps its own variable
    name, which the phase-B alignment binds against the target signature.
    """
    cls = _command_entity(command, entities_by_class)
    ent = entities_by_class.get(cls) if cls else None
    for option in command.get("options") or []:
        if not isinstance(option, dict) or option.get("type") == "flag":
            continue
        key = _opt_key(option)
        field = _entity_field_for(key, ent) if ent else None
        if field is not None:
            option["field"] = field["name"]
            ftype = field.get("type") or "str"
            if ftype in ("int", "float"):
                option["type"] = "int"
            elif ftype == "bool":
                option["type"] = "flag"
            continue
        if key == "id":
            option["field"] = "id"
            option["type"] = "int"
            continue
        if (
            key.endswith("_id")
            and key != "id"
            and _camel(key[: -len("_id")]) in entities_by_class
        ):
            option["field"] = key
            option["type"] = "int"


def build_prompt_cli_surface(prompt_text, entities_by_class, spec_methods=None):
    """The exact CLI surface the specification enumerates, or ``None``.

    ``None`` means the specification does not enumerate a command line (the
    caller keeps the open-ended LLM design). Otherwise every command, option
    and group is the specification's own, with targets resolved against the
    methods the specification declares.
    """
    if not entities_by_class:
        return None
    raw = extract_prompt_cli_commands(prompt_text)
    # No bullet list: the specification may still have named its commands
    # inline ("exposes commands: add, list, update, delete, and show"). Those
    # are FLAT — the specification wrote no group — and their options are
    # filled from the target method's own signature further down.
    flat = [] if raw else extract_prompt_inline_commands(prompt_text)
    if not raw and not flat:
        return None
    commands = []
    seen = set()
    if flat:
        hint = ""
        if len(entities_by_class) == 1:
            # A bare verb list on a single-entity project names that entity's
            # commands; the entity resolves the TARGET only — never the path,
            # which stays flat because the specification wrote no group.
            hint = _snake(next(iter(entities_by_class)))
        for name in flat:
            commands.append({
                "group": [],
                "name": name,
                "options": [],
                "target": "",
                "entity_hint": hint,
            })
    for text in raw:
        command = parse_prompt_command(text)
        if command is None:
            continue
        key = tuple(command["group"] + [command["name"]])
        if key in seen:
            continue
        seen.add(key)
        _resolve_option_fields(command, entities_by_class)
        commands.append(command)
    if not commands:
        return None
    candidates = {}
    for method in spec_methods or []:
        if not isinstance(method, dict) or not method.get("name"):
            continue
        candidates[method["name"]] = [
            p.get("name") for p in (method.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
    for command in commands:
        command["target"] = resolve_target(
            _command_context(command, entities_by_class),
            entities_by_class,
            candidates,
        )
    return {"commands": commands}


def _method_signatures(service_methods):
    out = {}
    for method in service_methods or []:
        if isinstance(method, dict) and method.get("name"):
            out[method["name"]] = [
                (p.get("name"), p.get("type") or "")
                for p in (method.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
    return out


def _relax_signature_to_surface(command, pairs):
    """Make a target method's signature FOLLOW the command's surface.

    The specification's command line is the authority: a parameter the command
    supplies through an OPTIONAL option (``[--expense-date]``), or through no
    option at all, must be OPTIONAL on the method — otherwise a required
    parameter no option can ever cover makes the wiring check DROP the command
    (``library member add`` lost to an uncovered ``is_active``). Only a
    parameter bound to a REQUIRED option stays as declared.

    Returns the number of parameters relaxed, and mutates the design entry in
    place (``pairs`` is the live ``[(name, type)]`` list of the method).
    """
    required_params = set()
    for option in command.get("options") or []:
        if not isinstance(option, dict):
            continue
        name = option.get("field") or _opt_key(option)
        if option.get("required"):
            required_params.add(name)
    relaxed = 0
    for param in pairs:
        # ``pairs`` are the LIVE parameter dicts of the designed method, so
        # the relaxation reaches the rendered signature.
        if not isinstance(param, dict):
            continue
        pname = param.get("name") or ""
        ptype = param.get("type") or ""
        if pname == "data" or pname in required_params:
            continue
        if str(ptype).strip().startswith("Optional"):
            continue
        # Every other parameter is unsupplied by this command — either it is
        # bound to an OPTIONAL option, or no option binds it at all. Both
        # readings are "the caller may omit it".
        param["type"] = "Optional[%s]" % (ptype.strip() or "Any")
        relaxed += 1
    return relaxed


def align_surface_to_design(surface, service_methods, entities_by_class):
    """Bind the surface's options to the DESIGNED service parameters.

    Runs once the service exists. For every command it (1) re-targets to a
    designed method when the phase-A target never made it into the design,
    and (2) sets each option's ``field`` to the parameter it actually supplies
    plus the parameter's primitive type — so a click option is rendered with
    the right type and the rendered call passes the value the user typed.

    Never adds, removes or renames a command: the surface stays exactly the
    specification's list.
    """
    signatures = _method_signatures(service_methods)
    designed = {name: [n for n, _ in pairs] for name, pairs in signatures.items()}
    live_pairs = {}
    for method in service_methods or []:
        if isinstance(method, dict) and method.get("name"):
            live_pairs[method["name"]] = [
                p for p in (method.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
    for command in (surface or {}).get("commands") or []:
        if not isinstance(command, dict):
            continue
        ctx = _command_context(command, entities_by_class)
        if command.get("target") not in signatures:
            command["target"] = resolve_target(ctx, entities_by_class, designed)
        if not command.get("target"):
            # A specification command whose verb matches no designed method
            # (inventory's ``product report low-stock``) still has to exist: an
            # empty target is dropped by ``_sanitize_cli_design`` as an unknown
            # target, so the command the specification wrote would vanish from
            # the shipped CLI. Name the method from the command's own path and
            # declare it below.
            command["target"] = _surface_target_name(ctx, entities_by_class)
        if command.get("target") and command["target"] not in signatures:
            # A target the design never declared. Two shapes are declarable,
            # both served by the deterministic service renderer:
            #   * an EMPTY target — a verb no designed method matches
            #     (inventory's ``product report low-stock``): an empty target
            #     is dropped by ``_sanitize_cli_design`` as an unknown target,
            #     so the command the specification wrote would vanish from the
            #     shipped CLI. Name the method from the command's own path;
            #   * a CANONICAL read the service design omitted (``show`` ->
            #     get_<entity>_by_id), which the renderer already serves as a
            #     single-row read of the entity's repository.
            if not command.get("target"):
                command["target"] = _surface_target_name(ctx, entities_by_class)
            entries = _declared_params_for_target(command, entities_by_class)
            if entries is None:
                entries = [
                    {
                        "name": _opt_key(o),
                        "type": "int" if o.get("type") == "int" else "str",
                    }
                    for o in command.get("options") or []
                    if isinstance(o, dict) and o.get("type") != "flag"
                ]
            if command["target"]:
                for p in entries:
                    live_pairs.setdefault(command["target"], []).append(dict(p))
                service_methods.append({
                    "name": command["target"],
                    "params": [dict(p) for p in entries],
                    "returns": "Any",
                })
                signatures[command["target"]] = [
                    (p["name"], p["type"]) for p in entries
                ]
                designed[command["target"]] = [p["name"] for p in entries]
        pairs = signatures.get(command.get("target") or "")
        if not pairs:
            continue
        if not command.get("options"):
            # The specification named the command but not its options
            # ("exposes commands: add, list, ..."), so the command cannot be
            # left optionless: the target method's own signature — the same
            # one the deterministic service renderer serves — supplies them.
            command["options"] = _options_from_params(
                live_pairs.get(command.get("target")) or [], pairs
            )
        params = [n for n, _ in pairs]
        types = dict(pairs)
        if live_pairs.get(command.get("target")):
            _relax_signature_to_surface(
                command, live_pairs[command["target"]]
            )
            # Re-read the relaxed types so the CLI option types below see
            # them (an optional param must not render as a required option).
            types = {
                p["name"]: (p.get("type") or "")
                for p in live_pairs[command["target"]]
            }
            pairs = [(n, t) for n, t in types.items()]
        for option in command.get("options") or []:
            if not isinstance(option, dict):
                continue
            bound = _bind_option(option, params)
            if bound is None:
                continue
            option["field"] = bound
            if option.get("type") == "flag":
                continue
            declared = str(types.get(bound) or "").strip().lower()
            if "int" in declared or "float" in declared:
                option["type"] = "int"
            elif "bool" in declared:
                option["type"] = "flag"
    return surface


def surface_command_paths(surface):
    """``['library/book/add', ...]`` — the surface's group/name paths."""
    return [
        "/".join([str(g) for g in (c.get("group") or [])] + [str(c.get("name"))])
        for c in (surface or {}).get("commands") or []
        if isinstance(c, dict) and c.get("name")
    ]
