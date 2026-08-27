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
from agentlib.generation.cli_render import _optvar, _match_param


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


def _design_cli(prompt_text, context, service_methods, verbose=False):
    """Design the CLI command tree; targets constrained to service methods."""
    schema = _cli_schema()
    allowed = {m.get("name") for m in service_methods if isinstance(m, dict)}
    user = (
        "SPECIFICATION:\n%s\n\n"
        "PROJECT LAYOUT SO FAR:\n%s\n\n"
        "AVAILABLE SERVICE METHODS (target must be one of these):\n%s\n\n"
        "Emit the CLI command JSON now."
        % (
            prompt_text,
            context,
            ", ".join(sorted(allowed)) if allowed else "(none yet)",
        )
    )
    messages = [
        {"role": "system", "content": _CLI_SYSTEM},
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
        errs = _v_cli(data)
        # constrain targets to existing service methods (the renderer
        # collapses group[-1]==name and suffixes flat collisions on its own,
        # so no shape-level rejection is needed here)
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
        errs.extend(_cli_wiring_errors(data, service_methods))
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


def _cli_wiring_errors(data, service_methods, entities_by_class=None):
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
                key = o.get("field") or _optvar(o)
                match = _match_param(key, direct)
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
            key = o.get("field") or _optvar(o)
            match = _match_param(key, params)
            if match is None:
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
            notes.append("%s -> dropped (unknown target)" % label)
            continue
        params = [n for n, _ in sig]
        opts = [o for o in (c.get("options") or []) if isinstance(o, dict)]
        if "data" in params:
            cleaned.append(c)
            continue
        kept, covered, dropped = [], set(), []
        for o in opts:
            key = o.get("field") or _optvar(o)
            match = _match_param(key, params)
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
            notes.append(
                "%s: stripped dead option(s) %s" % (label, ", ".join(dropped))
            )
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


def _design_module(path, kind, prompt_text, context, verbose=False):
    """One schema-constrained design call with one corrective retry."""
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
        "Emit the JSON now."
        % (prompt_text, context, path)
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
                stripped = _strip_invalid_impls(data)
                stripped += _strip_reserved_methods(data)
                label = "invalid impl(s)/method(s)"
            if stripped:
                errs = validator(data)
                if not errs:
                    print("    [design] %s: dropped %d %s, accepted"
                          % (path, stripped, label))
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


def _describe_design(kind, data):
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


def _fmt_design_context(designs):
    """Compact human-readable summary of the designs emitted so far."""
    lines = []
    for path, kind, data in designs:
        lines.append("  %s [%s]: %s" % (path, kind, _describe_design(kind, data)))
    return "\n".join(lines) if lines else "(none)"
