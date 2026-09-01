"""Manifest-first generation: design everything, render mechanically, fill only bodies.

The ``_manifest_first_blocks`` function is the heart of the manifest-first
pipeline: it drives the schema-constrained design phase, then the
deterministic render phase, then the LLM fill phase. It never lets the
4B model write whole file bodies — the LLM only fills business bodies
inside locked skeletons.
"""

import sys
from pathlib import Path

from agentlib.design import _generate_manifest, _validate_manifest
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
    cli_surface_constraint,
)
from agentlib.pipeline.cli_propagate import _reconcile_cli_design
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
from agentlib.checks.ast_utils import (
    _extract_model_ast,
    _check_syntax_and_imports,
    _check_structural,
    _extract_defined_names,
)
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

    # 2. models
    model_paths = [s["file"] for s in manifest if s["kind"] == "models"]
    for mp in model_paths:
        data = _design_into(mp, "models", _fmt_design_context(designs))
        if data is None:
            return None, None
        for ent in data.get("entities") or []:
            if isinstance(ent, dict) and ent.get("name"):
                entities_by_class[ent["name"]] = ent

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

    # CLI surface from the USER INTENTIONS. The LLM classifies each intention
    # into (entity, operation) semantically (fixing "invoice line" -> InvoiceLine
    # that the regex could not), then a mechanical rule table derives the
    # command shape (rich for CRUD/report, generic <op>_<entity>(id) otherwise).
    cli_surface = None
    if needs_cli and entities_by_class:
        classified = classify_intentions(
            intentions, entities_by_class, verbose=verbose
        )
        if classified:
            cli_surface = derive_cli_from_intents(
                classified, entities_by_class, verbose=verbose
            )

    # 3. repositories (custom methods only; CRUD is generated)
    repo_paths = [s["file"] for s in manifest if s["kind"] == "repository"]
    for rp in repo_paths:
        if _design_into(rp, "repositories", _fmt_design_context(designs)) is None:
            return None, None

    # 4. services (constrained to the CLI surface, so every method is
    # CLI-drivable — primitive params, one method per command; no whole-object
    # signatures that would make the CLI sanitizer drop commands).
    svc_paths = [s["file"] for s in manifest if s["kind"] == "service"]
    svc_constraint = cli_surface_constraint(cli_surface) if cli_surface else ""
    for sp in svc_paths:
        if _design_into(sp, "services", _fmt_design_context(designs),
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
        if explicit_cli or cli_surface is None:
            data = _design_cli(
                prompt_text, _fmt_design_context(designs), service_methods,
                verbose, allow_new_targets=True,
            )
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

    # Mechanical AST validation of the generated tree (same as the legacy
    # path): syntax, sibling-import resolution, structural checks.
    all_exports = {Path(f).stem: _extract_defined_names(c) for f, c in files.items()}
    ast_errors, ast_fixes = _check_syntax_and_imports(files, all_exports)
    for fp, fixed in ast_fixes.items():
        files[fp] = fixed
    struct_errors = _check_structural(files, design_ctx)
    if verbose and (ast_errors or struct_errors):
        print("    Validation: %d issue(s)" % (len(ast_errors) + len(struct_errors)))
        for e in (ast_errors + struct_errors)[:5]:
            print("      - %s" % e)

    return files, design_ctx
