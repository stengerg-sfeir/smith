"""Bounded CLI wiring propagation and reconciliation.

These functions repair a CLI design that conflicts with the designed
service signatures/models. Propagation is bounded (spec-token gated FK
completion + CRUD/history synthesis) so it never becomes a hallucination
channel; deterministic sanitization is the backstop.
"""

import re
import sys
from pathlib import Path

from agentlib.pipeline.design import (
    _command_entity,
    _entity_field_names,
    _resolve_flag_field,
    _spec_has_token,
    _v_cli,
    _cli_wiring_errors,
    _sanitize_cli_design,
)
from agentlib.naming import _snake, _camel, _plural
from agentlib.generation.cli_render import _optvar, _match_param


def _propagate_cli_commands(data, prompt_text, entities_by_class,
svc_design, designs):
    """Bounded back-propagation of CLI wiring conflicts into the designs.

    Three gates keep this from becoming a hallucination channel:
      1. a missing key must appear VERBATIM in the spec text;
      2. foreign keys must match '<existing_entity>_id' and are added as
         nullable int columns on the command's owning entity;
      3. synthesized service methods are plain CRUD/history signatures,
         rendered afterwards through the existing deterministic delegation
         tiers or the contract-validated fill — no new LLM freedom.

    Additionally, an add-command may cover a required boolean `is_*` field
    through a baked constant WHEN the spec itself declares its default
    ("is_active (default True)") — recorded as a declarative `defaults`
    map on the synthesized method, applied by the deterministic renderer.

    Mutates `data`, `entities_by_class` and `svc_design` IN PLACE (callers
    trial-run on deepcopies and replay on success). Returns notes.
    """
    notes = []
    sigs = {
        m.get("name"): m
        for m in (svc_design or {}).get("methods") or []
        if isinstance(m, dict) and m.get("name")
    }

    # Option 2 (LLM CLI) may emit nested groups (["invoice","list"], name="list")
    # or synonym verbs. Flatten a nested group to the owning entity's snake
    # token and normalize the verb so the CRUD/report branches below recognize
    # the command. Only flatten when the group is actually nested (a single
    # token group is already flat) and only when an entity resolves.
    _VERB_SYN = {
        "add": "add", "create": "add", "insert": "add",
        "list": "list", "view": "list", "show": "list", "display": "list",
        "fetch": "list", "read": "list", "retrieve": "list",
        "update": "update", "edit": "update", "modify": "update",
        "delete": "delete", "remove": "delete",
        "report": "report", "export": "report", "summary": "report",
        "aggregate": "report", "total": "report", "calculate": "report",
    }
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        cls = _command_entity(c, entities_by_class)
        if cls is None:
            continue
        grp = c.get("group") or []
        if len(grp) > 1:
            c["group"] = [_snake(cls)]
        cname = str(c.get("name") or "").strip().lower()
        norm = _VERB_SYN.get(cname)
        if norm is not None:
            c["name"] = norm
    # Dedupe after flattening: "library book add" collapses to ["book","add"]
    # and can collide with the deterministic "book add". Keep the FIRST
    # occurrence so the explicit spelling's options win.
    _seen_cmds = set()
    _unique_cmds = []
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        _key = (tuple(c.get("group") or []), str(c.get("name") or ""))
        if _key in _seen_cmds:
            continue
        _seen_cmds.add(_key)
        _unique_cmds.append(c)
    data["commands"] = _unique_cmds

    def required_missing(cls, covered):
        fields = [
            f for f in (entities_by_class[cls].get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        ]
        req = {
            f["name"] for f in fields
            if f["name"] != "id" and not f.get("nullable")
        }
        auto_now = {
            f["name"] for f in fields
            if f.get("auto") == "now"
            and f.get("type") in ("date", "datetime")
        }
        return req - covered - auto_now

    # ---- Pass A: FK completion ------------------------------------------
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        owner = _command_entity(c, entities_by_class)
        if owner is None:
            continue
        for o in c.get("options") or []:
            if not isinstance(o, dict):
                continue
            key = o.get("field") or _optvar(o)
            if (
                not isinstance(key, str) or key == "id"
                or not key.endswith("_id")
            ):
                continue
            ref_cls = _camel(key[: -len("_id")])
            if ref_cls not in entities_by_class:
                continue
            # Never attach an entity's own id onto itself (member-history
            # resolving owner=Member with --member-id would otherwise create
            # a nonsense self-referential column).
            if ref_cls == owner:
                continue
            if not _spec_has_token(prompt_text, key):
                continue
            if key in _entity_field_names(entities_by_class[owner]):
                continue
            entities_by_class[owner]["fields"].append(
                {"name": key, "type": "int", "nullable": True}
            )
            notes.append(
                "propagated %s.%s <- CLI/spec (nullable FK)" % (owner, key)
            )

    # ---- Pass B: service-method synthesis --------------------------------
    repo_customs = []  # (repo_attr, method_name, [param names])
    for path, kind, d in designs or []:
        if kind != "repositories" or not isinstance(d, dict):
            continue
        stem = Path(path).stem
        attr = (
            stem[: -len("_repository")]
            if stem.endswith("_repository") else stem
        ) + "_repo"
        for m in d.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            ps = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            repo_customs.append((attr, m["name"], ps))

    def synth(name, params, returns, defaults=None, flag_filters=None,
              replace=False):
        if name in sigs:
            # Signature-coherence repair (option diffusion fix). A CLI command
            # that targets an EXISTING service method may expose options for
            # entity fields the LLM-designed signature omitted (customer-add
            # --phone -> add_customer(name, email)). The CLI is the single
            # source of truth (service is deduced from CLI), so extend the
            # existing method's params to cover every CLI-derived option. The
            # deterministic renderer then emits the repaired signature and the
            # fill produces a consistent body — never edit generated code.
            entry = sigs[name]
            # Pair-based CRUD (update/delete by unique_together) is
            # authoritative over an id-bearing signature the CLI options
            # cannot serve (budget update/delete --category-id --month, no
            # --id). Replacing the params keeps the rendered method signature
            # aligned with the surface so the sanitizer doesn't drop the
            # command.
            if replace:
                new_names = {n for n, _ in params}
                existing_extra = {
                    p.get("name")
                    for p in entry.get("params") or []
                    if isinstance(p, dict) and p.get("name")
                } - new_names
                # Only reshape when the existing signature is over-constrained
                # by a param (usually an id) the command surface cannot serve —
                # e.g. borrow_loan(id) -> borrow_loan(member_id, book_id). When
                # the existing params are all covered by the new ones, keep the
                # extend path so a richer-but-compatible signature survives.
                if existing_extra:
                    entry["params"] = [{"name": n, "type": t} for n, t in params]
                    if defaults is not None:
                        entry["defaults"] = defaults
                    if flag_filters is not None:
                        entry["flag_filters"] = flag_filters
                    notes.append(
                        "reshaped %s(%s) to serve CLI surface"
                        % (
                            name,
                            ", ".join(
                                str(p.get("name"))
                                for p in (entry.get("params") or [])
                            ),
                        )
                    )
                    return name
            existing = {
                p.get("name")
                for p in entry.get("params") or []
                if isinstance(p, dict) and p.get("name")
            }
            missing = [
                {"name": n, "type": t}
                for n, t in params
                if n not in existing
            ]
            if missing:
                entry.setdefault("params", []).extend(missing)
                if defaults is not None:
                    entry["defaults"] = defaults
                if flag_filters is not None:
                    entry["flag_filters"] = flag_filters
                notes.append(
                    "extended %s(%s) to serve CLI options"
                    % (
                        name,
                        ", ".join(
                            str(p.get("name"))
                            for p in (entry.get("params") or [])
                        ),
                    )
                )
            return name
        entry = {
            "name": name,
            "params": [{"name": n, "type": t} for n, t in params],
            "returns": returns,
        }
        if defaults:
            entry["defaults"] = defaults
        if flag_filters:
            entry["flag_filters"] = flag_filters
        svc_design.setdefault("methods", []).append(entry)
        sigs[name] = entry
        notes.append(
            "synthesized %s(%s) -> %s"
            % (name, ", ".join(n for n, _ in params), returns)
        )
        return name

    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        label = "/".join(
            [str(g) for g in (c.get("group") or [])] + [str(c.get("name"))]
        )
        cls = _command_entity(c, entities_by_class)
        tgt = c.get("target")
        if tgt in sigs:
            # Known target: skip only when FULLY wired (every option maps,
            # every required param covered). An existing-but-wrong target
            # (book-add -> borrow_book) is exactly what needs repairing.
            tparams = [
                p.get("name")
                for p in (sigs[tgt].get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            treq = [
                p.get("name")
                for p in (sigs[tgt].get("params") or [])
                if isinstance(p, dict) and p.get("name")
                and not str(p.get("type") or "").startswith("Optional")
            ]
            # Entity match FIRST: a CRUD verb aimed at a DIFFERENT entity
            # than the command owner is a semantic mis-wire even when
            # option mapping passes — the data-dict exemption previously
            # hid it entirely (category-add -> add_expense shipped an
            # insert into the expenses table).
            own = _snake(cls) if cls else None
            tlow = str(tgt or "").lower()
            tent = next(
                (
                    _snake(e)
                    for e in sorted(entities_by_class)
                    if _snake(e).lower() in tlow
                ),
                None,
            )
            ent_ok = cls is None or tent is None or own == tent

            def _ent_mismatch():
                return not ent_ok

            if "data" in tparams:
                if ent_ok:
                    continue
            else:
                tcov, tok = set(), True
                for o in c.get("options") or []:
                    if not isinstance(o, dict):
                        continue
                    k = o.get("field") or _optvar(o)
                    m = _match_param(k, tparams)
                    if m is None:
                        tok = False
                        break
                    tcov.add(m)
                if tok and not (set(treq) - tcov):
                    if ent_ok:
                        continue
        if cls is None:
            cname = str(c.get("name") or "").strip().lower()
            # Domain-verb command with no entity group (e.g. "library
            # overdue"): match a repo custom find_<verb>_<entity>s and
            # synthesize get_<verb>_<entity>s() delegating to it.
            hit = None
            for attr, meth, ps in repo_customs:
                mm = re.match(r"find_%s_(.+)$" % re.escape(cname), meth)
                if not mm:
                    continue
                suffix = mm.group(1)
                for cls_name in entities_by_class:
                    s = _snake(cls_name)
                    if suffix == _plural(s) or suffix == s:
                        hit = (attr, meth, s, suffix)
                        break
                if hit:
                    break
            if hit:
                attr, meth, s, suffix = hit
                sname = "get_%s_%s" % (cname, suffix)
                rret = "List[Any]"
                for path, kind, d in designs or []:
                    if kind != "repositories" or not isinstance(d, dict):
                        continue
                    for m in d.get("methods") or []:
                        if isinstance(m, dict) and m.get("name") == meth:
                            rret = m.get("returns") or rret
                synth(sname, [], rret)
                c["target"] = sname
                c["group"] = []
                notes.append(
                    "%s -> %s (delegates to %s.%s)"
                    % (label, sname, attr, meth)
                )
                continue
            # Existing service method by name ("authenticate" ->
            # authenticate_user). When several candidates match the verb
            # (borrow_member, borrow_loan), prefer the one whose existing
            # params ALREADY cover the command's options so the wiring is a
            # no-op reshape (borrow --member-id --book-id -> borrow_loan,
            # not borrow_member(id), which the sanitizer then drops).
            cands = [m for m in sigs if m == cname or m.startswith(cname + "_")]
            tm = None
            best_score = -1
            for mname in cands:
                mparams = [
                    p.get("name")
                    for p in (sigs[mname].get("params") or [])
                    if isinstance(p, dict) and p.get("name")
                ]
                score = 0
                for o in c.get("options") or []:
                    if not isinstance(o, dict):
                        continue
                    k = o.get("field") or _optvar(o)
                    if _match_param(k, mparams) is not None:
                        score += 1
                if score > best_score:
                    best_score = score
                    tm = mname
            if tm is not None:
                # Reshape the existing method to serve the command's options
                # (borrow_loan(id) -> borrow_loan(member_id, book_id)). The
                # options' field names drive the params; the existing sig's
                # return type is preserved.
                mapped = []
                for o in c.get("options") or []:
                    if not isinstance(o, dict):
                        continue
                    if o.get("type") == "flag":
                        continue
                    key = o.get("field") or _optvar(o)
                    if not key:
                        continue
                    mapped.append(
                        (key, "int" if o.get("type") == "int" else "str")
                    )
                rret = "Any"
                if tm in sigs:
                    rret = sigs[tm].get("returns") or rret
                synth(tm, mapped, rret, replace=True)
                c["target"] = tm
                notes.append("%s -> %s (existing service method)" % (label, tm))
                continue
            continue
        sn = _snake(cls)
        cname = str(c.get("name") or "")
        opts = [o for o in (c.get("options") or []) if isinstance(o, dict)]

        if cname == "get":
            # get-by-id: synth get_<entity>_by_id(id). The deterministic
            # renderer already handles this shape.
            idopts = [
                o for o in opts
                if str(o.get("field") or _optvar(o) or "") in ("id", sn + "_id")
                and o.get("type") == "int"
            ]
            if len(idopts) != 1 or len(opts) != 1:
                continue
            meth = synth("get_" + sn + "_by_id", [("id", "int")], "Optional[%s]" % cls)
            c["target"] = meth
            notes.append("%s -> %s (get-by-id)" % (label, meth))
            continue

        if cname == "bulk-update":
            # Bulk update: synth bulk_update_<entity>(ids, value). The ids
            # option identifies the rows (SKUs/ids); the value option is the
            # field to set. The repo renderer has _bulk_update_spec.
            id_fields = {"ids", "id", "sku", "skus", sn + "_id", sn + "_sku"}
            fields = {
                f.get("name"): f.get("type")
                for f in (entities_by_class[cls].get("fields") or [])
                if isinstance(f, dict) and f.get("name")
            }
            value_keys = []
            id_key = None
            for o in opts:
                if o.get("type") == "flag":
                    continue
                key = o.get("field") or _optvar(o)
                if key in id_fields:
                    id_key = key
                    continue
                fm = _match_param(key, sorted(fields))
                if fm is None:
                    continue
                if fm in [v for v, _ in value_keys]:
                    continue
                value_keys.append(
                    (fm, "int" if fields.get(fm) == "int" else "str")
                )
            if id_key is None or not value_keys:
                continue
            meth = synth(
                "bulk_update_" + sn,
                [("ids", "str")] + value_keys,
                "bool",
            )
            c["target"] = meth
            notes.append("%s -> %s (bulk-update)" % (label, meth))
            continue

        if cname in ("add", "create"):
            params, covered, dead = [], set(), []
            field_names = sorted(_entity_field_names(entities_by_class[cls]))
            for o in opts:
                if o.get("type") == "flag":
                    dead.append(o.get("name"))
                    continue
                key = o.get("field") or _optvar(o)
                match = _match_param(key, field_names)
                if match is None:
                    dead.append(o.get("name"))
                    continue
                covered.add(match)
                params.append(
                    (match, "int" if o.get("type") == "int" else "str")
                )
            miss = required_missing(cls, covered)
            # Bounded boolean defaults: required is_* bools whose default
            # the SPEC itself declares become baked constants.
            defaults = {}
            for fname in sorted(miss):
                fent = next(
                    (
                        f for f in (entities_by_class[cls].get("fields") or [])
                        if isinstance(f, dict) and f.get("name") == fname
                    ),
                    {},
                )
                if (
                    fent.get("type") == "bool"
                    and fname.startswith("is_")
                    and re.search(
                        r"%s\s*\(\s*default\s+true\b" % re.escape(fname),
                        prompt_text or "", re.IGNORECASE,
                    )
                ):
                    defaults[fname] = True
            remaining = miss - set(defaults)
            if remaining:
                notes.append(
                    "%s: cannot synthesize add_%s (uncovered required: %s)"
                    % (label, sn, ", ".join(sorted(remaining)))
                )
                continue
            if dead:
                c["options"] = [
                    o for o in c["options"]
                    if not (isinstance(o, dict) and o.get("name") in dead)
                ]
            meth = synth("add_" + sn, params, "int", defaults or None)
            c["target"] = meth
            notes.append("%s -> %s" % (label, meth))
            continue

        if cname in ("list", "show"):
            # Entity-owned listing: every non-flag option must map onto the
            # owner entity's DECLARED list-filter params; then a plain
            # list_<entity> delegation renders deterministically. A flag
            # option named '<stem>_only' resolves onto ONE int/bool field of
            # the owner entity and becomes a constant-predicate filter
            # (available_copies > 0 / is_active = 1), recorded on the
            # synthesized method as flag_filters; _apply_filter_floors turns
            # those into repo.list() filters afterwards. Unresolvable flags
            # keep the honest drop.
            fparams = {
                s.get("param")
                for s in (entities_by_class[cls].get("list_filters") or [])
                if isinstance(s, dict) and s.get("param")
            }
            mapped = []
            flag_filters = {}
            ok = True
            for o in opts:
                if not isinstance(o, dict):
                    continue
                if o.get("type") == "flag":
                    oname = _optvar(o)
                    res = None
                    if oname.endswith("_only"):
                        res = _resolve_flag_field(
                            entities_by_class[cls], oname[: -len("_only")]
                        )
                    if res is None:
                        ok = False
                        break
                    col, ftype = res
                    op = "gt_zero" if ftype == "int" else "eq_true"
                    if oname not in flag_filters:
                        flag_filters[oname] = {"column": col, "op": op}
                        mapped.append((oname, "bool"))
                    continue
                k = o.get("field") or _optvar(o)
                fm = None
                if fparams:
                    fm = _match_param(k, sorted(fparams))
                if fm is None:
                    # Declared filters may be incomplete at propagate time
                    # (_apply_filter_floors runs AFTER reconciliation): fall
                    # back to the entity's own non-id fields — the filter
                    # floor adopts these params once it sees the synthesized
                    # signature, so repo.list() grows to serve them.
                    fm = _match_param(
                        k,
                        sorted(
                            f["name"]
                            for f in (
                                entities_by_class[cls].get("fields") or []
                            )
                            if isinstance(f, dict) and f.get("name")
                            and f["name"] != "id"
                        ),
                    )
                if fm is None:
                    ok = False
                    break
                if fm not in {p for p, _ in mapped}:
                    mapped.append(
                        (fm, "int" if o.get("type") == "int" else "str")
                    )
            if not ok:
                continue
            # Zero-option lists ("category list") legitimately synthesize
            # as list_<entity>() — the delegation tier renders a plain
            # repo.list(). Unresolvable flags stay dropped above (ok=False).
            meth = synth(
                "list_" + sn, mapped, "List[%s]" % cls,
                flag_filters=flag_filters or None,
            )
            c["target"] = meth
            notes.append("%s -> %s" % (label, meth))
            continue

        if cname == "delete":
            # Unique-pair delete: BOTH non-flag options must map onto one
            # declared unique_together pair of the owner entity -> a plain
            # delete_<entity>(a, b) delegating to the deterministic repo
            # pair delete. Single-id deletes already wire through the
            # designed surface and never reach this branch.
            pairs = entities_by_class[cls].get("unique_together") or []
            keys = []
            ok = True
            for o in opts:
                if not isinstance(o, dict):
                    continue
                if o.get("type") == "flag":
                    ok = False
                    break
                k = o.get("field") or _optvar(o)
                fm = _match_param(
                    k, _entity_field_names(entities_by_class[cls])
                )
                if fm is None:
                    ok = False
                    break
                keys.append(fm)
            if not ok:
                continue
            # Single-id delete (--id / <entity>_id): synthesize the plain
            # id-based delete_<entity>(id). Cross-entity single-id deletes
            # (category-delete -> delete_expense) used to survive because
            # arity coverage passed while the table was wrong.
            if len(keys) == 1 and keys[0] in ("id", sn + "_id"):
                meth = synth("delete_" + sn, [("id", "int")], "bool")
                c["target"] = meth
                notes.append("%s -> %s" % (label, meth))
                continue
            if len(keys) != 2:
                continue
            hit = next(
                (
                    [str(x) for x in p]
                    for p in pairs
                    if isinstance(p, list) and len(p) == 2
                    and {str(x) for x in p} == set(keys)
                ),
                None,
            )
            if hit is None:
                continue
            meth = synth(
                "delete_" + sn,
                [
                    (hit[0], "int" if hit[0].endswith("_id") else "str"),
                    (hit[1], "int" if hit[1].endswith("_id") else "str"),
                ],
                "bool",
                replace=True,
            )
            c["target"] = meth
            notes.append("%s -> %s (unique-pair)" % (label, meth))
            continue

        if cname in ("update", "edit"):
            # Two bounded shapes, both rendered deterministically by the
            # generic CRUD delegation tier afterwards:
            #   id-based   : an id option (--id / <entity>_id) plus >= 1
            #                field option, EVERY non-flag option mapping
            #                onto the owner entity ->
            #                update_<entity>(id, ...) delegating to
            #                repo.update(id, data).
            #   pair-based : NO id option; the mapped fields cover a
            #                declared unique_together pair plus >= 1 other
            #                field -> update_<entity>(a, b, ...) resolved
            #                through the repo's get_by_<a>_and_<b> getter.
            fields = {
                f.get("name"): f.get("type")
                for f in (entities_by_class[cls].get("fields") or [])
                if isinstance(f, dict) and f.get("name")
            }
            pairs = [
                [str(x) for x in p]
                for p in (entities_by_class[cls].get("unique_together") or [])
                if isinstance(p, list) and len(p) == 2
            ]
            id_seen, mapped, ok = False, [], True
            for o in opts:
                if o.get("type") == "flag":
                    ok = False
                    break
                key = o.get("field") or _optvar(o)
                if key == "id" or key == sn + "_id":
                    if id_seen:
                        ok = False
                        break
                    id_seen = True
                    continue
                fm = _match_param(key, sorted(n for n in fields if n != "id"))
                if fm is None or fm in mapped:
                    ok = False
                    break
                mapped.append(fm)
            if not ok:
                continue

            def _ptype(n):
                if n.endswith("_id"):
                    return "int"
                return str(fields.get(n) or "str")

            if id_seen and mapped:
                meth = synth(
                    "update_" + sn,
                    [("id", "int")] + [(fm, _ptype(fm)) for fm in mapped],
                    "bool",
                )
                c["target"] = meth
                notes.append("%s -> %s" % (label, meth))
                continue
            if not id_seen and pairs and len(mapped) >= 3:
                hit = next(
                    (
                        p for p in pairs
                        if {p[0], p[1]} <= set(mapped)
                        and len([m for m in mapped if m not in p]) >= 1
                    ),
                    None,
                )
                if hit is not None:
                    extra = [m for m in mapped if m not in hit]
                    meth = synth(
                        "update_" + sn,
                        [
                            (hit[0], _ptype(hit[0])),
                            (hit[1], _ptype(hit[1])),
                        ]
                        + [(m, _ptype(m)) for m in extra],
                        "bool",
                        replace=True,
                    )
                    c["target"] = meth
                    notes.append(
                        "%s -> %s (unique-pair)" % (label, meth)
                    )
                    continue

        if cname in ("history", "loans"):
            idopts = [
                o for o in opts
                if str(o.get("field") or _optvar(o) or "").endswith("_id")
                and o.get("type") == "int"
            ]
            if len(opts) != 1 or len(idopts) != 1:
                continue
            key = idopts[0].get("field") or _optvar(idopts[0])
            hit = next(
                ((a, m) for a, m, ps in repo_customs if ps == [key]), None
            )
            if hit is None:
                continue
            attr, meth = hit
            rret = "List[Any]"
            for path, kind, d in designs or []:
                if kind != "repositories" or not isinstance(d, dict):
                    continue
                for m in d.get("methods") or []:
                    if isinstance(m, dict) and m.get("name") == meth:
                        rret = m.get("returns") or rret
            sname = "get_%s_history" % sn
            synth(sname, [(key, "int")], rret)
            c["target"] = sname
            notes.append(
                "%s -> %s (delegates to %s.%s)"
                % (label, sname, attr, meth)
            )
            continue

        # Aggregate / report verb (report, total, summary, aggregate,
        # calculate, export): synthesize a report/scalar method on the
        # owning entity from the non-flag options. The body is LLM-filled
        # against the repo custom methods. Prefer the LLM's target name when
        # it is a plain identifier, else fall back to get_<entity>_report.
        if cname == "report":
            mapped = []
            ok = True
            for o in opts:
                if not isinstance(o, dict):
                    continue
                if o.get("type") == "flag":
                    continue
                key = o.get("field") or _optvar(o)
                fm = _match_param(
                    key, sorted(_entity_field_names(entities_by_class[cls]))
                )
                if fm is None:
                    ok = False
                    break
                if fm not in [p for p, _ in mapped]:
                    mapped.append(
                        (fm, "int" if o.get("type") == "int" else "str")
                    )
            if not ok:
                continue
            raw_tgt = str(c.get("target") or "")
            meth_name = (
                raw_tgt.split(".")[-1].strip()
                if "." in raw_tgt else raw_tgt.strip()
            )
            if not meth_name or not re.fullmatch(r"[a-z][a-z0-9_]*", meth_name):
                meth_name = "get_%s_report" % sn
            meth = synth(meth_name, mapped, "Dict")
            c["target"] = meth
            notes.append("%s -> %s" % (label, meth))
            continue

        # Fallback (Option 2, allow_new_targets): the LLM named an explicit,
        # well-formed target for a capability the deterministic verb branches
        # above did not recognize (e.g. top_revenue, sales_summary,
        # lines_by_invoice). Trust the LLM's identifier and synthesize a
        # service method with that exact name. Params are derived from the
        # non-flag options: an option that maps onto an owning-entity field is
        # bound to that field; an unmapped option (e.g. --limit, --price-min)
        # is bound to THE OPTION'S OWN NAME. This makes the fallback permissive
        # so no command with a well-formed LLM target is dropped by the
        # sanitizer; the body is LLM-filled against the repo custom methods.
        if (
            isinstance(tgt, str) and tgt
            and re.fullmatch(r"[a-z][a-z0-9_]*", tgt)
        ):
            field_names = sorted(_entity_field_names(entities_by_class[cls]))
            mapped = []
            ok = True
            seen = set()
            for o in opts:
                if not isinstance(o, dict):
                    continue
                if o.get("type") == "flag":
                    continue
                key = o.get("field") or _optvar(o)
                fm = _match_param(key, field_names)
                if fm is None:
                    fm = key
                if not fm or fm in seen:
                    continue
                seen.add(fm)
                mapped.append(
                    (fm, "int" if o.get("type") == "int" else "str")
                )
            if ok:
                # The CLI is the single source of truth for a domain-verb
                # command (borrow/return/search): the synthesized method's
                # params are the command's non-flag options, so replace an
                # existing id-bearing LLM signature the options cannot serve
                # (borrow_loan(id) -> borrow_loan(member_id, book_id)). The
                # synth guard keeps the reshape minimal (only drops params the
                # options don't cover), so other prompts are unaffected.
                #
                # When the target ALREADY exists, do NOT reshape it: a semantic
                # duplicate (loan/borrow --id on a borrow_loan(member_id,
                # book_id) already serving library/borrow) would replace the
                # params and break the deterministic command. Wire to the
                # existing method as-is; the sanitizer drops the incompatible
                # duplicate if its options don't cover the required params.
                if tgt in sigs:
                    c["target"] = tgt
                    notes.append("%s -> %s (trusted LLM target, existing)" % (label, tgt))
                else:
                    meth = synth(tgt, mapped, "Dict", replace=True)
                    c["target"] = meth
                    notes.append("%s -> %s (trusted LLM target)" % (label, meth))
                continue
    return notes


def _canonical_option_field(o):
    """The service param an option maps to (its declared field), else its
    CLI var name. Used to detect prompt-verb synonyms that diverge from the
    entity-field name (--method for payment_method)."""
    return o.get("field") or _optvar(o)


def _dedupe_cli_options_by_param(data, service_methods):
    """Dedupe each command's options by the service param they resolve to.

    A CLI merged from the LLM design (prompt-verb options, ``--method``) and
    the intent-derived surface (entity-field options, ``--payment-method``)
    can expose BOTH names for the SAME service param. The facade mapper picks
    whichever matches the intent phrase ("payment method" -> ``--payment-method``,
    "amount" -> ``--amount``) while the renderer wires the prompt verb — so the
    value the facade passed is dropped (expense-add I1: ``--payment-method
    'Credit Card'`` -> ``payment_method=method=None`` -> NOT NULL constraint).

    Keep ONE option per resolved param, preferring the option whose CLI var
    name EXACTLY equals the param (the entity-field name); it names the
    service param directly, so the renderer wires it and the facade mapper
    picks it. Drop prompt-verb synonyms that diverge (``--method`` for
    ``payment_method``). No-op for commands without such duplicates.
    """
    sigs = {}
    for m in service_methods or []:
        if isinstance(m, dict) and m.get("name"):
            sigs[m["name"]] = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
    for c in data.get("commands") or []:
        if not isinstance(c, dict):
            continue
        params = sigs.get(c.get("target"))
        if not params:
            continue
        chosen = {}   # resolved param (or raw key) -> option
        order = []    # keeps the surviving options's in original order
        for o in c.get("options") or []:
            if not isinstance(o, dict) or not o.get("name"):
                continue
            key = _canonical_option_field(o)
            resolved = _match_param(key, params)
            rkey = resolved if resolved is not None else key
            cur = chosen.get(rkey)
            if cur is None:
                chosen[rkey] = o
                order.append(o)
                continue
            # Prefer the option whose CLI var name equals its resolved param
            # (the entity-field name); drop the prompt-verb synonym.
            if _optvar(o) == rkey and _optvar(cur) != rkey:
                chosen[rkey] = o
                order[order.index(cur)] = o
        c["options"] = order


def _reconcile_cli_design(data, prompt_text, entities_by_class, designs,
                          verbose=False):
    """Propagation-first reconciliation of one CLI design against the
    designed services/models: try bounded back-propagation on deepcopies,
    commit on clean validation, then sanitize whatever remains unwired.
    Returns (data_or_None, service_methods)."""
    svc_design = next((d for p, k, d in designs if k == "services"), None)
    if svc_design is None:
        # Propagation synthesizes service methods; give them a home even
        # when the pipeline reached reconciliation without a services
        # design (defensive — the manifest pipeline always designs one).
        svc_design = {"methods": []}
        designs.append(("expense_service.py", "services", svc_design))
    service_methods = (svc_design or {}).get("methods") or []

    def _validate(d, methods):
        errs = _v_cli(d)
        allowed = {
            m.get("name") for m in methods if isinstance(m, dict)
        }
        for c in d.get("commands") or []:
            if isinstance(c, dict) and c.get("target") not in allowed:
                errs.append(
                    "target %r is not a designed service method"
                    % c.get("target")
                )
        errs.extend(_cli_wiring_errors(d, methods, entities_by_class))
        return errs

    errs = _validate(data, service_methods)
    if not errs:
        # A CLI merged from the LLM design + intent-derived surface may expose
        # both a prompt-verb option and an entity-field option for the same
        # service param (expense-add --method / --payment-method). The facade
        # mapper picks whichever matches the intent phrase; the deterministic
        # dedupe keeps ONE option per param so the mapper and renderer agree.
        _dedupe_cli_options_by_param(data, service_methods)
        return data, service_methods

    wiring_tokens = (
        "maps to no parameter", "no option covers",
        # Cross-entity mis-wires (e.g. category-update -> update_expense):
        # repairable by bounded propagation, NOT fatal shape errors.
        "targets '",
        # Missing-target commands are repairable the same way: the
        # propagation branches assign c["target"] when a verb shape maps.
        "target must be a non-empty string",
    )
    shape_errs = [
        e for e in errs
        if not e.startswith("target ")
        and not any(t in e for t in wiring_tokens)
    ]

    if not shape_errs:
        import copy as _copy

        trial_data = _copy.deepcopy(data)
        trial_ents = _copy.deepcopy(entities_by_class)
        trial_svc = _copy.deepcopy(svc_design or {"methods": []})
        notes = _propagate_cli_commands(
            trial_data, prompt_text, trial_ents, trial_svc, designs
        )
        if notes:
            # Commit: replay the deterministic mutations on the LIVE
            # structures (entities_by_class values ARE the models-design
            # dicts, so models.py/DDL render the propagated field).
            # Partial repairs are fine — whatever stays unwired goes to the
            # sanitizer below.
            _propagate_cli_commands(
                data, prompt_text, entities_by_class, svc_design, designs
            )
            service_methods = (svc_design or {}).get("methods") or []
            errs = _validate(data, service_methods)
            if verbose:
                for n in notes:
                    print(
                        "    [design] cli.py propagated: %s" % n,
                        file=sys.stderr,
                    )

    if errs:
        cleaned, snotes = _sanitize_cli_design(data, service_methods)
        for n in snotes:
            print("    [design] cli.py sanitized: %s" % n, file=sys.stderr)
        data = cleaned
        if not data.get("commands"):
            return None, service_methods
    # Dedupe options by resolved service param (expense-add --method /
    # --payment-method) so the CLI is unambiguous and the facade mapper +
    # renderer agree on ONE option per field. No-op for clean commands.
    _dedupe_cli_options_by_param(data, service_methods)
    return data, service_methods
