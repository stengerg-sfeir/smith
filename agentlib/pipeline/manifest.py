"""Manifest-first generation: design everything, render mechanically, fill only bodies.

The ``_manifest_first_blocks`` function is the heart of the manifest-first
pipeline: it drives the schema-constrained design phase, then the
deterministic render phase, then the LLM fill phase. It never lets the
4B model write whole file bodies — the LLM only fills business bodies
inside locked skeletons.
"""

import ast
import json
import os
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
    repo_spec_constraint,
    repo_surface_constraint,
)
from agentlib.pipeline.cli_spec import (
    align_surface_to_design,
    build_prompt_cli_surface,
    surface_command_paths,
)
from agentlib.pipeline.value_vocab import spec_enum_values
from agentlib.pipeline.field_rules import extract_field_rules
from agentlib.pipeline.amount_rules import extract_amount_ops
from agentlib.generation.field_guard import apply_field_guards
from agentlib.generation.state_guard import apply_state_guards
from agentlib.pipeline.state_rules import extract_state_rules
from agentlib.pipeline.pair_rules import (
    apply_time_pair_inputs,
    extract_time_pairs,
)
from agentlib.generation.overlap_guard import apply_overlap_guard
from agentlib.pipeline.overlap_rules import extract_overlap_rules
from agentlib.generation.active_guard import apply_active_guard
from agentlib.pipeline.active_rules import extract_active_rules
from agentlib.generation.overlap_guard import _table_from_source
from agentlib.generation.reference_guard import apply_reference_guard
from agentlib.pipeline.reference_rules import extract_reference_rules
from agentlib.generation.audit_guard import (
    apply_audit_guards,
    strip_audit_cascade,
)
from agentlib.pipeline.audit_rules import extract_audit_rules
from agentlib.generation.notify_guard import (
    NOTIFICATIONS_MODULE,
    apply_notify_guards,
    render_notifications_module,
)
from agentlib.pipeline.notify_rules import extract_notify_rules
from agentlib.pipeline.ownership_rules import extract_ownership_rule
from agentlib.pipeline.role_rules import extract_role_rules
from agentlib.pipeline.softdelete_rules import extract_soft_delete_rules
from agentlib.pipeline.cli_propagate import _reconcile_cli_design
from agentlib.pipeline.service_contract import (
    extract_service_contract,
    service_contract_constraint,
    check_service_contract,
    apply_service_contract_floors,
    apply_service_contract_params,
)
from agentlib.generation.service_render import (
    _apply_filter_floors,
    _apply_impl_floors,
    _apply_derived_total_floors,
    _apply_pagination_floors,
    _apply_report_count_floors,
    _apply_sort_floors,
    _ensure_derived_total_methods,
    _render_service_file,
    attach_contract_impls,
)
from agentlib.kernel.service import declared_money_keys
from agentlib.generation.model_render import (
    _render_exceptions_file,
    _render_models_file,
)
from agentlib.generation.cli_render import _render_cli_file, _render_main_file
from agentlib.generation.money_render import (
    MONEY_MODULE,
    money_display_enabled,
    money_field_names,
    render_money_module,
)
from agentlib.generation.repo_render import (
    _capability_tokens,
    _drop_functions,
    _render_repository_file,
    _stemmed_tokens,
)
from agentlib.pipeline.method_contract import extract_method_contracts
from agentlib.pipeline.model_defaults import (
    apply_model_defaults,
    extract_model_defaults,
)
from agentlib.checks.ast_utils import _extract_model_ast
from agentlib.naming import _generate_database_file, _snake, _camel
from agentlib.pipeline.generate import _generate_file


class _NoEntityScript(Exception):
    """Raised when a manifest declares no data entities (a script-like
    project such as a hello-world app). The multi-pass pipeline is
    entity-driven; such a spec degrades to single-pass generation rather
    than failing outright."""


def _dedupe_manifest_files(manifest, verbose=False):
    """Keep ONE manifest entry per file, preserving order.

    The layout LLM sometimes lists the SAME file once per entity it holds —
    prompt 34's layout declares ``models.py`` TWICE (entity ``order``, then
    ``order_line``). Every downstream path list is built from ``manifest``
    (``model_paths``, ``repo_paths``, ``svc_paths``), so a duplicate path is
    designed TWICE and rendered TWICE, and the second render silently
    OVERWRITES the first.

    That is exactly how 34 lost the ``Customer`` class: the first
    ``models.py`` design carried ``Order``/``OrderLine`` AND the
    back-propagated ``Customer``, the second carried only
    ``Order``/``OrderLine``, and the second write won — so
    ``customer_repository.py``'s ``from models import Customer`` could not
    resolve and the whole prompt aborted before writing anything.

    One file, one entry is an invariant the rest of the pipeline assumes.
    """
    seen = set()
    kept = []
    for spec in manifest:
        name = spec.get("file")
        if name in seen:
            if verbose:
                print("    dropped duplicate manifest entry for %s" % name)
            continue
        seen.add(name)
        kept.append(spec)
    if len(kept) != len(manifest):
        manifest[:] = kept
    return len(manifest)


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


def _drop_orphan_repositories(designs, entities_by_class, manifest,
                             verbose=False):
    """Remove repository designs whose OWN entity was never designed.

    A repository file imports its entity from the models module and is the
    only consumer of that name — ``customer_repository.py`` doing
    ``from models import Customer`` while ``models.py`` renders only
    ``Order``/``OrderLine`` is an unresolved import that aborts the whole
    prompt (34, reproducible: the design invented a Customer repository for a
    prompt that never mentions customers).

    The entity is resolved from the file stem EXACTLY as the renderer does
    (``customer_repository`` -> ``Customer``). When that class is absent from
    ``entities_by_class`` nothing ever designed it, so the repository is
    over-generation: drop the design and its manifest entry, so no file is
    rendered and the service header wires no ``self.customer_repo`` (the
    header is fed by the repository files that survive). A repository whose
    entity IS designed — every named prompt — is untouched.

    Runs AFTER ``_synthesize_cli_repos``: a repository legitimately needed by
    a ``--<entity>_id`` option has had its model synthesized by then, so only
    the genuinely orphaned repositories are removed.
    """
    kept = []
    dropped = []
    for path, kind, data in designs:
        if kind != "repositories":
            kept.append((path, kind, data))
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        cls = _camel(ent_snake)
        if cls in entities_by_class:
            kept.append((path, kind, data))
            continue
        dropped.append((path, cls))
    if not dropped:
        return []
    designs[:] = kept
    bad_files = {path for path, _ in dropped}
    manifest[:] = [
        spec for spec in manifest if spec.get("file") not in bad_files
    ]
    for path, cls in dropped:
        print(
            "    dropped %s (entity '%s' was never designed)" % (path, cls),
            file=sys.stderr,
        )
    if verbose:
        for path, cls in dropped:
            print("      - orphan repository %s -> entity %s" % (path, cls))
    return dropped


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


def _normalise_design_defaults(entities_by_class):
    """Flatten a TYPED design ``default`` wrapper to its scalar value.

    The design model emits a declared default either as a plain scalar
    (``"default": "cash"``) or as a typed wrapper
    (``"default": {"value": False, "type": "bool"}``). Every consumer
    downstream reads ``default`` as a scalar: the model renderer writes
    ``= <default>`` on the dataclass, the create recipe builds
    ``<field>=(<field> if <field> is not None else <default>)``, and
    ``_nullable_or_defaulted`` treats "has a default" as "an omitted value is
    safe". An un-normalised wrapper therefore makes a real default invisible:
    expenses' ``is_recurring`` (``{"value": False, "type": "bool"}``) rendered
    with NO ``= False`` and the create path passed the caller's ``None``
    straight into a NOT NULL column. Normalised once, in place, where the
    entities are collected.
    """
    for ent in (entities_by_class or {}).values():
        if not isinstance(ent, dict):
            continue
        for f in ent.get("fields") or []:
            if not isinstance(f, dict):
                continue
            default = f.get("default")
            if isinstance(default, dict) and "value" in default:
                f["default"] = default.get("value")


def _repo_called_methods(service_src, repo_attr):
    """Method names called on ``self.<repo_attr>`` in a rendered service."""
    if not service_src:
        return None
    try:
        tree = ast.parse(service_src)
    except SyntaxError:
        return None
    called = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == repo_attr
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
        ):
            called.add(node.func.attr)
    return called


def _ordered_tokens(text):
    """The lowercase alphanumeric tokens of a sentence, IN ORDER (no stemming).

    Used for the contiguity test below, where the stemmed SET would blur the
    boundary the test needs: ``_stemmed_tokens`` doubles every plural into its
    singular, so "find books by author" reads as [.., find, books, book, by,
    author] and no method name is ever contiguous in it.
    """
    return [raw for raw in re.split(r"[^a-z0-9]+", (text or "").lower()) if raw]


def _spelled_in_bullet(name, bullet_seq):
    """True when the method's own name tokens appear CONTIGUOUSLY in the bullet.

    The specification bullet "SQLite storage with CRUD + find books by author"
    spells ``find_books_by_author`` ([find, books, by, author]) and does NOT
    spell ``list_authors_with_books`` ([list, authors, with, books]): the
    spelling the specification wrote is the spelling it asked for, so between
    two unreached methods naming the same capability the spelled one survives.
    """
    toks = [t for t in (name or "").lower().split("_") if t]
    if not toks or len(toks) > len(bullet_seq):
        return False
    for i in range(len(bullet_seq) - len(toks) + 1):
        if bullet_seq[i:i + len(toks)] == toks:
            return True
    return False


def _prune_uncalled_repo_customs(repo_paths, designs, files, service_src,
                                 prompt_text):
    """Drop repository customs the service never calls and the spec never names.

    A repository method nobody can reach is a second source of truth for the
    same table, free to diverge: expenses' repository-level ``export_to_csv``
    and ``detect_recurring`` duplicate the SERVICE methods of the same name,
    which build their result from ``list()``. The repository's own
    specification bullet keeps genuinely spec-mandated duties alive however
    unreachable they look — ``get_monthly_report`` / ``get_yearly_summary``
    ("monthly/yearly aggregation queries"), ``get_expenses_for_category``
    ("find expenses for a category"), ``check_budget_exceeded`` ("check if a
    category has exceeded its budget"). Pruning is skipped for any repository
    the prompt does not name, so an unspecified project is left alone.

    ONE capability stated by the bullet, spelled TWICE by two unreached
    methods, is a single duty implemented twice — and the intersection test
    above is too weak to see it, because the bullet names the capability's
    OBJECT word ("find books by author" carries 'books') and both spellings
    therefore pass. Between them, the one the bullet itself SPELLS survives:
    AuthorRepository is the measured case, where the bullet keeps
    ``find_books_by_author`` and drops ``list_authors_with_books`` (both read
    as the capability {'books'}).
    """
    for rp in repo_paths:
        design = next((d for p, k, d in designs if p == rp), None)
        if not isinstance(design, dict):
            continue
        methods = design.get("methods") or []
        if not methods:
            continue
        stem = Path(rp).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        called = _repo_called_methods(service_src, ent_snake + "_repo")
        if called is None:
            continue
        bullet = repo_spec_constraint(prompt_text, ent_snake)
        if not bullet:
            continue
        bullet_tokens = _stemmed_tokens(bullet)
        bullet_seq = _ordered_tokens(bullet)
        dropped = []
        # Unreached customs the bullet's wording keeps alive, grouped by the
        # capability they name ({'books'} under both spellings of
        # AuthorRepository's find-books duty).
        by_capability: dict[frozenset, list] = {}
        for m in methods:
            name = m.get("name") or ""
            if not name or name in called:
                continue
            _, content = _capability_tokens(name, ent_snake, _camel(ent_snake))
            if not content or (content & bullet_tokens):
                if content:
                    by_capability.setdefault(frozenset(content), []).append(m)
                continue
            dropped.append(name)
        # One capability, two unreached spellings: keep the spelling the bullet
        # writes (its name tokens contiguous in the bullet), drop the other.
        # A capability named ONCE is left alone — the bullet asked for it.
        for content, group in by_capability.items():
            if len(group) < 2:
                continue
            spelled = [
                m for m in group
                if _spelled_in_bullet(m.get("name") or "", bullet_seq)
            ]
            keep = spelled[0] if spelled else group[0]
            for m in group:
                if m is not keep:
                    dropped.append(m.get("name") or "")
        if dropped:
            dropped_set = set(dropped)
            design["methods"] = [
                m for m in methods
                if (m.get("name") or "") not in dropped_set
            ]
            files[rp] = _drop_functions(files[rp], dropped_set)


def _apply_derived_total_surface(cli_surface, entities_by_class):
    """Drop a DERIVED total from the CLI surface and add its calculation.

    A surface reaches this function from EITHER path — the derived one
    (``derive_cli_surface``, which already skips derived fields) or the
    spec-enumerated one (``build_prompt_cli_surface``, which reads the
    specification's own option list). Only the first honoured the derivation,
    so a specification that enumerates its CLI still demanded a total it had
    just said must be calculated (prompt 28's ``invoice add --total-amount``).
    Filtering the FINAL surface covers both paths in one place.

    In place; returns the same surface.
    """
    if not cli_surface:
        return cli_surface
    derived = {
        f
        for ent in (entities_by_class or {}).values()
        if isinstance(ent, dict)
        for f in (ent.get("derived_fields") or [])
    }
    if derived:
        for c in cli_surface.get("commands") or []:
            if not isinstance(c, dict):
                continue
            opts = c.get("options")
            if not isinstance(opts, list):
                continue
            c["options"] = [
                o for o in opts
                if not (
                    isinstance(o, dict)
                    and (
                        o.get("field") in derived
                        or (isinstance(o.get("name"), str)
                            and o["name"].lstrip("-").replace("-", "_") in derived)
                    )
                )
            ]
    commands = cli_surface.setdefault("commands", [])
    for cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict) or not ent.get("derived_total"):
            continue
        e_snake = _snake(cls)
        if any(
            c.get("group") == [e_snake] and c.get("name") == "calculate-total"
            for c in commands
        ):
            continue
        commands.append({
            "group": [e_snake],
            "name": "calculate-total",
            "options": [
                {"name": "--id", "required": True, "type": "int", "field": "id"},
            ],
            "target": "calculate_%s_total" % e_snake,
        })
    return cli_surface


def _op_matches(cmd_name, op_name):
    """True when a command name denotes the operation ``op_name``.

    The specification names the operation as a noun the code spells as a verb
    ("withdrawals" -> ``withdraw``), and the stem is resolved by
    ``amount_rules._op_stem``. Exact-or-prefix in either direction keeps a
    command named ``deposit`` matching the stem ``deposit`` without letting an
    unrelated command through (a two-letter stem is ignored).
    """
    if not cmd_name or not op_name or len(op_name) < 4:
        return False
    return cmd_name == op_name or cmd_name.startswith(op_name) or \
        op_name.startswith(cmd_name)


def _apply_amount_op_surface(cli_surface, entities_by_class, amount_ops):
    """Give each implicit-amount OPERATION its ``--amount`` option.

    The specification names the operation and its direction but never the
    amount ("Deposits increase the balance and withdrawals decrease it",
    prompt 31): the amount is therefore the operation's own parameter, and
    without the option the command cannot be invoked at all (the shipped
    ``account deposit --id 1`` had no way to say how much). Applied to the
    FINAL surface, so a specification that ENUMERATES its CLI is covered too —
    and the service design, which is constrained to this surface, then carries
    the parameter as well.
    """
    if not cli_surface or not amount_ops:
        return cli_surface
    for cls, spec in amount_ops.items():
        e_snake = _snake(cls)
        for c in cli_surface.get("commands") or []:
            if not isinstance(c, dict):
                continue
            if e_snake not in [str(g) for g in (c.get("group") or [])]:
                continue
            if not any(
                _op_matches(str(c.get("name") or ""), op["name"])
                for op in spec["ops"]
            ):
                continue
            opts = c.setdefault("options", [])
            if any(
                isinstance(o, dict) and o.get("field") == "amount"
                for o in opts
            ):
                continue
            opts.append({
                "name": "--amount",
                "required": True,
                "type": "int",
                "field": "amount",
            })
    return cli_surface


def _ensure_amount_param(method, param):
    """Make sure the operation accepts the amount the caller types."""
    params = method.get("params")
    if not isinstance(params, list):
        method["params"] = [
            {"name": "id", "type": "int"}, {"name": param, "type": "float"},
        ]
        return
    for p in params:
        if isinstance(p, dict) and p.get("name") == param:
            return
    params.append({"name": param, "type": "float"})


def _ensure_amount_op_methods(entities_by_class, designs, amount_ops):
    """Attach the deterministic delta body to each implicit-amount operation.

    The body is the ``contract_effects`` recipe over an ``amount_delta``: the
    anchor row is loaded, the field moves by the caller's signed amount, and a
    DECREASING operation whose spec states the refusal first checks that the
    result stays non-negative. Rendered rather than filled because the fill
    already shipped this method as an unconditional raise
    ("Withdrawal amount is required but not provided").
    """
    if not amount_ops:
        return
    for cls, spec in amount_ops.items():
        e_snake = _snake(cls)
        field = spec["field"]
        svc_design = next(
            (d for p, k, d in designs or []
             if k == "services" and str(p) == "%s_service.py" % e_snake),
            None,
        )
        if not isinstance(svc_design, dict):
            continue
        methods = svc_design.setdefault("methods", [])
        for op in spec["ops"]:
            method_name = "%s_%s" % (op["name"], e_snake)
            impl = {
                "kind": "contract_effects",
                "entity": e_snake,
                "id_param": "id",
                "effects": [{
                    "kind": "amount_delta",
                    "cls": cls,
                    "field": field,
                    "sign": op["sign"],
                    "param": op["amount_param"],
                    "target": "self",
                    "non_negative": bool(op.get("non_negative")),
                }],
            }
            method = next(
                (m for m in methods
                 if isinstance(m, dict) and m.get("name") == method_name),
                None,
            )
            if method is None:
                method = {
                    "name": method_name,
                    "params": [
                        {"name": "id", "type": "int"},
                        {"name": op["amount_param"], "type": "float"},
                    ],
                    "returns": "bool",
                }
                methods.append(method)
            _ensure_amount_param(method, op["amount_param"])
            method["impl"] = impl


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
    # One file, one manifest entry: a layout that lists the same file twice
    # (prompt 34's `models.py` under both `order` and `order_line`) would be
    # designed and rendered twice, and the SECOND render would silently
    # overwrite the first — losing the back-propagated `Customer` class and
    # aborting the prompt on `from models import Customer`.
    _dedupe_manifest_files(manifest, verbose=verbose)

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

    # A typed ``default`` wrapper is flattened to its scalar value BEFORE any
    # renderer or create-recipe reads it (see _normalise_design_defaults).
    _normalise_design_defaults(entities_by_class)

    # A pair of timestamps the specification COMPARES ("Each appointment must
    # always end after it starts … start and end time are identical", prompt 54)
    # is the CALLER's input, never a stamp. The design model marks such a pair
    # auto:"now" — it reads "a time field" and reaches for datetime.now() — and
    # every layer then hides it: _derive_options omits auto-now columns from
    # `add`, the dataclass stamps it, and the service takes neither, so the
    # caller cannot state the very interval the prompt compares. Cleared HERE,
    # before the CLI surface is derived from these fields.
    _time_pairs = extract_time_pairs(prompt_text, entities_by_class)
    if _time_pairs:
        if verbose:
            print("    [models] spec compared time pairs (inputs): %r" % ({
                _snake(cls): (start.get("name"), end.get("name"))
                for cls, (start, end) in _time_pairs.items()
            },))
        apply_time_pair_inputs(_time_pairs, entities_by_class)

    # A total the specification DERIVES from child rows is marked HERE — before
    # the CLI surface is derived — so ``--<total>`` is never offered as an input
    # on add/update (prompt 22/28). The pass runs again after the service design,
    # once a total parameter the design invented can also be removed.
    _apply_derived_total_floors(entities_by_class, designs, prompt_text)

    # 2.4 Spec-declared field defaults, transcribed from the PROMPT alone.
    # The design LLM is asked to stamp ``"default"`` when the spec declares
    # one, but a 4B model drops it — library_system's ``is_active (default
    # True)`` and ``available_copies (default 1)`` then render as REQUIRED
    # constructor arguments, so the spec's default is lost and a caller that
    # omits the field gets a TypeError instead of the specified value (S16).
    # Independent source: the prompt states the default, the generated code
    # never feeds this scan, and only a field a designed entity already
    # carries can be stamped.
    # Spec-declared FIELD VALIDATIONS, transcribed from the prompt alone (C6):
    # "The email must be valid, age must be between 18 and 70, and salary must
    # be positive" (prompt 09) states a domain nothing ever enforced — the
    # shipped add_employee built the row with no check at all. Read once here,
    # applied to the rendered service below.
    _field_rules = extract_field_rules(prompt_text, entities_by_class)
    if _field_rules and verbose:
        print("    [models] spec field validations: %r" % (_field_rules,))

    # Spec-declared AMOUNT operations (C1) — a delta on a numeric field whose
    # amount the specification never names ("Deposits increase the balance and
    # withdrawals decrease it", prompt 31). Read once here; the surface gains
    # the missing ``--amount`` and the service gains the deterministic delta
    # body (with the spec's own non-negative refusal) below.
    _amount_ops = extract_amount_ops(prompt_text, entities_by_class)
    if _amount_ops and verbose:
        print("    [models] spec amount operations: %r" % (_amount_ops,))

    # Spec-declared STATE TRANSITIONS (C2) — "A cancelled order cannot be
    # shipped, and a shipped order cannot be cancelled" (prompt 32). The
    # shipped operations refused only the IDEMPOTENT repeat; the forbidden
    # SOURCE states were never checked. Read once here, injected into the
    # rendered operations below.
    _state_rules = extract_state_rules(prompt_text, entities_by_class)
    if _state_rules and verbose:
        print("    [models] spec state transitions: %r" % (_state_rules,))

    # Spec-declared OVERLAP rule (C3) — "A room cannot have two overlapping
    # reservations" (prompt 27). Nothing enforced it, so two reservations for
    # the same room over the same nights both persisted. Read once here; the
    # reservation repository gains the existence test and the service's create
    # path gains the refusal below.
    _overlap_rules = extract_overlap_rules(prompt_text, entities_by_class)
    if _overlap_rules and verbose:
        print("    [models] spec overlap rules: %r" % (_overlap_rules,))

    # Spec-declared "at most one ACTIVE row per resource" (C4) — "a book can
    # have at most one active loan" (prompt 26). Nothing enforced it, so a book
    # could be on loan twice. Read once here; applied to the rendered loan
    # repository and service below.
    _active_rules = extract_active_rules(prompt_text, entities_by_class)
    if _active_rules and verbose:
        print("    [models] spec at-most-one-active: %r" % (_active_rules,))

    # Spec-declared REFERENTIAL guard on DELETE (C5) — "A category cannot be
    # deleted while products still belong to it" (prompt 36). Nothing enforced
    # it, so a referenced category was deleted and its products orphaned.
    _reference_rules = extract_reference_rules(prompt_text, entities_by_class)
    if _reference_rules and verbose:
        print("    [models] spec referential delete guards: %r"
              % (_reference_rules,))

    # Spec-declared AUDIT TRAIL (E1) — "Every creation, update and deletion
    # must also produce an audit record" (prompt 33). The design builds the
    # audit entity and wires its repository, but nothing ever WRITES a row.
    # Two halves here: the audit table must not CASCADE (an audit row has to
    # survive the delete it records — stripped BEFORE models render, since the
    # DDL is derived from the entity), and the writes are spliced into the
    # service's create/update/delete below.
    _audit_rules = extract_audit_rules(prompt_text, entities_by_class)
    if _audit_rules:
        for _rule in _audit_rules.values():
            strip_audit_cascade(entities_by_class, _rule["audit_cls"])
        if verbose:
            print("    [models] spec audit trail: %r" % (_audit_rules,))

    # Spec-declared NOTIFICATION requirement (E2) — "When an order is
    # confirmed, the application must send a notification. Define a
    # notification service abstraction ..." (prompt 40). The confirmation sent
    # nothing and no abstraction existed. The rule carries everything the
    # renderer needs: which method notifies, the id it reports, and the entity
    # field a notification should be addressed to.
    _notify_rules = extract_notify_rules(prompt_text, entities_by_class)
    for _ncls, _nrule in _notify_rules.items():
        _nrule["entity"] = _ncls
        _nrule["id_param"] = _snake(_ncls) + "_id"
        for _f in (entities_by_class.get(_ncls) or {}).get("fields") or []:
            _fname = (_f or {}).get("name") or ""
            if _fname.endswith("_id") and _fname != "id":
                _nrule["recipient_field"] = _fname
                break
    if _notify_rules and verbose:
        print("    [models] spec notification: %r" % (_notify_rules,))

    # Spec-declared OWNERSHIP scoping (E3) — "A user can only read, modify or
    # delete their own documents" (prompt 38). The baseline rendered a service
    # where any caller could list every document, and where
    # ``document update --user-id`` only chose WHICH OWNER TO WRITE, i.e. a way
    # to hand a document to somebody else. Read once here; carried in
    # ``design_ctx`` and imposed by the finalize phase (run.py), because it
    # must survive ``_restore_service_signatures``.
    _ownership_rule = extract_ownership_rule(prompt_text, entities_by_class)
    if _ownership_rule and verbose:
        print("    [models] spec ownership rule: %r" % (_ownership_rule,))

    # Spec-declared ROLE policy (E4) — "Administrators can manage products and
    # users. Normal users can create orders and view their own orders but
    # cannot modify products or other users." (prompt 39). The baseline rendered
    # every command open to anyone: no command identified its caller, and
    # nothing ever read the role column. Read once here; carried in
    # ``design_ctx`` and imposed by the finalize phase, like the ownership rule.
    _role_rule = extract_role_rules(prompt_text, entities_by_class)
    if _role_rule and verbose:
        print("    [models] spec role rule: %r" % (_role_rule,))

    # Spec-declared SOFT DELETE (14) — "Deleting a project must be implemented
    # as a soft delete: the project remains in the database but is no longer
    # returned by normal listing operations." The design carries the
    # ``deleted_at`` column but deletes the row outright and never filters on
    # it. Read once here; imposed on the rendered repositories by the finalize
    # phase (run.py), after every renderer has run.
    _soft_delete_rule = extract_soft_delete_rules(prompt_text, entities_by_class)
    if _soft_delete_rule and verbose:
        print("    [models] spec soft delete: %r" % (_soft_delete_rule,))

    _spec_defaults = extract_model_defaults(prompt_text)
    if _spec_defaults:
        if verbose:
            print("    [models] spec defaults: %r" % _spec_defaults)
        apply_model_defaults(designs, _spec_defaults, verbose=verbose)

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
    # The methods the SPECIFICATION declares (evidence-closed) — needed BOTH
    # to resolve the spec's own CLI surface here and as a service-design
    # requirement further down.
    service_contract = extract_service_contract(prompt_text, verbose=verbose)
    # A specification that ENUMERATES its command line has already fixed the
    # CLI surface. Take it verbatim (group chain, command names, option names,
    # required/optional) instead of designing a CLI and unioning the two: the
    # union is what shipped commands the spec never asked for, under group and
    # option names the spec never used.
    prompt_surface = build_prompt_cli_surface(
        prompt_text, entities_by_class,
        (service_contract or {}).get("required_methods"),
    )
    if prompt_surface is not None and verbose:
        print("      - spec-enumerated CLI surface: %d command(s)"
              % len(prompt_surface.get("commands") or []))
    # The option NAMES the specification wrote. An option it named is
    # rendered exactly as named — a bool it wrote as `[--recurring]` never
    # gains a synthesized `--no-recurring` twin, which is a command-line
    # name the specification never asked for. Read from the spec surface,
    # never from a domain word list.
    spec_option_names = sorted({
        o.get("name")
        for c in ((prompt_surface or {}).get("commands") or [])
        for o in (c.get("options") or [])
        if isinstance(o, dict) and isinstance(o.get("name"), str)
    })
    # Value vocabularies the specification declares for a FIELD
    # (``payment_method (cash/card/transfer)``), restricted to fields the
    # DESIGNED entities actually carry — a parenthesised slash-list in prose
    # must not constrain an unrelated option.
    _field_names = {
        f.get("name")
        for ent in (entities_by_class or {}).values()
        if isinstance(ent, dict)
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }
    enum_values = {
        k: v for k, v in spec_enum_values(prompt_text).items()
        if k in _field_names
    }
    if enum_values and verbose:
        print("    [cli] spec value vocabularies: %r" % (enum_values,))
    cli_surface = None
    if prompt_surface is not None:
        cli_surface = prompt_surface
    elif entities_by_class:
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
    # Both surface paths converge here: a specification that ENUMERATES its
    # CLI never passed through the derived path, so the derived-total filter
    # has to run on the FINAL surface.
    cli_surface = _apply_derived_total_surface(cli_surface, entities_by_class)
    cli_surface = _apply_amount_op_surface(
        cli_surface, entities_by_class, _amount_ops
    )

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
        # The CLI-derived bound PLUS the specification's own bullet for this
        # repository: the spec states duties the CLI list never reaches
        # ("check if a category has exceeded its budget"), and once an
        # over-generated command that used to imply them is dropped, only the
        # spec's bullet keeps the repository design covering them.
        repo_constraint = "\n\n".join(
            x for x in (
                repo_surface_constraint(cli_surface, ent_snake) if cli_surface else "",
                repo_spec_constraint(prompt_text, ent_snake),
            ) if x
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
    # Already extracted ABOVE (the spec-enumerated CLI surface is resolved
    # against it) — never extracted twice for the same prompt text.
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
    # Spec param-name floor, applied BEFORE the CLI surface binds its options:
    # the specification declares its service signatures verbatim
    # (list_expenses(category_id, start_date, end_date, payment_method)) and
    # the design paraphrases a role (from_date/to_date). Renaming here — ahead
    # of align_surface_to_design — makes the shipped method callable exactly as
    # the specification wrote it, and lets the CLI option (--from-date) bind to
    # the spec's own parameter.
    _param_renames = apply_service_contract_params(service_contract, svc_design)
    if _param_renames and verbose:
        print("    [contract] renamed to spec param names: %s"
              % ", ".join(_param_renames))
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
        if prompt_surface is not None:
            # The specification enumerated the commands: use them verbatim. No
            # CLI design runs and nothing is merged, so no unrequested command
            # can appear and no group/option name can drift. Options are bound
            # to the DESIGNED service parameters here (the service design ran
            # above) so every rendered call passes the value the user typed.
            align_surface_to_design(prompt_surface, service_methods, entities_by_class)
            data = prompt_surface
        elif explicit_cli or cli_surface is None:
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
            data, prompt_text, entities_by_class, designs, verbose,
            preserve_surface=prompt_surface is not None,
        )
        if data is None:
            print("    [design] %s: FAILED (will generate via per-file path)" % cp, file=sys.stderr)
            cli_failed = True
            continue
        if prompt_surface is not None:
            # Reconciliation must never REMOVE a command the specification
            # wrote: a missing one is a generator defect, reported loudly
            # instead of shipping a CLI that cannot answer the spec.
            _missing = sorted(
                set(surface_command_paths(prompt_surface))
                - set(surface_command_paths(data))
            )
            for _m in _missing:
                print("    [conformity] MISSING command: %s" % _m, file=sys.stderr)
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
    # A repository whose OWN entity was never designed can only produce an
    # unresolved import (`from models import Customer` with no Customer class)
    # that aborts the whole prompt — drop it rather than ship a broken tree.
    _drop_orphan_repositories(designs, entities_by_class, manifest,
                              verbose=verbose)
    # Recompute repo_paths to include any repository file synthesized above.
    repo_paths = [s["file"] for s in manifest if s["kind"] == "repository"]

    # Service-contract coverage: every spec-declared internal method must be
    # present in the FINAL (post-reconcile/floor) service design. A missing
    # method is a real specification gap and is reported loudly — the anchor
    # that stops a spec method with no CLI command from silently vanishing.
    _svc_final = next((d for p, k, d in designs if k == "services"), None)
    # Restore the spec-declared service methods the design dropped, for the
    # two shapes the deterministic renderer bodies exactly (delete_<e>(id),
    # update_<e>(id, ...)): expenses lost update_expense/delete_expense, so
    # two spec-authorized service paths raised AttributeError. Anything else
    # stays reported below rather than shipping a NotImplementedError stub.
    _added_methods = apply_service_contract_floors(
        service_contract, _svc_final, entities_by_class
    )
    if _added_methods and verbose:
        print(
            "    [contract] restored %d spec method(s) the design omitted: %s"
            % (len(_added_methods), ", ".join(_added_methods))
        )
    for _cv in check_service_contract(service_contract, _svc_final):
        print("    [contract] VIOLATION: %s" % _cv, file=sys.stderr)

    # Deterministic floor for list_filters: cover the parameters the
    # designed service/repository signatures actually use. Declarations
    # from the models design always win (see _apply_filter_floors).
    _apply_filter_floors(entities_by_class, designs)
    # Deterministic floor for PAGINATION: a designed list_<entity> taking
    # page/page_size marks its entity so the repository's list() accepts
    # those params (and pages its SQL) and the service returns the total
    # (prompt 16: "--page/--page-size sans effet ; pas de total de pages").
    # Runs BEFORE the repositories/services are rendered — both renderers
    # read the mark off the entity.
    _apply_pagination_floors(entities_by_class, designs)
    _apply_sort_floors(entities_by_class, designs)
    _apply_report_count_floors(entities_by_class, designs, prompt_text)
    # The derived-total pass runs again now that the service design exists: it
    # strips any total parameter the design added anyway, and adds the
    # ``calculate_<entity>_total`` method that computes what is no longer an
    # input (the ``sum_children`` capability was previously unreachable).
    _apply_derived_total_floors(entities_by_class, designs, prompt_text)
    _ensure_derived_total_methods(entities_by_class, designs)
    # C1: the implicit-amount operations get their deterministic delta body —
    # the fill shipped ``withdraw_account`` as an unconditional raise.
    _ensure_amount_op_methods(entities_by_class, designs, _amount_ops)
    # Deterministic floor for service impls on unambiguous aggregate
    # shapes (Dict-returning methods over a single date+numeric entity).
    _apply_impl_floors(entities_by_class, designs)

    # Diagnostic dump: the FINAL (post-floor) designs, i.e. exactly what the
    # renderers see. Set NEUROSYM_DUMP_DESIGNS=<dir> to capture them so a
    # rendering defect can be reproduced offline from the real design instead
    # of a reconstruction. Off by default — zero effect unless set.
    _dump_dir = os.environ.get("NEUROSYM_DUMP_DESIGNS")
    if _dump_dir:
        try:
            os.makedirs(_dump_dir, exist_ok=True)
            with open(
                os.path.join(_dump_dir, "designs.json"), "w", encoding="utf-8"
            ) as _fh:
                json.dump(
                    {
                        "designs": [
                            [p, k, d] for p, k, d in designs
                        ],
                        "entities_by_class": entities_by_class,
                        "exception_names": exception_names,
                        "manifest": [
                            {"file": s.get("file"), "kind": s.get("kind"),
                             "entity": s.get("entity")}
                            for s in manifest
                        ],
                    },
                    _fh,
                    indent=1,
                )
        except OSError:
            pass

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
        # E4: the role policy travels with the same file sets as E3's
        # ownership rule, and is imposed at the same place (see run.py).
        "role_rule": _role_rule,
        # 14: the spec's soft-delete requirement, imposed on the repositories
        # by the finalize phase (see run.py).
        "soft_delete_rule": _soft_delete_rule,
        # E3: the ownership rule and the file sets it acts on, handed to the
        # finalize phase (see run.py). The rule is a SPECIFICATION requirement,
        # not part of the designed service contract, so it is imposed after the
        # finalize repairs rather than during the render.
        "ownership_rule": _ownership_rule,
        "repo_files": list(repo_paths),
        "service_files": list(svc_paths),
        "cli_files": list(cli_paths),
        "exception_files": sorted(
            {p for p, k, d in designs if k == "exceptions"}
        ),
    }

    # ---- Prompt-derived method contracts (stage 3) ----
    # Transcribed from the SPECIFICATION alone, plus the design's own method
    # signatures (which only NAME the methods to describe). The extractor
    # never sees a generated body, so a contract cannot restate the code;
    # the contract-time body verifier never sees the specification. Feeds
    # both the deterministic effect recipes and the fill-time verifier.
    _mc_sigs = [
        (
            m.get("name"),
            [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ],
        )
        for _p, _k, _d in designs
        if _k == "services" and isinstance(_d, dict)
        for m in _d.get("methods") or []
        if isinstance(m, dict) and m.get("name")
    ]
    method_contracts = (
        extract_method_contracts(prompt_text, _mc_sigs, verbose=verbose)
        if _mc_sigs else {}
    )

    # ---- Render phase (deterministic) ----
    files = {}
    svc_class = "App"
    if svc_paths:
        stem = Path(svc_paths[0]).stem
        if stem.endswith("_service"):
            stem = stem[: -len("_service")]
        svc_class = _camel(stem) + "Service"
    # The specification's money convention is two-sided — integer cents in
    # storage, decimal amounts for DISPLAY — so the project needs ONE
    # importable conversion helper. Emitted only when the specification asks
    # for the conversion AND the design actually carries a ``*_cents`` field,
    # so every other project keeps a byte-identical CLI.
    money_display = money_display_enabled(prompt_text, entities_by_class)
    # Every name that carries cents — the DESIGN's ``*_cents`` columns plus
    # the fields the SPECIFICATION marks "stored as cents" (monthly_budget).
    # One set drives all three halves of the convention: the display helper,
    # the CLI option type, and the boundary conversion.
    money_fields = (
        money_field_names(entities_by_class, prompt_text)
        if money_display else []
    )
    # Money display of a REPORT: the recipe that builds the dict declares
    # which RESULT keys hold money ("total", "per_category"). The CLI file is
    # rendered BEFORE the service bodies (this loop), so a table a recipe
    # stamps only WHILE rendering its body is invisible to the CLI renderer —
    # the report then printed raw cents. Attach the specification's
    # deterministic contract impls HERE (they are otherwise compiled while the
    # service bodies render, later) and stamp the declared table on every
    # method the CLI sees, so the report prints through the converter.
    for _p, _k, _d in designs:
        if _k == "services" and isinstance(_d, dict):
            attach_contract_impls(_d, entities_by_class, method_contracts,
                                  prompt_text)
    _report_money = {}
    for _p, _k, _d in designs:
        if _k != "services" or not isinstance(_d, dict):
            continue
        for _m in _d.get("methods") or []:
            if not isinstance(_m, dict) or not _m.get("name"):
                continue
            _impl = _m.get("impl")
            if isinstance(_impl, dict):
                _mk = declared_money_keys(_impl)
                if _mk:
                    _m["money_keys"] = _mk
                    _report_money[_m["name"]] = _mk
    # The CLI renderer reads the RECONCILED method list, which may carry
    # copies of the design dicts; stamp by NAME so the two agree.
    for _sm in service_methods or []:
        if isinstance(_sm, dict) and _sm.get("name") in _report_money:
            _sm["money_keys"] = _report_money[_sm["name"]]
    for path, kind, data in designs:
        if kind == "exceptions":
            files[path] = _render_exceptions_file(data)
        elif kind == "models":
            files[path] = _render_models_file(data)
        elif kind == "cli":
            files[path] = _render_cli_file(
                data, svc_class, entities_by_class, service_methods,
                verbose, db_path=db_file, money=money_display,
                exception_names=exception_names, money_fields=money_fields,
                spec_options=spec_option_names, enums=enum_values,
            )
    if money_display:
        files[MONEY_MODULE] = render_money_module(money_fields)

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
            spec_bullet=repo_spec_constraint(prompt_text, ent_snake),
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
            method_contracts=method_contracts,
        )
        files[sp] = body
        # 5.2b C6 — enforce the field domains the SPECIFICATION states. Injected
        # at the TOP of the entity's create/update bodies, so the rule holds
        # whichever tier produced the body (deterministic create, impl recipe or
        # LLM fill) and a re-render never doubles it.
        # The rules are keyed by the ENTITY class ("Employee"); this service is
        # named after it plus the module suffix ("EmployeeService"). Resolve the
        # entity by stripping that suffix, and hand the ENTITY to the injector —
        # the guard targets `add_employee`, not `add_employee_service`.
        _rule_cls = svc_class
        if _rule_cls not in _field_rules and _rule_cls.endswith("Service"):
            _rule_cls = _rule_cls[: -len("Service")]
        _rules_for_class = _field_rules.get(_rule_cls)
        if _rules_for_class:
            files[sp] = apply_field_guards(
                body, _rule_cls, _rules_for_class, exception_names
            )
        # 5.2c C2 — refuse the state TRANSITIONS the SPECIFICATION forbids. The
        # guard is spliced AFTER the row is loaded (it reads the current state)
        # and before the first write, and chained from the file as it stands so
        # it cannot discard an earlier injection for the same service.
        _state_for_class = _state_rules.get(_rule_cls)
        if _state_for_class:
            files[sp] = apply_state_guards(
                files[sp], _rule_cls, _state_for_class, exception_names
            )
        # (#3) adopt bounded repository repairs made while filling this
        # service: the shipped repository file and the service contract
        # must stay consistent (the fill legally calls what was added).
        for p in repo_paths:
            if repo_srcs.get(p) != files.get(p):
                files[p] = repo_srcs[p]
        # (#4) A repository custom the shipped service never calls, and the
        # repository's own specification bullet never names, is unreachable
        # duplicate machinery: drop it from the shipped file and the design.
        _prune_uncalled_repo_customs(
            repo_paths, designs, files, body, prompt_text
        )
        # 5.2d C3 — enforce the OVERLAP rule the SPECIFICATION states. Placed
        # AFTER the repository adoption above so the added existence test is
        # not overwritten by the adopted (pre-edit) repository source.
        _overlap_rule = _overlap_rules.get(_rule_cls)
        if _overlap_rule:
            _item_snake = _snake(_rule_cls)
            _repo_path = next(
                (p for p in repo_paths
                 if Path(p).stem == "%s_repository" % _item_snake),
                None,
            )
            if _repo_path:
                files[_repo_path], files[sp] = apply_overlap_guard(
                    files.get(_repo_path) or "", files[sp],
                    _rule_cls, _overlap_rule, exception_names,
                )
        # 5.2e C4 — a resource carries at most ONE active row ("a book can have
        # at most one active loan", prompt 26). Same placement and same
        # repository+service edit as C3, chained from the file as it stands.
        _active_rule = _active_rules.get(_rule_cls)
        if _active_rule:
            _item_snake = _snake(_rule_cls)
            _repo_path = next(
                (p for p in repo_paths
                 if Path(p).stem == "%s_repository" % _item_snake),
                None,
            )
            if _repo_path:
                files[_repo_path], files[sp] = apply_active_guard(
                    files.get(_repo_path) or "", files[sp],
                    _rule_cls, _active_rule, exception_names,
                )
        # 5.2f C5 — refuse to DELETE a row the specification says is still
        # referenced ("a category cannot be deleted while products still
        # belong to it", prompt 36). The check sits on the RESOURCE repository
        # but queries the ITEM table, whose name is read back from the ITEM
        # repository's own FROM clause.
        _ref_rule = _reference_rules.get(_rule_cls)
        if _ref_rule:
            _res_snake = _snake(_rule_cls)
            _item_snake = _ref_rule["item"]
            _res_repo = next(
                (p for p in repo_paths
                 if Path(p).stem == "%s_repository" % _res_snake),
                None,
            )
            _item_repo = next(
                (p for p in repo_paths
                 if Path(p).stem == "%s_repository" % _item_snake),
                None,
            )
            _item_table = (
                _table_from_source(files.get(_item_repo) or "")
                if _item_repo else None
            )
            if _res_repo and _item_table:
                files[_res_repo], files[sp] = apply_reference_guard(
                    files.get(_res_repo) or "", files[sp],
                    _rule_cls, _ref_rule, _item_table, exception_names,
                )
        # 5.2h E1 — the AUDIT TRAIL ("every creation, update and deletion must
        # also produce an audit record", prompt 33). Chained from the file as
        # it stands, after every other service edit.
        _audit_rule = _audit_rules.get(_rule_cls)
        if _audit_rule:
            files[sp] = apply_audit_guards(files[sp], _rule_cls, _audit_rule)

    # 5.2g C5 (cross-service) — the referential DELETE guard can live in a
    # service that is NOT the resource's own: prompt 36 hosts
    # ``delete_category`` on ProductService, the only service the design
    # created, so a guard keyed to ``category_service.py`` never ran. The
    # repository check is added once (on the RESOURCE repository), and the
    # guard is injected into EVERY service that actually carries the delete
    # method — found by name, not by file.
    for _ref_cls, _ref_rule in (_reference_rules or {}).items():
        _res_snake = _snake(_ref_cls)
        _item_snake = _ref_rule["item"]
        _res_repo = next(
            (p for p in repo_paths
             if Path(p).stem == "%s_repository" % _res_snake),
            None,
        )
        _item_repo = next(
            (p for p in repo_paths
             if Path(p).stem == "%s_repository" % _item_snake),
            None,
        )
        _item_table = (
            _table_from_source(files.get(_item_repo) or "")
            if _item_repo else None
        )
        if not (_res_repo and _item_table):
            continue
        for _sp in svc_paths:
            _src = files.get(_sp) or ""
            if ("delete_%s" % _res_snake) not in _src and \
                    ("remove_%s" % _res_snake) not in _src:
                continue
            files[_res_repo], files[_sp] = apply_reference_guard(
                files.get(_res_repo) or "", _src, _ref_cls, _ref_rule,
                _item_table, exception_names,
            )

    # 5.2i E2 — the NOTIFICATION requirement ("when an order is confirmed …
    # send a notification", prompt 40). Two pieces: emit the abstraction
    # module the specification asks for, and splice the call into whichever
    # service actually carries the trigger method (found by name, not by the
    # file the design happened to name).
    if _notify_rules:
        files["%s.py" % NOTIFICATIONS_MODULE] = render_notifications_module()
        for _nrule in _notify_rules.values():
            for _sp in svc_paths:
                _src = files.get(_sp) or ""
                if _nrule["method"] not in _src:
                    continue
                files[_sp] = apply_notify_guards(_src, _nrule)
                break

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

    # NOTE (E3): the OWNERSHIP rule ("a user can only read, modify or delete
    # their own documents", prompt 38) is NOT applied here. It has to precede
    # nothing and follow everything: ``_restore_service_signatures`` (see
    # run.py) re-imposes the DESIGNED signature of every service method, and the
    # acting user is no part of that design, so a parameter added during the
    # render phase is stripped from the ``def`` while its guarded body stays —
    # every call to ``list_document``/``delete_document`` then raises
    # ``NameError: user_id``. The rule therefore travels in ``design_ctx`` and is
    # imposed at the end of the finalize phase, on what is actually shipped.

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

    # A CLI project ALWAYS gets a runnable entry point, whether or not the
    # manifest happened to declare one. The loop above renders a main.py only
    # for a spec the LLM layout listed — so library_system shipped with NO
    # entry point while expenses (the same shape: a click CLI) got one, purely
    # because the layout named the module in one project and not the other.
    # `python main.py library book list` is how a user runs the deliverable;
    # that cannot depend on an LLM listing a file. Emitted unconditionally
    # here, for a tree that has a CLI and no entry point of its own.
    if "cli.py" in files and not any(
        Path(f).stem in ("main", "app") for f in files
    ):
        files["main.py"] = _render_main_file(files, db_file)
        if verbose:
            print("    [render] added main.py entry point (layout omitted it)")

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
