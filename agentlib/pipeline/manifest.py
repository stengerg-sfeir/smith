"""Manifest-first generation: design everything, render mechanically, fill only bodies.

The ``_manifest_first_blocks`` function is the heart of the manifest-first
pipeline: it drives the schema-constrained design phase, then the
deterministic render phase, then the LLM fill phase. It never lets the
4B model write whole file bodies — the LLM only fills business bodies
inside locked skeletons.
"""

import re
import sys
from pathlib import Path

from agentlib.design import (
    _generate_manifest,
    _validate_manifest,
    _strip_infeasible_repo_methods,
    _strip_repo_method_chains,
)
from agentlib.pipeline.design import (
    _design_module,
    _describe_design,
    _fmt_design_context,
    _design_cli,
    _command_entity,
)
from agentlib.pipeline.intents import (
    extract_intentions,
    compute_needs_cli,
    _prompt_specifies_cli,
)
from agentlib.pipeline.cli_surface import (
    classify_intentions,
    derive_cli_from_intents,
    derive_cli_surface,
    _merge_cli_surfaces,
    cli_surface_constraint,
    repo_surface_constraint,
)
from agentlib.pipeline.cli_propagate import _reconcile_cli_design
from agentlib.pipeline.service_contract import (
    extract_service_contract,
    service_contract_constraint,
    check_service_contract,
)
from agentlib.generation.service_render import (
    _apply_filter_floors,
    _apply_impl_floors,
    _render_service_file,
)
from agentlib.generation.model_render import (
    _render_exceptions_file,
    _render_models_file,
)
from agentlib.generation.cli_render import _render_cli_file, _render_main_file
from agentlib.generation.repo_render import _render_repository_file
from agentlib.checks.ast_utils import _extract_model_ast
from agentlib.naming import _generate_database_file, _snake, _camel
from agentlib.pipeline.generate import _generate_file


class _NoEntityScript(Exception):
    """Raised when a manifest declares no data entities (a script-like
    project such as a hello-world app). The multi-pass pipeline is
    entity-driven; such a spec degrades to single-pass generation rather
    than failing outright."""


def _synthesize_cli_repos(designs, entities_by_class, manifest):
    """Back-propagate missing repository files from the CLI design.

    A CLI command that references an entity (via its options/name) makes the
    service header need ``self.<entity>_repo``. When ``<entity>_repository.py``
    was never designed, the deterministic CRUD delegation would emit an
    ``AttributeError`` at runtime (prompt 31's ``add_customer`` ->
    ``self.customer_repo``, prompt 40's ``list_notification`` ->
    ``self.notification_repo``). Synthesize the repo file: an empty customs
    design renders a deterministic CRUD repository, and the service header
    wires it on the next render pass.

    Famille 1 (back-propagated model): a ``--<entity>_id`` option (order-add
    ``--customer-id``) references an entity the design did not capture
    (``Customer``). Without it, ``orders.customer_id`` FK points at a missing
    ``customers`` table -> ``no such table: main.customers`` (prompt 32/40).
    Also synthesize a minimal model for each referenced-but-undesigned entity
    and add it to the models design so models.py renders its table.
    """
    if not designs:
        return
    cli_entries = [
        d for p, k, d in designs
        if k == "cli" and isinstance(d, dict)
    ]
    if not cli_entries:
        return
    existing_repo_stems = {
        Path(path).stem
        for path, kind, _ in designs
        if kind == "repositories"
    }
    model_design = next(
        (d for p, k, d in designs if k == "models" and isinstance(d, dict)),
        None,
    )

    def _id_option_entity(o):
        """Entity class referenced by an ``--<entity>_id`` option, or ""."""
        if not isinstance(o, dict):
            return ""
        key = o.get("field")
        if key is None:
            names = o.get("names") or []
            key = next((n.lstrip("-") for n in names if n.startswith("--")), None)
        if not isinstance(key, str) or not key.endswith("_id") or key == "id":
            return ""
        return _camel(key[: -len("_id")])

    def _ensure_entity(cls):
        if cls in entities_by_class:
            return entities_by_class[cls]
        ent = {
            "name": cls,
            "fields": [
                {"name": "id", "type": "int", "primary_key": True},
                {"name": "name", "type": "str"},
            ],
            "fks": [],
        }
        entities_by_class[cls] = ent
        if model_design is not None:
            ents = model_design.setdefault("entities", [])
            if not any(e.get("name") == cls for e in ents):
                ents.append(ent)
        return ent

    def _ensure_repo(cls):
        ent_snake = _snake(cls)
        stem = ent_snake + "_repository"
        if stem in existing_repo_stems:
            return
        file_name = stem + ".py"
        designs.append((file_name, "repositories", {"methods": []}))
        existing_repo_stems.add(stem)
        manifest.append({
            "file": file_name,
            "role": "data access",
            "kind": "repository",
            "entity": ent_snake,
            "imports_from": ["models", "database"],
        })

    for cli_data in cli_entries:
        for c in cli_data.get("commands") or []:
            if not isinstance(c, dict):
                continue
            # 1. entity named by the command group (existing behaviour)
            cls = _command_entity(c, entities_by_class)
            if cls is not None:
                ent = entities_by_class.get(cls)
                if isinstance(ent, dict):
                    _ensure_repo(cls)
            # 2. entities referenced via --<entity>_id options (Famille 1)
            for o in c.get("options") or []:
                ref_cls = _id_option_entity(o)
                if ref_cls and ref_cls in entities_by_class:
                    _ensure_repo(ref_cls)
                elif ref_cls:
                    # Undesigned entity: back-propagate model + repo.
                    _ensure_entity(ref_cls)
                    _ensure_repo(ref_cls)


def _merge_duplicate_entity(existing, additional):
    """Merge a duplicate entity design into the canonical one (in place).

    A class declared in two model files with differing field sets is
    reconciled by unioning fields. Without this, the LAST design wins in
    entities_by_class (so repo/service use every column), but the service
    imports the FIRST model module — which may render a shorter class —
    producing a TypeError at runtime. Fusion preserves a valid dataclass
    ordering (required fields before optional/defaulted ones), since a
    non-default field appended after ``id`` (which defaults to None) would
    render an invalid dataclass. Returns ``existing``.
    """
    if not isinstance(existing, dict) or not isinstance(additional, dict):
        return existing
    existing.setdefault("fields", [])
    existing.setdefault("fks", [])
    existing.setdefault("unique_together", [])

    def _is_optional(f):
        return f.get("name") == "id" or bool(f.get("nullable"))

    seen = {f.get("name") for f in existing["fields"] if isinstance(f, dict)}
    for f in additional.get("fields") or []:
        if isinstance(f, dict) and f.get("name") and f["name"] not in seen:
            existing["fields"].append(f)
            seen.add(f["name"])

    # Canonical dataclass ordering: required fields before optional ones.
    req = [f for f in existing["fields"] if isinstance(f, dict) and not _is_optional(f)]
    opt = [f for f in existing["fields"] if isinstance(f, dict) and _is_optional(f)]
    existing["fields"] = req + opt

    unique_seen = {tuple(p) for p in existing["unique_together"]
                   if isinstance(p, (list, tuple))}
    for p in additional.get("unique_together") or []:
        if isinstance(p, (list, tuple)) and tuple(p) not in unique_seen:
            existing["unique_together"].append(p)
            unique_seen.add(tuple(p))

    seen_fks = {
        (fk.get("field"), fk.get("ref_table"), fk.get("ref_field"))
        for fk in existing["fks"] if isinstance(fk, dict)
    }
    for fk in additional.get("fks") or []:
        if isinstance(fk, dict):
            t = (fk.get("field"), fk.get("ref_table"), fk.get("ref_field"))
            if t not in seen_fks:
                existing["fks"].append(fk)
                seen_fks.add(t)
    return existing


def _service_is_complex(cli_surface, entities_by_class):
    """True when a single schema-constrained service-design call would exceed
    the 4B model's attention window (~3.1k tokens).

    Projected method count is approximated by CLI commands (one service method
    per command, enforced by ``cli_surface_constraint``) plus the number of
    entities (each drives CRUD + business methods). A CRUD-heavy prompt like
    expense (22 commands, 3 entities = 25) used to fit the monolithic design,
    but its single call still produced a ~2075-token prompt + ~2313-token
    output (total ~4398 tokens, above the ~3.1k window), so the monolithic
    design is safe only for SMALL services. A genuinely large cross-entity
    service such as library_system (31 commands, 4 entities = 35) is complex
    and routes to the scoped split design. Threshold 24 sits so expense (25)
    also engages the split: only when the sum exceeds a single design call's
    safe size does the split engage (it degrades to monolithic on failure).
    """
    n_cmds = len((cli_surface or {}).get("commands") or [])
    n_ents = len(entities_by_class)
    return (n_cmds + n_ents) > 24


def _command_owner_entity(c, entities_by_class):
    """Owner entity class for a CLI command: the command's group entity, else
    the JOIN entity a multi-id reference operation addresses (borrow
    --member-id --book-id -> Loan, the entity FKing to every referenced
    entity), else the single entity referenced by a leading
    ``--<entity>_id`` option. '' when neither resolves. Grouping is
    structural over the CLI surface, never prompt regex."""
    cls = _command_entity(c, entities_by_class)
    if cls:
        return cls
    refs = []
    for o in c.get("options") or []:
        if not isinstance(o, dict):
            continue
        key = o.get("field")
        if key is None:
            names = o.get("names") or []
            key = next((n.lstrip("-") for n in names if n.startswith("--")), None)
        if isinstance(key, str) and key.endswith("_id") and key != "id":
            ref = _camel(key[: -len("_id")])
            if ref in entities_by_class and ref not in refs:
                refs.append(ref)
    if len(refs) == 1:
        return refs[0]
    if len(refs) >= 2:
        # A multi-id reference operation (borrow --member-id --book-id)
        # addresses the JOIN entity that FKs to ALL referenced entities.
        # Exactly one such entity wins.
        for cls, ent in entities_by_class.items():
            if cls in refs:
                continue
            fk_refs = set()
            for fk in ent.get("fks") or []:
                if isinstance(fk, dict) and fk.get("ref"):
                    fk_refs.add(fk["ref"])
            if not fk_refs:
                fk_refs = {
                    _camel(f["name"][: -len("_id")])
                    for f in (ent.get("fields") or [])
                    if isinstance(f, dict) and isinstance(f.get("name"), str)
                    and f["name"].endswith("_id") and f["name"] != "id"
                }
            if set(refs) <= fk_refs:
                return cls
    return ""


def _service_design_groups(cli_surface, entities_by_class, designs):
    """{entity_class: {"commands": [...]}} grouping service-shaping inputs by
    owner entity, so a complex service can be designed in small scoped calls.

    Derived from the deterministic CLI surface (owner entity + FK options) and
    the designed repository files (custom methods' owning entity) — never from
    prompt regex. Entities with a designed repository get a group even when no
    CLI command targets them directly, so business/custom methods
    (``get_loan_report``, ``get_overdue_loans``) are designed in scope.
    """
    groups = {}
    for c in (cli_surface or {}).get("commands") or []:
        if not isinstance(c, dict):
            continue
        owner = _command_owner_entity(c, entities_by_class)
        if owner:
            groups.setdefault(owner, [])
            groups[owner].append(c)
    for path, kind, data in designs:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = stem[: -len("_repository")] if stem.endswith("_repository") else stem
        cls = _camel(ent_snake)
        if cls in entities_by_class:
            groups.setdefault(cls, [])
    return {cls: {"commands": cmds} for cls, cmds in groups.items()}


def _scoped_fmt_design_context(ent_cls, designs, entities_by_class, compact=False):
    """``_fmt_design_context`` filtered to the entity's model + its repository
    and the FK-referenced entities' repositories, so a scoped service design
    sees only the context it needs. Keeps the design conversation small enough
    for the 4B model to stay instruction-faithful (no cross-entity repo noise).
    ``compact`` is threaded to ``_fmt_design_context`` so the scoped repo
    methods are listed by name only."""
    ent = entities_by_class.get(ent_cls) or {}
    fk_refs = {
        _camel(str(f.get("ref")))
        for f in (ent.get("fks") or [])
        if isinstance(f, dict) and f.get("ref")
    }
    keep_repo_stems = {_snake(ent_cls) + "_repository"}
    for ref in fk_refs:
        keep_repo_stems.add(_snake(ref) + "_repository")
    scoped = []
    for p, k, d in designs:
        if k == "models":
            scoped.append((p, k, d))
        elif k == "repositories" and Path(p).stem in keep_repo_stems:
            scoped.append((p, k, d))
    return (
        _fmt_design_context(scoped, compact=compact)
        if scoped else _fmt_design_context(designs, compact=compact)
    )


def _scoped_cli_constraint(commands):
    """``cli_surface_constraint`` over a subset of commands ('' when none)."""
    if not commands:
        return ""
    return cli_surface_constraint({"commands": commands})


def _service_method_owner(m, entities_by_class):
    """Owner entity class for a designed service method, derived from the
    method name's last entity-matching token (``borrow_loan`` -> Loan,
    ``get_loan_report`` -> Loan, ``add_book`` -> Book), else the first
    ``<entity>_id`` parameter. '' when neither resolves. Used to scope the
    CLI design by command group so no single design call packs the whole
    service. Structural over the method name/params, never prompt regex."""
    name = (m.get("name") if isinstance(m, dict) else None) or ""
    toks = name.split("_")
    for tok in reversed(toks):
        cls = _camel(tok)
        if cls in entities_by_class:
            return cls
    for p in m.get("params") or []:
        pn = p.get("name") if isinstance(p, dict) else None
        if pn and pn.endswith("_id") and pn != "id":
            ref = _camel(pn[: -len("_id")])
            if ref in entities_by_class:
                return ref
    return ""


def _manifest_first_blocks(prompt_text, verbose=False):
    """smith-style manifest-first pipeline.

    Design everything as schema-constrained JSON, render all mechanical files
    deterministically, and let the LLM fill only business bodies (service and
    repository custom methods) inside locked skeletons. Returns {file: code}.
    """
    if verbose:
        print("    Generating architecture manifest...")
    layout = _generate_manifest(prompt_text, verbose=verbose)
    if not layout:
        if verbose:
            print("    Manifest failed; generation aborted (no fallback)")
        return None, None
    manifest, db_file = _validate_manifest(layout)

    # Intent-based CLI gate: extract the user intentions ONCE (used both as
    # the deterministic needs-CLI gate and, under Approach B, as the single
    # source of truth for the CLI surface + service constraint). If the LLM
    # layout omitted a CLI but the intentions describe data-management
    # capabilities, inject a cli spec. Never inject when the manifest already
    # declared a CLI.
    intentions = extract_intentions(prompt_text, verbose=verbose)
    manifest_has_cli = any(s["kind"] == "cli" for s in manifest)
    needs_cli = manifest_has_cli or compute_needs_cli(intentions)
    if needs_cli and not manifest_has_cli:
        manifest.append({
            "file": "cli.py",
            "role": "command-line interface",
            "kind": "cli",
            "entity": "",
            "imports_from": [],
        })
        if verbose:
            print("    Intent gate: CLI required — injecting cli.py")

    designs = []  # (path, kind, data)
    entities_by_class = {}

    if verbose:
        print("    Design phase (schema-constrained JSON)...")

    def _design_into(path, kind, context, extra_context=None):
        """One schema-constrained design call, appended to `designs`."""
        data = _design_module(path, kind, prompt_text, context, verbose,
                              extra_context=extra_context)
        if data is None:
            print("    [design] %s: FAILED" % path, file=sys.stderr)
            return None
        designs.append((path, kind, data))
        if verbose:
            print("      - %s [%s] %s" % (path, kind, _describe_design(kind, data)))
        return data

    # 1. exceptions — ALWAYS designed from the spec under the schema; the
    # prompt text is never regex-scanned. The canonical module survives only
    # when the design names exceptions or the layout declared the file.
    declared_exc = [
        s["file"] for s in manifest
        if s["kind"] == "exceptions" or "exception" in Path(s["file"]).stem
    ]
    exception_names = []
    for ep in (declared_exc or ["exceptions.py"]):
        data = _design_into(ep, "exceptions", "(none)")
        if data is None:
            return None, None
        for e in data.get("exceptions") or []:
            if e not in exception_names:
                exception_names.append(e)
    if not declared_exc and not exception_names:
        # Nothing declared and nothing designed: no exceptions module at all.
        designs[:] = [(p, k, d) for p, k, d in designs if k != "exceptions"]

    # 2. models — collect entities, reconciling duplicate classes so every
    # model file renders the same field set. A class split across two model
    # files gets its fields unioned: the repo/service use the LAST captured
    # design (entities_by_class), but the service imports the FIRST model
    # module (models_module), so without reconciliation a field present only
    # in a later design is used by the repo but missing from the imported
    # class -> TypeError at runtime.
    model_paths = [s["file"] for s in manifest if s["kind"] == "models"]
    model_designs = {}
    for mp in model_paths:
        data = _design_into(mp, "models", _fmt_design_context(designs))
        if data is None:
            return None, None
        model_designs[mp] = data
        for ent in data.get("entities") or []:
            if isinstance(ent, dict) and ent.get("name"):
                existing = entities_by_class.get(ent["name"])
                if existing is None:
                    entities_by_class[ent["name"]] = ent
                else:
                    _merge_duplicate_entity(existing, ent)
    # Propagate the reconciled entity back to every model design so each
    # module renders the identical column set (not just the first).
    for data in model_designs.values():
        ents = data.get("entities") or []
        for i, ent in enumerate(ents):
            if isinstance(ent, dict) and ent.get("name"):
                merged = entities_by_class.get(ent["name"])
                if merged is not None and merged is not ent:
                    ents[i] = merged

    if not entities_by_class:
        print("    [design] no entities designed", file=sys.stderr)
        # A manifest that plans no data model is a script-like project
        # (hello-world, a pure CLI tool): the entity-driven multi-pass
        # pipeline cannot serve it. Signal the caller to degrade to
        # single-pass generation rather than failing outright.
        raise _NoEntityScript()

    # The models module stem drives every "from <models_module> import"
    # emitted downstream (repositories, service) — never hardcode
    # "models": a layout may name its entity file task.py.
    models_module = Path(model_paths[0]).stem if model_paths else "models"

    # 2.5 Canonicalize repository/service module names around their ENTITY.
    # Every downstream consumer binds these modules as
    # "<entity>_repository.py" / "<entity>_service.py" (repository class
    # names, the service header's imports, _repo_dict_keys, CLI wiring), so
    # ANY deviating declared filename — an invented interface/implementation
    # split like "sqlite_task_repository.py", or a bare "repository.py" —
    # would be rendered against a filename-derived entity that may not
    # exist, historically producing a silently EMPTY file that no syntax
    # or import gate could catch. Rename each repository/service file to
    # its resolved entity's canonical name; drop specs whose canonical
    # target is already claimed (duplicate classes across files break
    # sibling imports). Resolution order: declared entity -> filename-
    # derived entity -> first designed entity.
    def _rewrite_import_stems(old_stem, new_name):
        for s in manifest:
            s["imports_from"] = [
                (new_name[:-3] if Path(f).stem == old_stem else f)
                for f in s.get("imports_from", [])
            ]

    first_entity = _snake(sorted(entities_by_class)[0])
    claimed = set()  # filenames bound so far (any kind)
    kept = []
    for spec in manifest:
        if spec["kind"] not in ("repository", "service"):
            claimed.add(spec["file"])
            kept.append(spec)
            continue
        stem = Path(spec["file"]).stem
        kind_word = (
            "repository" if spec["kind"] == "repository" else "service"
        )
        suffix = "_%s" % kind_word
        declared = _snake(spec.get("entity") or "")
        derived = stem[: -len(suffix)] if stem.endswith(suffix) else ""
        entity = (
            declared if declared in entities_by_class
            else derived if derived in entities_by_class
            else declared or derived or first_entity
        )
        target = "%s%s.py" % (entity, suffix)
        if target in claimed:
            print(
                "    dropped %s (canonical %s already owns entity '%s')"
                % (spec["file"], target, entity),
                file=sys.stderr,
            )
            _rewrite_import_stems(stem, target)
            continue
        claimed.add(target)
        if spec["file"] != target:
            old_stem = stem
            spec["file"] = target
            spec["entity"] = entity
            _rewrite_import_stems(old_stem, target)
        kept.append(spec)
    manifest[:] = kept

    # CLI surface from the USER INTENTIONS, LLM-normalized. The LLM classifier
    # maps each intention to a language-agnostic (entity, operation) pair, so
    # a non-English or badly-worded prompt is interpreted semantically instead
    # of against an English regex/synonym table. The classified operations are
    # the AUTHORITATIVE signal for both whether a CLI surface is needed and
    # for its command shape. The deterministic compute_needs_cli regex gate
    # above remains only as a cheap, zero-LLM safety net (it can only ADD an
    # early CLI, never refuse one), so the agent is not dependent on it.
    cli_surface = None
    if entities_by_class:
        classified = classify_intentions(
            intentions, entities_by_class, verbose=verbose
        )
        if classified and not needs_cli:
            # The LLM normalized the intentions into data-management
            # operations even though the regex gate missed them (e.g. a
            # non-English prompt). That is an authoritative CLI signal.
            needs_cli = True
            if not manifest_has_cli and not any(
                s["kind"] == "cli" for s in manifest
            ):
                manifest.append({
                    "file": "cli.py",
                    "role": "command-line interface",
                    "kind": "cli",
                    "entity": "",
                    "imports_from": [],
                })
                if verbose:
                    print(
                        "    Intent gate (LLM-normalized): CLI required — "
                        "injecting cli.py"
                    )
        _paginated = bool(
            re.search(r"\b(page|pagina\w*)\b", (prompt_text or "").lower())
        )
        if classified:
            cli_surface = derive_cli_from_intents(
                classified, entities_by_class, verbose=verbose, page=_paginated
            )
        # CRUD-completeness guarantee: union the LLM-classified surface with
        # the deterministic regex surface so a dropped classification can't
        # silently remove a required CRUD command (prompt 21's customer-update).
        det_surface = derive_cli_surface(
            intentions, prompt_text, entities_by_class, verbose=verbose
        )
        cli_surface = _merge_cli_surfaces(cli_surface, det_surface)

    # 3. repositories (custom methods only; CRUD is generated).
    #
    # Design-time restriction: the repository design is constrained to the
    # CLI surface (project need) via repo_surface_constraint — the repo-
    # level analogue of the service's cli_surface_constraint. This bounds the
    # 4B model to the methods the CLI-driven service layer actually needs
    # instead of letting it enumerate every filter combination on a rich FK
    # graph (library_system's book_repository ~55 methods). The deterministic
    # pruners below remain as a backstop for when the model over-generates
    # anyway: schema-infeasible customs + 2+ 'and' permutation chains.
    repo_paths = [s["file"] for s in manifest if s["kind"] == "repository"]
    for rp in repo_paths:
        stem = Path(rp).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        repo_constraint = (
            repo_surface_constraint(cli_surface, ent_snake) if cli_surface else ""
        )
        if _design_into(
            rp, "repositories", _fmt_design_context(designs, compact=True),
            extra_context=repo_constraint,
        ) is None:
            return None, None

    # Backstop for when the model over-generates anyway. Run the deterministic
    # chain-prune FIRST (it cheaply drops 2+ 'and' permutation chains), so the
    # LLM infeasibility classifier below sees fewer methods -> a smaller prompt
    # (kept under the ~3.1k-token conversation budget).
    #   (#2) permutation CHAINS (a name chaining 2+ 'and' filters, e.g.
    #        get_books_with_active_loans_and_overdue_loans_and_low_copies).
    #        A single 'and' join (list_expenses_by_category_and_date_range) is
    #        a real query and survives; only the chain is dropped.
    _strip_repo_method_chains(designs, verbose=verbose)
    #   (#1) LLM semantic infeasibility: replaces the brittle regex verb/field
    #        token classification (_FEAS_* tables) that false-dropped methods
    #        on CRUD-verb/'update'/'delete' name tokens and non-English verbs.
    #        The LLM reads the designed schema + method names semantically
    #        (temp=0, schema-constrained JSON) and is robust to language; the
    #        SQL-schema validator during fill is the deterministic backstop.
    _strip_infeasible_repo_methods(designs, entities_by_class, verbose=verbose)

    # 4. services (constrained to the CLI surface, so every method is
    # CLI-drivable — primitive params, one method per command; no whole-object
    # signatures that would make the CLI sanitizer drop commands).
    #
    # Design-vs-CLI single source of truth (FIX 3 mitigation): the service is
    # constrained HERE to the deterministic intent-derived surface (built from
    # the LLM classifier in the block above, merged with the explicit-command
    # floor), and the service is RENDERED LATER (step 5.2) — AFTER
    # _reconcile_cli_design has back-propagated any CLI-required methods/params
    # into svc_design. So the shipped service always reflects the FINAL CLI
    # surface: the service renderer consumes the reconciled svc_design, not a
    # stale pre-CLI one. The bounded propagation remains the recovery path for
    # genuinely ambiguous prompts (data model not aligned with CLI section);
    # the two LLM design passes (service + CLI) may still disagree on NEW
    # commands, and that divergence is reconciled deterministically here.
    svc_paths = [s["file"] for s in manifest if s["kind"] == "service"]
    # INTERNAL CONTRACT anchor: extract the service methods the SPEC explicitly
    # declares (evidence-closed) and make them a design requirement — the
    # mirror of cli_surface_constraint, but anchored to the spec instead of the
    # CLI. Without it a spec method with no CLI command (renew_membership) is
    # dropped, and a wrong name (borrow_member) can replace a real one
    # (borrow_book). Underspecified prompts yield few/no required methods.
    service_contract = extract_service_contract(prompt_text, verbose=verbose)
    _contract_block = service_contract_constraint(service_contract)
    svc_constraint = "\n\n".join(
        x for x in (
            cli_surface_constraint(cli_surface) if cli_surface else "",
            _contract_block,
        ) if x
    )
    for sp in svc_paths:
        if _service_is_complex(cli_surface, entities_by_class):
            if verbose:
                print(
                    "    [design] %s: complex service (%d commands, %d entities)"
                    " — scoped split design" % (
                        sp,
                        len((cli_surface or {}).get("commands") or []),
                        len(entities_by_class),
                    )
                )
            # Split the service design into small per-entity scoped calls so
            # each conversation stays under the 4B model's attention window
            # (a monolithic design of a 28-method service hits ~5852 tokens).
            groups = _service_design_groups(cli_surface, entities_by_class, designs)
            merged = {"methods": []}
            failed = False
            for ent_cls, grp in groups.items():
                scoped_ctx = _scoped_fmt_design_context(
                    ent_cls, designs, entities_by_class, compact=True
                )
                # Every scoped service call sees the FULL spec contract so a
                # required method is never dropped by group scoping.
                scoped_cons = "\n\n".join(
                    x for x in (
                        _scoped_cli_constraint(grp["commands"]),
                        _contract_block,
                    ) if x
                )
                gdata = _design_module(
                    sp, "services", prompt_text, scoped_ctx, verbose,
                    extra_context=scoped_cons,
                )
                if gdata is None:
                    failed = True
                    break
                for m in gdata.get("methods") or []:
                    merged.setdefault("methods", []).append(m)
                for k, v in gdata.items():
                    if k != "methods":
                        merged.setdefault(k, v)
            if failed:
                # The scoped split is a best-effort optimization, never a
                # correctness requirement: fall back to the monolithic design.
                print("    [design] %s: scoped split failed — monolithic fallback" % sp,
                      file=sys.stderr)
                if _design_into(sp, "services", _fmt_design_context(designs, compact=True),
                                extra_context=svc_constraint) is None:
                    return None, None
            else:
                # Deduplicate methods by name (keep the first/richest).
                seen = set()
                deduped = []
                for m in merged.get("methods") or []:
                    nm = m.get("name") if isinstance(m, dict) else None
                    if nm and nm not in seen:
                        seen.add(nm)
                        deduped.append(m)
                merged["methods"] = deduped
                designs.append((sp, "services", merged))
                if verbose:
                    print("      - %s [services] %s"
                          % (sp, _describe_design("services", merged)))
        else:
            if _design_into(sp, "services", _fmt_design_context(designs, compact=True),
                            extra_context=svc_constraint) is None:
                return None, None

    # 5. CLI (targets constrained to designed service methods).
    # A CLI design failure is NOT fatal: the deterministic repos/service are
    # still valid, so keep them and generate cli.py via the per-file path
    # later (legacy _generate_file) rather than abandoning the whole
    # manifest-first pipeline to the volatile legacy multi-pass.
    cli_paths = [s["file"] for s in manifest if s["kind"] == "cli"]
    svc_design = next((d for p, k, d in designs if k == "services"), None)
    service_methods = (svc_design or {}).get("methods") or []
    cli_failed = False
    # CLI ← intentions (Approach B, LLM-classified). For prompts that NAME a
    # CLI explicitly (click/argparse/--flag), keep the LLM design. Otherwise
    # the command tree is the intent-derived surface, so the CLI matches
    # exactly what the user asked (no over-generation). _reconcile_cli_design
    # synthesizes any missing service method/repository below.
    explicit_cli = _prompt_specifies_cli(prompt_text) or any(
        (i.get("cli_command") or "").strip() for i in intentions
    )
    for cp in cli_paths:
        # POINT 2 (reverted): the deterministic surface is NOT a drop-in
        # substitute for the LLM CLI design — explicit commands carry an empty
        # target, and the reconcile/sanitize drops domain-verb commands
        # (overdue, history) and CRUD list commands whose options the
        # deterministic surface doesn't fully wire. A prompt that only vaguely
        # mentions a CLI ("use click") also needs the LLM to invent the tree.
        # Keep the open-ended _design_cli (then merge with the deterministic
        # surface); the LLM's proper targets survive the sanitizer.
        if explicit_cli or cli_surface is None:
            if _service_is_complex(cli_surface, entities_by_class) and cli_surface is not None:
                # Split the CLI design by command group so no single design
                # call packs the whole service + context (which hit ~7944
                # tokens on library_system). Each group designs only the
                # commands + service methods for its owner entity, then the
                # results are merged.
                groups = _service_design_groups(cli_surface, entities_by_class, designs)
                merged_cli = {"commands": []}
                cli_split_failed = False
                for ent_cls, grp in groups.items():
                    scoped_ctx = _scoped_fmt_design_context(
                        ent_cls, designs, entities_by_class, compact=True
                    )
                    grp_methods = [
                        m for m in service_methods
                        if _service_method_owner(m, entities_by_class) == ent_cls
                    ]
                    gdata = _design_cli(
                        prompt_text, scoped_ctx, grp_methods,
                        verbose, allow_new_targets=True,
                        entities_by_class=entities_by_class,
                        repair_methods=service_methods,
                    )
                    if gdata is None:
                        cli_split_failed = True
                        break
                    for c in gdata.get("commands") or []:
                        # A scoped CLI call is CONSTRAINED to its group's
                        # commands, but with allow_new_targets=True the model
                        # can still re-emit a command owned by ANOTHER entity
                        # (library: the Member group re-emits
                        # library/borrow/borrow, the Book group re-emits
                        # book/return). Appending those cross-entity
                        # re-emissions unions into a heavily duplicated tree
                        # (library: 4 groups -> 60 commands for a 30-command
                        # surface) that the deterministic collapse then has to
                        # rewire — the source of the return_book double-reshape
                        # thrash and the 60-command reconcile. Drop any command
                        # whose owner entity is a DIFFERENT group: it is
                        # designed by its own group, and re-added by
                        # _merge_cli_surfaces if the model missed it.
                        owner = _command_owner_entity(c, entities_by_class)
                        if owner and owner != ent_cls:
                            continue
                        merged_cli.setdefault("commands", []).append(c)
                if cli_split_failed:
                    # Best-effort split: fall back to the monolithic design.
                    print("    [design] %s: scoped CLI split failed — monolithic fallback" % cp,
                          file=sys.stderr)
                    data = _design_cli(
                        prompt_text, _fmt_design_context(designs, compact=True), service_methods,
                        verbose, allow_new_targets=True,
                        entities_by_class=entities_by_class,
                        repair_methods=service_methods,
                    )
                else:
                    data = merged_cli
            else:
                data = _design_cli(
                    prompt_text, _fmt_design_context(designs, compact=True), service_methods,
                    verbose, allow_new_targets=True,
                    entities_by_class=entities_by_class,
                    repair_methods=service_methods,
                )
            # Merge with the deterministic intent-derived surface so domain/
            # state commands the LLM missed (overdue, bulk-update, get-by-id)
            # survive the explicit-CLI path. The merge unions by (group, name),
            # keeping the LLM's richer options on collisions.
            if cli_surface is not None:
                data = _merge_cli_surfaces(data, cli_surface)
        else:
            data = cli_surface
        if data is None:
            print("    [design] %s: FAILED (will generate via per-file path)" % cp, file=sys.stderr)
            cli_failed = True
            continue
        # Reconcile wiring conflicts: bounded back-propagation into the
        # designs first (spec-token gated FK completion + CRUD/history
        # synthesis), deterministic sanitization as the backstop.
        data, service_methods = _reconcile_cli_design(
            data, prompt_text, entities_by_class, designs, verbose
        )
        if data is None:
            print("    [design] %s: FAILED (will generate via per-file path)" % cp, file=sys.stderr)
            cli_failed = True
            continue
        designs.append((cp, "cli", data))
        if verbose:
            print("      - %s [cli] commands=%d"
                  % (cp, len(data.get("commands") or [])))

    # Famille 1: back-propagate missing repository files. A CLI command that
    # references an entity (add_customer -> Customer) makes the service header
    # need self.<entity>_repo; if <entity>_repository.py was never designed,
    # the deterministic CRUD delegation would emit an AttributeError at
    # runtime. Synthesize the repo (empty customs -> deterministic CRUD).
    _synthesize_cli_repos(designs, entities_by_class, manifest)
    # Recompute repo_paths to include any repository file synthesized above.
    repo_paths = [s["file"] for s in manifest if s["kind"] == "repository"]

    # Service-contract coverage: every spec-declared internal method must be
    # present in the FINAL (post-reconcile/floor) service design. A missing
    # method is a real specification gap and is reported loudly — the anchor
    # that stops a spec method with no CLI command from silently vanishing.
    _svc_final = next((d for p, k, d in designs if k == "services"), None)
    for _cv in check_service_contract(service_contract, _svc_final):
        print("    [contract] VIOLATION: %s" % _cv, file=sys.stderr)

    # Deterministic floor for list_filters: cover the parameters the
    # designed service/repository signatures actually use. Declarations
    # from the models design always win (see _apply_filter_floors).
    _apply_filter_floors(entities_by_class, designs)
    # Deterministic floor for service impls on unambiguous aggregate
    # shapes (Dict-returning methods over a single date+numeric entity).
    _apply_impl_floors(entities_by_class, designs)

    # Exception names come ONLY from the schema-constrained exceptions
    # design (collected in step 1) — there is no spec-text floor anymore.

    # service_methods = the designed service methods (CLI targets must map
    # to them, so this is computed once here)
    svc_design = next((d for p, k, d in designs if k == "services"), None)
    service_methods = (svc_design or {}).get("methods") or []

    # Design context for structural validation — replaces every form of
    # spec-text sniffing: what MUST exist in the final tree is exactly what
    # the schema-constrained designs declared, nothing else.
    design_ctx = {
        "exceptions": list(exception_names),
        "entities": {
            cls: [
                f.get("name") for f in (ent.get("fields") or []) if f.get("name")
            ]
            for cls, ent in entities_by_class.items()
        },
        "service_file": svc_paths[0] if svc_paths else None,
        "service_design": svc_design,
        "service_methods": [
            m.get("name") for m in service_methods
            if isinstance(m, dict) and m.get("name")
        ],
        "db_file": db_file,
        "model_files": list(model_paths),
        "exception_files": sorted(
            {p for p, k, d in designs if k == "exceptions"}
        ),
    }

    # ---- Render phase (deterministic) ----
    files = {}
    svc_class = "App"
    if svc_paths:
        stem = Path(svc_paths[0]).stem
        if stem.endswith("_service"):
            stem = stem[: -len("_service")]
        svc_class = _camel(stem) + "Service"
    for path, kind, data in designs:
        if kind == "exceptions":
            files[path] = _render_exceptions_file(data)
        elif kind == "models":
            files[path] = _render_models_file(data)
        elif kind == "cli":
            files[path] = _render_cli_file(
                data, svc_class, entities_by_class, service_methods,
                verbose, db_path=db_file,
            )

    # ---- Fill phase (LLM, locked skeletons; deterministic contract bodies) ----
    if verbose:
        print("    Fill phase (service + repository custom methods)...")

    # 5.1 repository files: deterministic CRUD + stubs; UNIQUE-pair custom
    # methods (get_by_<a>_and_<b>) are rendered deterministically from the
    # designed unique_together by _render_repository_file.
    for rp in repo_paths:
        stem = Path(rp).stem
        ent_snake = stem[: -len("_repository")] if stem.endswith("_repository") else stem
        repo_design = next((d for p, k, d in designs if p == rp), {})
        files[rp] = _render_repository_file(
            ent_snake, repo_design, entities_by_class, exception_names,
            prompt_text=prompt_text, verbose=verbose,
            models_module=models_module,
        )

    # 5.2 service file: deterministic contract bodies; LLM fills only extras
    for sp in svc_paths:
        svc_design = next((d for p, k, d in designs if p == sp), {})
        repo_srcs = {p: files[p] for p in repo_paths}
        body = _render_service_file(
            svc_design, svc_class, designs, entities_by_class,
            prompt_text, exception_names, verbose,
            repo_sources=repo_srcs,
            models_module=models_module,
        )
        files[sp] = body
        # (#3) adopt bounded repository repairs made while filling this
        # service: the shipped repository file and the service contract
        # must stay consistent (the fill legally calls what was added).
        for p in repo_paths:
            if repo_srcs.get(p) != files.get(p):
                files[p] = repo_srcs[p]

    # 5.3 CLI fallback: when the CLI design failed, keep the deterministic
    # pipeline and generate cli.py via the per-file path instead of
    # abandoning everything to the volatile legacy multi-pass.
    if cli_failed:
        for spec in manifest:
            if Path(spec["file"]).stem == "cli" and spec["file"] not in files:
                if verbose:
                    print("    Generating %s via per-file path (CLI design failed)..." % spec["file"])
                content, status = _generate_file(
                    spec, manifest, prompt_text, files,
                    verbose=verbose, db_file=db_file,
                )
                if content:
                    # A CLI file must be invocable: the LLM per-file fallback
                    # can emit a click group without dispatching it, leaving
                    # `python3 cli.py <cmd> ...` a silent no-op (library_system
                    # __seed_Loan FK failure was traced to exactly this).
                    # Guarantee the entry point even on the fallback path.
                    if Path(spec["file"]).stem == "cli" and "if __name__" not in content:
                        content = content.rstrip() + "\n\nif __name__ == \"__main__\":\n    cli()\n"
                    files[spec["file"]] = content
                else:
                    print("    %s: %s" % (spec["file"], status), file=sys.stderr)

    # Inter-file invariant: a DESIGNED module must never ship blank or
    # class-less. A blank file parses as valid Python with no imports and no
    # definitions, which is exactly how an empty repository used to slip
    # past every downstream gate. Fail loudly instead of writing corruption.
    for path, kind, data in designs:
        content = files.get(path)
        if content is None or not content.strip():
            raise RuntimeError(
                "designed module %s rendered empty — refusing to write "
                "(inter-file consistency failure)" % path
            )
        if kind in ("repositories", "services") and "class " not in content:
            raise RuntimeError(
                "designed module %s rendered without a class "
                "(inter-file consistency failure)" % path
            )

    # Provisional database.py: repos/service import `from database import
    # Database`, but database.py is normally generated later (Phase 4) from
    # the final models. Synthesize it now from the DESIGNED model files (by
    # declared kind, never by filename sniffing) so this validation pass
    # resolves the sibling import; the outer flow regenerates it afterward.
    model_srcs = {p: files[p] for p in model_paths if p in files}
    if "database.py" not in files and model_srcs:
        model_classes = _extract_model_ast(model_srcs, paths=list(model_srcs))
        if model_classes:
            files["database.py"] = _generate_database_file(model_classes, db_file)

    # ensure every manifest file exists: a declared main/app entry point gets
    # a deterministic renderer; invented "other" modules are dropped rather
    # than shipped empty (an empty file is worse than an absent one, and a
    # file with no schema-constrained design contract has no business being
    # written by hand).
    for spec in manifest:
        fn = spec["file"]
        if fn in files:
            continue
        kind = spec.get("kind")
        if kind == "main" or Path(fn).stem in ("main", "app"):
            files[fn] = _render_main_file(files, db_file)
            continue
        if verbose:
            print(
                "    dropped invented module %s (no design contract)" % fn,
                file=sys.stderr,
            )

    # NOTE: _multi_pass (run.py) runs the authoritative validation
    # (_check_syntax_and_imports + _check_structural) over this tree. Running
    # it here too produced a duplicate "Validation: N issue(s)" line in the
    # log that looked like the repair repeated the same message, so the
    # validation pass happens ONLY in _multi_pass now. The provisional
    # database.py above is still required so the sibling import resolves while
    # _manifest_first_blocks returns.

    # LAST-RESORT entry-point guarantee: the AST repair above can rewrite a
    # broken cli.py (e.g. a syntax error in the LLM/merged click group) and
    # drop the `if __name__ == "__main__": cli()` appended earlier. A CLI file
    # with no dispatch is a silent no-op — `python3 cli.py <cmd> ...` defines
    # the group and exits 0 without running anything, so every seed/intent
    # that relies on it either vacuously passes or FK-fails (library_system
    # __seed_Loan was traced to exactly this). Re-assert the dispatch on the
    # FINAL output so the CLI is always invocable.
    for fn, content in files.items():
        if Path(fn).stem == "cli" and "if __name__" not in content:
            files[fn] = content.rstrip() + "\n\nif __name__ == \"__main__\":\n    cli()\n"

    return files, design_ctx
