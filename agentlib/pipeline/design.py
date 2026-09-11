"""Schema-constrained design orchestration (LLM design calls).

These functions turn a prompt + a design schema into a validated design
dict. They are the bridge between the pure schemas/validators in
``agentlib.design`` and the manifest-first generation pipeline: they call
the LLM, normalize near-miss tokens, run the schema validators, and
apply one corrective retry before giving up.
"""

import re
import sys

from agentlib.design import (
    _exceptions_schema,
    _entities_schema,
    _methods_schema,
    _v_exceptions,
    _v_entities,
    _v_methods,
    _DESIGN_SYSTEMS,
    _NAME_SNAKE,
    _strip_invalid_list_filters,
    _strip_invalid_impls,
    _strip_reserved_methods,
)
from agentlib.llm.client import _json_complete
from agentlib.naming import _snake, _camel
from agentlib.generation.cli_render import _optvar, _match_param, _resolve_option_param


def _cli_schema():
    return {
        "type": "object",
        "properties": {
            "commands": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group": {"type": "array", "items": {"type": "string"}},
                        "name": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "required": {"type": "boolean"},
                                    "type": {
                                        "type": "string",
                                        "enum": ["str", "int", "flag"],
                                    },
                                    "field": {"type": "string"},
                                },
                                "required": ["name", "required", "type"],
                                "additionalProperties": False,
                            },
                        },
                        "target": {"type": "string"},
                    },
                    "required": ["group", "name", "options", "target"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["commands"],
        "additionalProperties": False,
    }


def _v_cli(d):
    cmds = d.get("commands") if isinstance(d, dict) else None
    if not isinstance(cmds, list) or not cmds:
        return ["commands must be a non-empty array"]
    errs = []
    for c in cmds:
        if not isinstance(c, dict):
            errs.append("command not an object")
            continue
        group = c.get("group")
        name = c.get("name")
        full = "/".join(
            [str(g) for g in (group or []) if isinstance(g, str)] + [str(name)]
        )
        if not isinstance(group, list) or not group or not all(
            isinstance(g, str) and _NAME_SNAKE.fullmatch(g) for g in group
        ):
            errs.append("%s: bad group" % (name,))
        if not isinstance(name, str) or not _NAME_SNAKE.fullmatch(name):
            errs.append("bad command name %r" % (name,))
            continue
        # NOTE: duplicate paths are NOT rejected here — the model often
        # expresses a nested group ("product report") both as parent intent
        # and as leaf, and the deterministic renderer already resolves flat
        # collisions with numeric suffixes. Rejecting duplicates here burned
        # the whole CLI design for nothing.
        opts = c.get("options")
        if not isinstance(opts, list):
            errs.append("%s: options must be an array" % full)
            continue
        for o in opts:
            if (
                not isinstance(o, dict)
                or not isinstance(o.get("name"), str)
                or not o.get("name", "").startswith("--")
            ):
                errs.append("%s: bad option entry" % full)
            elif o.get("type") not in ("str", "int", "flag"):
                errs.append("%s: option %s bad type" % (full, o.get("name")))
        if not isinstance(c.get("target"), str) or not c.get("target"):
            errs.append("%s: target must be a non-empty string" % full)
    return errs


_CLI_SYSTEM = (
    "You are an expert Python architect. Design the click CLI command tree of a "
    "Python project from its specification. Output JSON with a \"commands\" "
    "array. Each command: "
    '{"group": ["<top group>", "<nested group>", ...], "name": "single lowercase '
    'token", "options": [{"name": "--flag", "required": bool, "type": "str"|"int"|"flag", '
    '"field": "exact service method param this option maps to (omit when the '
    'param name matches)"}], "target": "the exact service method name this '
    'command calls"}. Use the exact command surface and option names the spec '
    "names. The target must be "
    "one of the service methods already designed (never invent method names)."
)

_CLI_SYSTEM_ALLOW_NEW = (
    "You are an expert Python architect. Design the click CLI command tree of a "
    "Python project from its specification. Output JSON with a \"commands\" "
    "array. Each command: "
    '{"group": ["<top group>", "<nested group>", ...], "name": "single lowercase '
    'token", "options": [{"name": "--flag", "required": bool, "type": "str"|"int"|"flag", '
    '"field": "exact service method param this option maps to (omit when the '
    'param name matches)"}], "target": "the exact service method name this '
    'command calls"}. Use the exact command surface and option names the spec '
    "names. Prefer reusing an ALREADY-DESIGNED service method when one matches "
    "the capability. If the spec implies a capability that no existing method "
    "covers, you MAY name a NEW method as the target — it will be synthesized "
    "automatically with the right parameters, and its repository underneath. "
    "Name new targets with a clear verb + entity (add_invoice_line, "
    "delete_invoice_line, get_invoice_total).\n\n"
    "Use a FLAT command tree: \"group\" is a SINGLE token naming the entity "
    "(e.g. \"invoice_line\", \"customer\", \"invoice\"), and \"name\" is a SINGLE "
    "verb token (add, list, delete, update, report, total). Do NOT nest "
    "groups (never group=[entity, verb]) and do NOT repeat the verb inside the "
    "group. For a child entity use its own snake token (invoice_line, not "
    "invoice line)."
)


def _fill_missing_cli_options(data, service_methods):
    """Deterministically fill required-option gaps on a CLI design.

    The CLI design is a SEPARATE LLM call from the service design, so it may
    omit an option for a REQUIRED parameter of the target (budget-update has
    no ``--id`` for ``update_budget(id, ...)``). Left alone, that forces
    ``_reconcile_cli_design`` to hard-retrofit the service signature (reshape
    the method, synth a duplicate). Fill the gap HERE, at design time: for
    every non-Optional param of the target that no option currently covers,
    add a default-typed option bound to that param. Deterministic and
    design-driven; never mutates the target. ``data``-style targets pack
    leftovers, so only their non-data required params (usually the id) are
    ensured. Idempotent — safe on the corrective retry.
    """
    sigs = _cli_target_sigs(service_methods)
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        sig = sigs.get(c.get("target"))
        if not sig:
            continue
        params = [n for n, _ in sig]
        opts = [o for o in (c.get("options") or []) if isinstance(o, dict)]
        covered = set()
        for o in opts:
            m = _resolve_option_param(o, params)
            if m is not None:
                covered.add(m)
        required = [
            (n, t) for n, t in sig
            if n != "data" and n not in ("data", "payload", "record")
            and not t.strip().startswith("Optional")
            and n not in covered
        ]
        existing = {o.get("name") for o in opts}
        for n, t in required:
            flag = "--" + n.replace("_", "-")
            if flag in existing:
                continue
            otype = "int" if "int" in t.lower() else "str"
            c.setdefault("options", []).append({
                "name": flag,
                "required": True,
                "type": otype,
                "field": n,
            })
            existing.add(flag)
    return data


def _repair_cross_entity_targets(data, service_methods, entities_by_class):
    """Deterministically rewrite a command whose target belongs to a DIFFERENT
    entity than the command's OWNER entity (expense/category/add ->
    add_expense, where the group names Category but the target adds an
    Expense). The command owner (via ``_command_entity``) is authoritative:
    if a ``<verb>_<owner>`` method was designed, point the command at it so
    the design validates on the FIRST attempt instead of burning a retry on
    a semantically wrong target. Conservative: only rewrites when the
    ``<verb>_<owner>`` method actually exists and the target's entity is a
    strict mismatch; every other case is left to ``_reconcile_cli_design``.
    """
    if not entities_by_class or not service_methods:
        return
    allowed = {
        m.get("name")
        for m in service_methods
        if isinstance(m, dict) and m.get("name")
    }
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        tgt = c.get("target")
        if not isinstance(tgt, str) or not tgt:
            continue
        cls = _command_entity(c, entities_by_class)
        if cls is None:
            continue
        own_snake = _snake(cls)
        tlow = tgt.lower()
        # Longest matching entity name wins (book_loan before book).
        tent = None
        best_len = -1
        for e in sorted(entities_by_class):
            es = _snake(e).lower()
            if es and es in tlow and len(es) > best_len:
                tent = e
                best_len = len(es)
        if tent is None or tent == cls:
            continue
        verb = str(c.get("name") or "").strip().lower()
        cand = "%s_%s" % (verb, own_snake)
        if cand in allowed:
            c["target"] = cand


def _design_cli(prompt_text, context, service_methods, verbose=False,
                allow_new_targets=False, entities_by_class=None,
                repair_methods=None):
    """Design the CLI command tree.

    ``allow_new_targets=False`` (default): every command target must be one of
    the ALREADY-DESIGNED service methods. ``allow_new_targets=True``: the LLM
    may name a NEW service method for a capability the spec implies but no
    existing method covers; the caller's ``_reconcile_cli_design`` then
    synthesizes the method (and its repository) before rendering.
    """
    schema = _cli_schema()
    allowed = {m.get("name") for m in service_methods
               if isinstance(m, dict) and m.get("name")}
    user = (
        "SPECIFICATION:\n%s\n\n"
        "PROJECT LAYOUT SO FAR:\n%s\n\n"
        "AVAILABLE SERVICE METHODS:\n%s\n\n"
        "Emit the CLI command JSON now."
        % (
            prompt_text,
            context,
            ", ".join(sorted(allowed)) if allowed else "(none yet)",
        )
    )
    messages = [
        {"role": "system", "content": (
            _CLI_SYSTEM_ALLOW_NEW if allow_new_targets else _CLI_SYSTEM
        )},
        {"role": "user", "content": user},
    ]
    data = None
    for attempt in (0, 1):
        # 4096-token budget: an 11-command CLI design with option arrays
        # overflows the 2048 default mid-JSON -> truncated -> parse failure.
        data = _json_complete(
            messages, schema=schema, max_tokens=4096, verbose=verbose
        )
        if data is None:
            continue
        # Normalize near-miss command tokens before validation: specs write
        # hyphenated commands ("low-stock") while the schema demands
        # snake_case identifiers — normalize instead of rejecting.
        for c in data.get("commands") or []:
            if not isinstance(c, dict):
                continue
            if isinstance(c.get("name"), str):
                c["name"] = re.sub(r"[\s-]+", "_", c["name"].strip())
            grp = c.get("group")
            if isinstance(grp, list):
                c["group"] = [
                    re.sub(r"[\s-]+", "_", g.strip())
                    for g in grp if isinstance(g, str)
                ]
            # Options: specs/model emit bare names ("category") where click
            # needs "--category"; normalize instead of rejecting.
            opts = c.get("options")
            if isinstance(opts, list):
                for o in opts:
                    if isinstance(o, dict) and isinstance(o.get("name"), str):
                        n = re.sub(r"[\s_]+", "-", o["name"].strip().lstrip("-"))
                        if n:
                            o["name"] = "--" + n
            # Targets: tolerate "Service.method" / "module.Service.method"
            # spellings — the trailing identifier is the method name.
            tgt = c.get("target")
            if isinstance(tgt, str) and "." in tgt:
                c["target"] = tgt.split(".")[-1].strip()
        # Deterministic cross-entity target repair: a command whose target
        # belongs to a DIFFERENT entity than its owner (expense/category/add
        # -> add_expense) would burn a retry; point it at the owner's
        # <verb>_<entity> method when one was designed. The repair checks the
        # FULL designed method list (repair_methods), not the scoped subset
        # passed to the LLM — a scoped call for one entity may still emit a
        # command for another (expense/category/add in the Expense group), and
        # add_category is only in the full list.
        _repair_cross_entity_targets(
            data, repair_methods if repair_methods is not None else service_methods,
            entities_by_class,
        )
        # Fill required-option gaps at design time so the CLI surface is
        # complete BEFORE the reconcile, which would otherwise hard-retrofit
        # the service signature (budget-update --id for update_budget(id,...)).
        # The CLI design is a separate LLM call from the service design, so it
        # can omit an option for a required param; fill it deterministically
        # here. This saves the retrofit AND the LLM-corrective retry.
        _fill_missing_cli_options(data, service_methods)
        errs = _v_cli(data)
        # Constrain targets to existing service methods UNLESS new targets are
        # allowed, in which case _reconcile_cli_design synthesizes them. The
        # renderer collapses group[-1]==name and suffixes flat collisions on
        # its own, so no shape-level rejection is needed here.
        if not allow_new_targets:
            for c in data.get("commands") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("target") not in allowed:
                    errs.append(
                        "target %r is not a designed service method" % c.get("target")
                    )
        # Inter-design consistency (CLI <-> services/models designs): every
        # option must map onto the TARGET's real parameters and every
        # required parameter of the target must be covered — otherwise the
        # deterministic renderer silently ships dead flags / calls with
        # missing arguments (observed as `--author-id` + svc.borrow_book()
        # on the ambiguous library spec).
        errs.extend(_cli_wiring_errors(
            data, service_methods, entities_by_class, lenient_fk=True
        ))
        if not errs:
            return data
        if verbose:
            print("    [design] cli invalid: %s" % "; ".join(errs[:3]))
        retry_user = (
            user
            + "\n\nThe previous CLI design was rejected with these errors. Fix ONLY "
            + "these — do not change anything else:\n"
            + "\n".join("  - " + e for e in errs)
        )
        messages = [messages[0], {"role": "user", "content": retry_user}]
    if data is None:
        print("    [design] cli.py: FAILED (no valid JSON)", file=sys.stderr)
        return None
    # Wiring conflicts are reconciled by the CALLER (_reconcile_cli_design):
    # bounded back-propagation into the designs first, deterministic
    # sanitization as the backstop. Returning raw keeps every option open.
    return data


def _cli_target_sigs(service_methods):
    """{method_name: [(param, type)]} from the DESIGNED services."""
    sigs = {}
    for m in service_methods or []:
        if isinstance(m, dict) and m.get("name"):
            sigs[m["name"]] = [
                (p.get("name"), p.get("type") or "")
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
    return sigs


def _cli_wiring_errors(data, service_methods, entities_by_class=None,
                       lenient_fk=False):
    """Cross-design consistency between the CLI design and the designed
    service signatures (models/services designs are authoritative):

    - every option key (declared field, else the option variable, resolved
      through the SAME exact/suffix rule the renderer uses) must map to a
      parameter of the command's target — an unmapped option would render
      as a decorator whose value is silently discarded;
    - every non-Optional parameter of the target must be covered by some
      option — otherwise the renderer emits a call missing required
      arguments (guaranteed TypeError at runtime).

    update-style (id, data) targets pack leftover options into the data
    dict, so every option is consumable there.
    """
    sigs = _cli_target_sigs(service_methods)
    errs = []
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        label = "/".join(
            [str(g) for g in (c.get("group") or [])] + [str(c.get("name"))]
        )
        target = c.get("target")
        sig = sigs.get(target)
        if sig is None:
            continue  # unknown targets are reported by the existing check
        params = [n for n, _ in sig]
        opts = [o for o in (c.get("options") or []) if isinstance(o, dict)]
        # Cross-entity guard (applies to BOTH the data-style and the
        # arity-style paths): the target's entity must match the command's
        # OWNING entity. A CRUD verb aimed at another entity (e.g.
        # category-list -> list_expenses, category-delete -> delete_expense)
        # used to validate clean on arity/all-optional targets and silently
        # read or delete rows from the WRONG table.
        own = tent = None
        if entities_by_class:
            cls = _command_entity(c, entities_by_class)
            own = _snake(cls) if cls else None
            tlow = str(target or "").lower()
            tent = next(
                (
                    _snake(e)
                    for e in sorted(entities_by_class)
                    if _snake(e).lower() in tlow
                ),
                None,
            )
        if own is not None and tent is not None and own != tent:
            errs.append(
                "%s: target %s targets '%s', not '%s'"
                % (label, target, tent, own)
            )
        if "data" in params:
            # update-style (id, data) targets pack leftover options into
            # the data dict, so unmapped options are consumed there. The
            # non-data required parameters must still be covered.
            direct = [n for n in params if n != "data"]
            covered = set()
            for o in opts:
                oname = o.get("name")
                if not isinstance(oname, str) or not oname.startswith("--"):
                    continue
                match = _resolve_option_param(o, direct)
                if match is not None:
                    covered.add(match)
            missing = sorted(
                n for n, t in sig
                if n != "data"
                and not t.strip().startswith("Optional")
                and n not in covered
            )
            if missing:
                errs.append(
                    "%s: target %s accepts (%s); no option covers %s"
                    % (label, target, ", ".join(params), ", ".join(missing))
                )
            continue
        covered = set()
        for o in opts:
            oname = o.get("name")
            if not isinstance(oname, str) or not oname.startswith("--"):
                continue
            match = _resolve_option_param(o, params)
            if match is None:
                # An FK option (--<entity>_id) referencing a designed entity is
                # NOT an arity error when lenient: _propagate_cli_commands adds
                # the FK param to the target on reconcile (book/add
                # --author-id -> add_book(..., author_id)). The design-time
                # gate would otherwise burn a retry on a gap the reconcile
                # resolves deterministically. Reconcile stays strict
                # (lenient_fk=False) so propagation still triggers there.
                if lenient_fk and entities_by_class:
                    okey = o.get("field") or _optvar(o)
                    if (
                        isinstance(okey, str) and okey.endswith("_id")
                        and okey != "id"
                        and _camel(okey[: -len("_id")]) in entities_by_class
                    ):
                        continue
                errs.append(
                    "%s: option %r maps to no parameter of %s(%s)"
                    % (label, oname, target, ", ".join(params))
                )
            else:
                covered.add(match)
        missing = sorted(
            n for n, t in sig
            if not t.strip().startswith("Optional") and n not in covered
        )
        if missing:
            errs.append(
                "%s: target %s accepts (%s); no option covers %s"
                % (label, target, ", ".join(params), ", ".join(missing))
            )
    return errs


def _sanitize_cli_design(data, service_methods):
    """Deterministic repair of a CLI design that still violates wiring after
    the corrective retry: drop options that map to no parameter of their
    target, then drop commands whose target still has uncovered required
    parameters. Returns (cleaned_design, notes); never raises."""
    sigs = _cli_target_sigs(service_methods)
    notes = []
    cleaned = []
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        label = "/".join(
            [str(g) for g in (c.get("group") or [])] + [str(c.get("name"))]
        )
        sig = sigs.get(c.get("target"))
        if sig is None:
            notes.append(
                "%s -> dropped (unknown target %r, options=%s)"
                % (
                    label,
                    c.get("target"),
                    ",".join(
                        str(o.get("name"))
                        for o in (c.get("options") or [])
                        if isinstance(o, dict)
                    ),
                )
            )
            continue
        params = [n for n, _ in sig]
        opts = [o for o in (c.get("options") or []) if isinstance(o, dict)]
        if "data" in params:
            cleaned.append(c)
            continue
        kept, covered, dropped = [], set(), []
        for o in opts:
            match = _resolve_option_param(o, params)
            if match is None:
                dropped.append(o.get("name"))
            else:
                kept.append(o)
                covered.add(match)
        missing = sorted(
            n for n, t in sig
            if not t.strip().startswith("Optional") and n not in covered
        )
        if missing:
            notes.append(
                "%s -> dropped (no designed service method serves its surface)"
                % label
            )
            continue
        if dropped:
            # Silently strip dead options: a benign cleanup (the command still
            # wires to its target) that previously emitted a `sanitized: ...
            # stripped dead option(s)` log line — a marker the verification
            # treats as a rejection. The command's lifecycle is already shown
            # by the `wired`/`kept` POSITIVE logs; only a genuine command DROP
            # (the missing branch above) is worth a note.
            c["options"] = kept
        cleaned.append(c)
    return {"commands": cleaned}, notes


def _spec_has_token(prompt_text, key):
    """True when `key` (snake_case) appears verbatim in the spec text, in
    any of its snake/hyphen/space spellings — the gate that keeps
    propagation from becoming a hallucination channel."""
    low = (prompt_text or "").lower()
    return (
        key in low
        or key.replace("_", "-") in low
        or key.replace("_", " ") in low
    )


def _command_entity(c, entities_by_class):
    """Entity addressed by a command: last group/name token matching a
    designed entity (CamelCase lookup over snake tokens)."""
    tokens = [str(t) for t in (c.get("group") or [])]
    tokens.append(str(c.get("name") or ""))
    for tok in reversed(tokens):
        cand = _camel(tok)
        if cand in entities_by_class:
            return cand
    return None


def _entity_field_names(cls_ent):
    return {
        f.get("name")
        for f in (cls_ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }


def _resolve_flag_field(ent, stem):
    """Resolve an '<stem>_only' CLI flag onto exactly ONE owner-entity field.

    Matches exact, prefix ('available' -> available_copies), or suffix
    ('active' -> is_active). Returns (column, type) for a unique int/bool
    match, else None so the caller keeps the honest-drop behavior.
    """
    fields = [
        f for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name") and f["name"] != "id"
    ]
    cands = [
        f for f in fields
        if f["name"] == stem
        or f["name"].startswith(stem + "_")
        or f["name"].endswith("_" + stem)
    ]
    if len(cands) != 1:
        return None
    col = cands[0]["name"]
    ftype = cands[0].get("type")
    if ftype not in ("int", "bool"):
        return None
    return col, ftype


def _design_module(path, kind, prompt_text, context, verbose=False,
                   extra_context=None):
    """One schema-constrained design call with one corrective retry.

    ``extra_context`` is appended to the user prompt before "Emit the JSON
    now." — used to pass a generated CLI surface to the service design so it
    produces CLI-drivable (primitive-parameter) methods.
    """
    schema = {
        "exceptions": _exceptions_schema,
        "models": _entities_schema,
        "repositories": _methods_schema,
        "services": _methods_schema,
    }[kind]()
    system = _DESIGN_SYSTEMS[kind]
    user = (
        "SPECIFICATION:\n%s\n\n"
        "PROJECT LAYOUT SO FAR:\n%s\n\n"
        "FILE TO DESIGN: %s\n"
        "%s"
        "Emit the JSON now."
        % (prompt_text, context, path, extra_context or "")
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    validator = {
        "exceptions": _v_exceptions,
        "models": _v_entities,
        "repositories": lambda d: _v_methods(d, path),
        "services": lambda d: _v_methods(d, path),
    }[kind]

    for attempt in (0, 1):
        # 4096-token budget: method designs with many entries (11-command
        # CLIs, 8-method services) overflow the 2048 default mid-JSON ->
        # truncated output -> guaranteed design failure.
        data = _json_complete(
            messages, schema=schema, max_tokens=4096, verbose=verbose
        )
        if data is None:
            print("    [design] %s: no JSON (attempt %d)" % (path, attempt + 1))
            continue
        errs = validator(data)
        if errs and kind in ("services", "repositories", "models"):
            # Malformed optimization hints degrade gracefully instead of
            # failing the design: strip them and re-validate what remains.
            if kind == "models":
                stripped = _strip_invalid_list_filters(data)
                label = "invalid list_filter(s)"
            else:
                # Snapshot (name, has_impl) so the drop log can NAME the
                # methods whose impl recipe was removed (opacity fix: the
                # old log said "dropped N" with no method names).
                _before_map = {
                    m.get("name"): (m.get("impl") is not None)
                    for m in (data.get("methods") or [])
                    if isinstance(m, dict) and m.get("name")
                }
                stripped = _strip_invalid_impls(data)
                stripped += _strip_reserved_methods(data)
                label = "invalid impl(s)/method(s)"
            if stripped:
                errs = validator(data)
                if not errs:
                    detail = ""
                    if kind != "models":
                        _after_map = {
                            m.get("name"): (m.get("impl") is not None)
                            for m in (data.get("methods") or [])
                            if isinstance(m, dict) and m.get("name")
                        }
                        _affected = sorted(
                            n for n, had in _before_map.items()
                            if n not in _after_map
                            or (had and not _after_map[n])
                        )
                        if _affected:
                            detail = " (%s)" % ", ".join(_affected)
                    print("    [design] %s: dropped %d %s%s, accepted"
                          % (path, stripped, label, detail))
                    return data
        if not errs:
            return data
        if verbose:
            print("    [design] %s invalid: %s (attempt %d)"
                  % (path, "; ".join(errs[:3]), attempt + 1))
        retry_user = (
            user
            + "\n\nThe previous design was rejected with these errors. Fix ONLY "
            + "these — do not change anything else:\n"
            + "\n".join("  - " + e for e in errs)
        )
        messages = [messages[0], {"role": "user", "content": retry_user}]
    return None


def _describe_design(kind, data, compact=False):
    if kind == "exceptions":
        return ", ".join(data.get("exceptions", [])) or "(none)"
    if kind == "models":
        parts = []
        for ent in data.get("entities", []):
            fields = ", ".join(
                "%s:%s%s%s"
                % (
                    f.get("name"),
                    f.get("type", ""),
                    "*" if f.get("unique") else "",
                    "?" if f.get("nullable") else "",
                )
                for f in ent.get("fields", [])
            )
            parts.append("%s(%s)" % (ent.get("name", "?"), fields))
        return "; ".join(parts)
    if compact:
        # Method-name-only summary. The design model needs to know WHAT exists
        # to keep a new file consistent, not the full signature of every prior
        # repo/service method (the schema already constrains the current file;
        # bodies are filled later). This keeps the growing "PROJECT LAYOUT SO
        # FAR" context bounded so a design conversation stays under the 4B
        # model's attention window (expense's service/CLI design hit ~5256
        # tokens with full signatures embedded on every call).
        return ", ".join(
            m.get("name")
            for m in data.get("methods", [])
            if isinstance(m, dict) and m.get("name")
        ) or "(none)"
    return "; ".join(
        "%s(%s) -> %s"
        % (
            m.get("name"),
            ", ".join(
                p.get("name") + ":" + p.get("type", "") for p in m.get("params", [])
            ),
            m.get("returns"),
        )
        for m in data.get("methods", [])
    ) or "(none)"


def _fmt_design_context(designs, compact=False):
    """Compact human-readable summary of the designs emitted so far.

    ``compact=True`` lists repo/service methods by NAME only (see
    ``_describe_design``) so the design-phase context stays bounded; models and
    exceptions are always shown in full (field/exception names are essential
    for cross-file consistency)."""
    lines = []
    for path, kind, data in designs:
        lines.append(
            "  %s [%s]: %s"
            % (path, kind, _describe_design(kind, data, compact=compact))
        )
    return "\n".join(lines) if lines else "(none)"
