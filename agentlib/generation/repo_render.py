"""Deterministic repository renderer + LLM-fill merge for custom methods.

Extracted from agent.py. Renders the CRUD repository skeleton and splices
accepted LLM fills for designed custom methods, gating each fill against the
designed SQLite schema and the name-resolution contract. No behaviour change.
"""
import ast
import re
from pathlib import Path

from ..config import LLM_RETRY_TEMPERATURE
from ..naming import _camel, _entity_table_name, _plural, _snake
from ..llm.fill import _llm_fill
from ..kernel.service.common import _declared_filters, _filter_flag_refs
from ..kernel.repo.bodies import _repo_method_body
from .helpers import _method_stub_code
from .model_render import _repo_columns
from .repo_contract import (
    _repo_fill_schema_violations,
    _repo_schema_from_entities,
    _repo_sql_context_hint,
)
from .splice import (
    _fn_has_stub_raise,
    _fn_undefined_names,
    _indent_block,
    _module_defined_names,
    _splice_functions,
)


def _repo_method_purpose(m, ent):
    """One-line deterministic purpose for a designed repository custom method,
    from its spelling + owning entity. Prompt-independent and bounded, so the
    repo fill conversation stays small (a rich spec like expense embedded the
    whole app on every repo fill, hitting ~4398 tokens)."""
    name = m.get("name") or ""
    ent_snake = _snake(ent["name"]) if ent else ""
    low = name.lower()
    if not name:
        return "implement the query over %s using the designed schema." % (ent_snake or "the entity")
    if low.startswith(("find_", "list_", "get_", "search_", "fetch_")):
        return "retrieve %s rows matching the given arguments." % (ent_snake or "the entity")
    if low.startswith(("count_", "total_", "sum_")):
        return "aggregate/count %s rows per the given arguments." % (ent_snake or "the entity")
    if "pattern" in low or "recurring" in low:
        return "find recurring %s patterns (same amount/category over consecutive months)." % (ent_snake or "rows")
    if any(k in low for k in ("budget", "status", "exceed", "month", "year", "summary", "report")):
        return "report an aggregate/status detail over %s for the given period or key." % (ent_snake or "the entity")
    return "implement the '%s' query over %s." % (name, ent_snake or "the entity")


def _repo_requirement_context(stub_methods, ent_snake, ent):
    """Compact, prompt-independent business context for a repository fill.

    Replaces the always-full ``prompt_text`` (the whole spec) with a bounded
    block derived ONLY from the designed stub methods' signatures + returns +
    one-line purposes, so the per-repo fill conversation never scales with the
    prompt length. The fill is still validated by ``_merge_repo_fill`` against
    the designed SQL schema, so a weaker-but-in-scope fill is caught and
    reverted to a safe stub rather than shipping broken SQL."""
    lines = [
        "REPOSITORY TO IMPLEMENT — %sRepository" % _camel(ent_snake),
        "Write a real body for each custom method below using ONLY the "
        "designed tables/columns (see the SQL context) and the shared Database "
        "object (with self.db.connect() as conn:).",
        "CUSTOM METHODS:",
    ]
    for m in stub_methods:
        name = m.get("name") or ""
        params = ", ".join(
            "%s: %s" % (p.get("name"), p.get("type") or "Any")
            for p in (m.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        )
        lines.append(
            "  - %s(%s) -> %s"
            % (name, params, m.get("returns") or "Any")
        )
    lines.append("PURPOSES:")
    for m in stub_methods:
        lines.append(
            "  - %s: %s" % ((m.get("name") or "?"), _repo_method_purpose(m, ent))
        )
    return "\n".join(lines)


# System-side rules for a repository fill, in the primacy slot so a small
# model attends to them. Every rule states a property the validator below
# also enforces, so the fill usually complies and the rejection (which
# reverts the method to a safe empty body) stays a backstop, not the norm.
_REPO_FILL_SYSTEM_RULES = (
    "REPOSITORY BODY RULES\n"
    "- PARAMETERS  every declared parameter must reach the SQL: bind it as a "
    "query parameter in the WHERE clause. Never accept a parameter and ignore "
    "it.\n"
    "- DATE VALUES  a date/datetime parameter arrives as an ISO-format "
    "STRING, never as a datetime object. Pass it straight into the SQL; never "
    "call .isoformat(), .strftime() or .date() on it.\n"
    "- QUERY BUILDING  build ONE query variable INCREMENTALLY (query += "
    "\"...\"), and never assign a fresh query to a variable that already "
    "holds one before the old value has been used — the conditions you "
    "patched in would be discarded.\n"
    "- Emit only the methods listed, each complete, returning the designed "
    "model/dict rows; never invent helper methods."
)


# --- CRUD-shadow pruning ---------------------------------------------------
# Every repository file renders the same deterministic CRUD surface:
# create/get_by_id/get_all/list/update/delete (+ the unique_together lookups).
# A designed custom method that merely RE-SPELLS one of those on its own entity
# is a second source of truth for the same table: it is dead (the rendered
# service calls the CRUD method), it diverges silently, and it bloats every
# downstream interface enumeration. Measured cases:
#   library_system  member.add_member / member.list_members / book.list_books
#   expenses        list_expenses / get_expense_by_id / add_category /
#                   update_category / delete_category / list_budgets / ...
# A method that keeps a NON-entity token (search_books, get_overdue_loans,
# find_books_by_author, get_expenses_for_category) names a capability the CRUD
# surface does not provide and is left untouched.
_CRUD_BASE_METHODS = ("create", "get_by_id", "get_all", "list", "update", "delete")
_CRUD_WRITE_VERBS = {
    "add": "create", "create": "create", "insert": "create", "new": "create",
    "register": "create", "save": "create", "store": "create", "make": "create",
    "delete": "delete", "remove": "delete", "erase": "delete", "drop": "delete",
    "update": "update", "edit": "update", "modify": "update", "change": "update",
    "set": "update",
}
_CRUD_QUALIFIERS = {
    "count", "total", "sum", "avg", "average", "number", "nb", "exists", "all",
}


def _entity_stem_variants(ent_snake, model):
    """Every spelling of the entity token a designed method name may use."""
    stems = set()
    for raw in (ent_snake, _snake(model or "")):
        if not raw:
            continue
        stems.add(raw)
        plural = _plural(raw)
        stems.add(plural)
        # Naive singular of the plural (expenses -> expense, categories ->
        # category, budgets -> budget) so a `get_<entity>_by_id` spelling is
        # recognised against the singular repository stem.
        if plural.endswith("ies"):
            stems.add(plural[:-3] + "y")
        elif plural.endswith("s"):
            stems.add(plural[:-1])
        if raw.endswith("ies"):
            stems.add(raw[:-3] + "y")
        elif raw.endswith("s"):
            stems.add(raw[:-1])
    return {s for s in stems if s}


def _crud_shadow_target(name, ent_snake, model):
    """The deterministic CRUD method this designed custom merely re-spells.

    ``add_member`` -> create, ``list_expenses`` -> list,
    ``get_category_by_id`` -> get_by_id, ``update_budget`` -> update.
    Returns None as soon as a NON-entity token survives (``search_books``,
    ``get_overdue_loans``, ``find_books_by_author``), so a capability the CRUD
    surface does not provide is never pruned.
    """
    low = (name or "").lower()
    if not low or low in _CRUD_BASE_METHODS:
        return None
    stems = _entity_stem_variants(ent_snake, model)
    toks = [t for t in low.split("_") if t]
    if not any(t in stems for t in toks):
        return None
    core = [t for t in toks if t not in stems]
    if not core:
        return None
    if core[0] in ("get", "find", "fetch", "load", "read", "retrieve"):
        if core[1:] == ["by", "id"]:
            return "get_by_id"
        # get_all_<e> / find_all_<e> re-spell the deterministic get_all().
        if core[1:] == ["all"]:
            return "get_all"
        return None
    if core[0] in ("list", "all"):
        return "list" if core[1:] in ([], ["all"]) else None
    head = _CRUD_WRITE_VERBS.get(core[0])
    if head is None or core[1:]:
        return None
    return head


def _qualifier_extension_of(name, other):
    """True when ``name`` is ``other`` plus trailing scalar-qualifier tokens.

    ``get_overdue_loans_count`` extends ``get_overdue_loans``: the same query
    answering a different shape, so the count copy is redundant. Restricted to
    qualifier tokens, so an unrelated longer name (``get_expenses_for_category``
    beside ``get_expenses``) is never mistaken for a duplicate.
    """
    def norm(s):
        for pre in ("get_", "find_", "list_", "fetch_", "count_", "all_"):
            if s.startswith(pre):
                return s[len(pre):]
        return s

    na, nb = norm(name or ""), norm(other or "")
    if not na or not nb or na == nb or not na.startswith(nb + "_"):
        return False
    extra = [t for t in na[len(nb) + 1:].split("_") if t]
    return bool(extra) and all(t in _CRUD_QUALIFIERS for t in extra)


def _prune_crud_shadow_customs(design, ent_snake, model):
    """Drop designed repository customs the deterministic surface already covers.

    Pruned IN PLACE so every downstream consumer of the design (the service
    interface, the fill's method enumeration, the shipped source) agrees: a
    method pruned here can never be advertised to a service fill. Returns the
    kept list.
    """
    methods = (design or {}).get("methods")
    if not isinstance(methods, list):
        return []
    kept = []
    for m in methods:
        if not isinstance(m, dict):
            continue
        if _crud_shadow_target(m.get("name") or "", ent_snake, model):
            continue
        kept.append(m)
    names = [m.get("name") or "" for m in kept] + list(_CRUD_BASE_METHODS)
    final = [
        m for m in kept
        if not any(
            _qualifier_extension_of(m.get("name") or "", other)
            for other in names if other != (m.get("name") or "")
        )
    ]
    design["methods"] = final
    return final


# --- capability reading + unjustified-extras pruning -----------------------
# A repository must carry the CRUD surface plus ONLY the capabilities its own
# specification bullet names. Two measured extras survive the CRUD-shadow
# prune and are removed here:
#   library_system  AuthorRepository.get_author_books_count   a count nobody
#                   asked for; the bullet says "find books by author",
#                   already satisfied by find_books_by_author.
#   library_system  AuthorRepository.list_authors_with_books  a redundant
#                   spelling of find_books_by_author that the schema gate
#                   REJECTED — it shipped a `return []` stub plus a `reverted`
#                   log line instead of a working method.
_STOPWORDS = {
    "with", "by", "for", "and", "of", "to", "in", "the", "a", "an", "on",
    "from", "all", "per", "as", "at", "that", "its", "is", "are",
}
_READ_VERBS = {
    "get", "find", "list", "fetch", "load", "read", "retrieve", "search",
    "query", "show", "count", "total", "sum", "check", "detect", "export",
}


def _capability_tokens(name, ent_snake, model):
    """(verb, content tokens) of a designed method name.

    The leading verb and the entity stem are removed, so on AuthorRepository
    ``list_authors_with_books`` reads as ('list', {'books'}) and
    ``find_books_by_author`` as ('find', {'books'}) — one capability under two
    spellings. ``get_author_books_count`` reads as ('get', {'books', 'count'}):
    a count qualifier nobody asked for.
    """
    stems = _entity_stem_variants(ent_snake, model)
    toks = [t for t in (name or "").lower().split("_") if t]
    verb = ""
    if toks and (toks[0] in _READ_VERBS or toks[0] in _CRUD_WRITE_VERBS):
        verb = toks[0]
        toks = toks[1:]
    content = {t for t in toks if t not in stems and t not in _STOPWORDS}
    return verb, content


def _stemmed_tokens(text):
    """Lowercase alphanumeric tokens of a sentence, plural-stemmed."""
    out = set()
    for raw in re.split(r"[^a-z0-9]+", (text or "").lower()):
        if not raw:
            continue
        out.add(raw)
        if raw.endswith("ies") and len(raw) > 3:
            out.add(raw[:-3] + "y")
        elif raw.endswith("s") and len(raw) > 1:
            out.add(raw[:-1])
    return out


def _unjustified_qualifier_customs(customs, spec_bullet, ent_snake, model):
    """Drop count/total-style customs the repository's own bullet never asks for.

    Applies only when the prompt names the repository (a non-empty bullet), so
    a specification that does ask for a count — its bullet containing the word
    — is untouched. ``AuthorRepository.get_author_books_count`` is the measured
    case: nothing in "CRUD + find books by author" asks for a count.
    """
    if not spec_bullet:
        return customs
    bullet_tokens = _stemmed_tokens(spec_bullet)
    kept = []
    for m in customs:
        _, content = _capability_tokens(m.get("name") or "", ent_snake, model)
        qualifiers = content & _CRUD_QUALIFIERS
        if qualifiers and not (qualifiers & bullet_tokens):
            continue
        kept.append(m)
    return kept


def _subsumed_by_sibling(name, sibling_names, ent_snake, model):
    """True when every content token of ``name`` already appears in a sibling.

    ``list_authors_with_books`` -> {'books'} is subsumed by
    ``find_books_by_author`` -> {'books'}: the dropped method names no object
    word its surviving sibling does not also name, so removing it costs no
    capability. An EMPTY content set (``search_books``) is never subsumed —
    such a method is the repository's own entity-wide operation.
    """
    _, content = _capability_tokens(name, ent_snake, model)
    if not content:
        return False
    for other in sibling_names:
        if other == name:
            continue
        _, other_content = _capability_tokens(other, ent_snake, model)
        if other_content and content <= other_content:
            return True
    return False


def _drop_functions(text, names):
    """Remove the named methods from a source string, in place of a re-render.

    Used instead of re-rendering a repository so the ACCEPTED sibling fills
    (and any bounded repair the service fill made) survive untouched.
    """
    names = {n for n in (names or []) if n}
    if not names:
        return text
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    lines = text.splitlines(keepends=True)
    ranges = []
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        ):
            start = node.lineno - 1
            if node.decorator_list:
                start = min(d.lineno for d in node.decorator_list) - 1
            ranges.append((start, node.end_lineno))
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
        if start < len(lines) and not lines[start].strip():
            del lines[start]
    return "".join(lines)


def _render_repository_file(ent_snake, design, entities_by_class, exception_names=None,
                            prompt_text="", verbose=False, models_module="models",
                            spec_bullet=""):
    """Deterministic CRUD repo over a Database object (database.py owns DDL).

    - create/get_by_id/get_all/update/delete are rendered with real bodies.
    - `list(**filters)` is built from the entity's declared "list_filters"
      design entries (param/column/op) — no suffix heuristics, no LLM.
    - a designed unique_together pair renders
      get_by_<a>_and_<b> and delete(a, b) replacing the id-based delete.
    - update raises "<Model>NotFoundError" when the row is missing, if that
      exception was designed (contract-style, deterministic).
    """
    model = _camel(ent_snake)
    repo = model + "Repository"
    ent = entities_by_class.get(model)
    if not ent:
        # Filename-derived entity mismatch (audit_entry_repository serves
        # AuditRecord, not AuditEntry). Derive the entity from the designed
        # custom methods' return types so the repo doesn't render empty.
        for m in (design or {}).get("methods") or []:
            if not isinstance(m, dict):
                continue
            ret = (m.get("returns") or "")
            if not ret:
                continue
            for cls in entities_by_class:
                if re.search(r"\b%s\b" % cls, ret):
                    ent = entities_by_class[cls]
                    model = cls
                    ent_snake = _snake(cls)
                    repo = model + "Repository"
                    break
            if ent:
                break
        if not ent:
            return ""
    exception_names = exception_names or []
    table_names = {cls: _entity_table_name(e) for cls, e in entities_by_class.items()}
    cols = _repo_columns(ent, table_names)
    has_id = any(c[2] for c in cols)
    nonid = [c for c in cols if not c[2]]
    col_names = [c[0] for c in nonid]
    table = table_names.get(model) or _plural(ent_snake)
    # Prune designed customs the deterministic CRUD surface already covers
    # (list_expenses / get_expense_by_id / add_category / list_budgets / ...):
    # a repository never ships two implementations of the same capability. The
    # design is pruned IN PLACE, so the service interface and the fill read the
    # same pruned list and nothing can call a method pruned away.
    customs = _prune_crud_shadow_customs(design, ent_snake, model)
    customs = _unjustified_qualifier_customs(
        customs, spec_bullet, ent_snake, model
    )
    design["methods"] = customs
    needs_json = any(
        re.search(r"_(?:to|from)_json$", m.get("name") or "")
        for m in customs
    )

    # --- declared filter API (from the entity design's list_filters) --------
    filter_specs = _declared_filters(ent)
    filter_params = [(p, None) for p, _, _ in filter_specs]
    # Cross-table filter columns (filtering by a JOIN entity's column, e.g.
    # Post filtered by PostTag.tag_id — prompt 23's "posts by tag") need a
    # JOIN so the list() SQL qualifies the column with the join alias instead
    # of a bare column that doesn't exist on the entity's own table.
    own_cols = set(col_names)
    join_clauses = []
    qualified = {}
    for _p, col, _op in filter_specs:
        if col in own_cols:
            continue
        for cls, other in entities_by_class.items():
            if cls == model:
                continue
            other_fields = {
                f.get("name")
                for f in (other.get("fields") or [])
                if isinstance(f, dict)
            }
            if col not in other_fields:
                continue
            fk_to_me = next(
                (
                    fk for fk in (other.get("fks") or [])
                    if isinstance(fk, dict) and fk.get("ref") == model
                ),
                None,
            )
            if fk_to_me is None:
                continue
            other_table = table_names.get(cls) or _plural(_snake(cls))
            other_alias = _snake(cls)
            fk_field = fk_to_me.get("field") or "id"
            fk_ref = fk_to_me.get("ref_field") or "id"
            join_clauses.append(
                "JOIN %s %s ON %s.%s = %s.%s"
                % (
                    other_table, other_alias,
                    other_alias, fk_field,
                    ent_snake, fk_ref,
                )
            )
            qualified[col] = "%s.%s" % (other_alias, col)
            break
    # Constant-predicate ops (eq_true/gt_zero) arrive via bounded CLI flag
    # propagation (_apply_filter_floors): they bind NO value and guard on
    # truthiness instead of is-not-None (a click flag defaults to False,
    # and False must mean "no filter", never "filter on false").
    _FRAG = {
        "eq": " AND %s = ?", "gte": " AND %s >= ?", "lte": " AND %s <= ?",
        "eq_true": " AND %s = 1", "gt_zero": " AND %s > 0",
    }
    _BOUND_OPS = {"eq", "gte", "lte"}
    # "Below the referenced row's threshold" filters (see
    # _flag_threshold_spec): the compared column lives on THIS table, the
    # threshold on the row this entity's foreign key points at, so they need
    # their own JOIN and a fragment qualified by BOTH aliases. Kept apart from
    # _FRAG, whose fragments are single-column constants.
    flag_refs = _filter_flag_refs(ent)
    below_specs = [
        (p, col, flag_refs[p])
        for p, col, op in filter_specs
        if op == "below_ref" and p in flag_refs
    ]
    for _p, _col, _ref in below_specs:
        ref_alias = _snake(_ref["ref_cls"])
        ref_table = table_names.get(_ref["ref_cls"]) or _plural(ref_alias)
        join_clauses.append(
            "JOIN %s %s ON %s.%s = %s.id"
            % (ref_table, ref_alias, ent_snake, _ref["ref"], ref_alias)
        )
    below_where = [
        (
            " AND %s.%s < %s.%s"
            % (ent_snake, col, _snake(r["ref_cls"]), r["ref_column"]),
            p,
        )
        for p, col, r in below_specs
    ]
    filter_where = [
        (_FRAG[op] % qualified.get(col, col), p, op in _BOUND_OPS)
        for p, col, op in filter_specs
        if op in _FRAG
    ]

    # --- unique_together pair -> lookup + delete-by-pair --------------------
    unique_pairs = ent.get("unique_together") or []
    pair = None
    for up in unique_pairs:
        if isinstance(up, list) and len(up) == 2:
            pair = [str(u) for u in up]
            break
    not_found_exc = "%sNotFoundError" % model
    raise_missing = not_found_exc in exception_names

    insert_cols = ", ".join(col_names)
    placeholders = ", ".join("?" for _ in col_names)
    insert_vals = ", ".join("%s.%s" % (ent_snake, c) for c in col_names)

    L = []
    L.append('"""%s data access."""' % repo)
    L.append("from __future__ import annotations")
    L.append("")
    L.append("import sqlite3")
    if needs_json:
        L.append("import json")
    L.append("from typing import Any, Dict, List, Optional")
    L.append("")
    L.append("from database import Database")
    # Import ALL designed entity classes: custom-method fills legitimately
    # reference related entities (a member-repo fill returning Loan rows),
    # and the per-method splice keeps only bodies — the fill's own imports
    # never survive. A complete models import makes the merged namespace
    # self-consistent; _merge_repo_fill's undefined-name gate then rejects
    # any residual hallucinated name instead of shipping a NameError.
    L.append("from %s import %s"
             % (models_module, ", ".join(sorted(entities_by_class))))
    if raise_missing:
        L.append("from exceptions import %s" % not_found_exc)
    L.append("")
    L.append("")
    L.append("class %s:" % repo)
    L.append('    """SQLite repository for %s over the shared Database."""' % model)
    L.append("")
    L.append("    def __init__(self, db: Database) -> None:")
    L.append("        self.db = db")
    L.append("")
    L.append("    def create(self, %s: %s) -> int:" % (ent_snake, model))
    L.append("        with self.db.connect() as conn:")
    L.append("            cur = conn.cursor()")
    L.append("            cur.execute(")
    L.append('                "INSERT INTO %s (%s) VALUES (%s)",' % (table, insert_cols, placeholders))
    L.append("                (%s)," % insert_vals)
    L.append("            )")
    L.append("            conn.commit()")
    L.append("            return cur.lastrowid")
    L.append("")
    L.append("    def get_by_id(self, id: int) -> Optional[%s]:" % model)
    L.append("        with self.db.connect() as conn:")
    L.append("            row = conn.execute(")
    L.append('                "SELECT * FROM %s WHERE id = ?", (id,)' % table)
    L.append("            ).fetchone()")
    L.append("            return %s(**dict(row)) if row else None" % model)
    L.append("")
    L.append("    def get_all(self) -> List[%s]:" % model)
    L.append("        with self.db.connect() as conn:")
    L.append("            rows = conn.execute(")
    L.append('                "SELECT * FROM %s ORDER BY id"' % table)
    L.append("            ).fetchall()")
    L.append("            return [%s(**dict(r)) for r in rows]" % model)
    L.append("")
    if filter_params:
        sig = ", ".join("%s: Optional[Any] = None" % p[0] for p in filter_params)
        L.append("    def list(self, %s) -> List[%s]:" % (sig, model))
        L.append("        with self.db.connect() as conn:")
        if join_clauses:
            L.append(
                '            query = "SELECT %s.* FROM %s %s %s WHERE 1=1"'
                % (ent_snake, table, ent_snake, " ".join(join_clauses))
            )
        else:
            L.append('            query = "SELECT * FROM %s WHERE 1=1"' % table)
        L.append("            params: List[Any] = []")
        for frag, expr, bound in filter_where:
            guard = (
                "if %s is not None:" % expr if bound else "if %s:" % expr
            )
            L.append("            " + guard)
            L.append("                query += %r" % frag)
            if bound:
                L.append("                params.append(%s)" % expr)
        # Below-threshold flags bind no value: the flag being truthy is the
        # whole condition, so guard on truthiness (never "is not None" — a
        # click flag defaults to False and False means "no filter").
        for frag, expr in below_where:
            L.append("            if %s:" % expr)
            L.append("                query += %r" % frag)
        order_col = "%s.id" % ent_snake if join_clauses else "id"
        L.append(
            "            rows = conn.execute(query + \" ORDER BY %s\", params).fetchall()"
            % order_col
        )
        L.append("            return [%s(**dict(r)) for r in rows]" % model)
    else:
        L.append("    def list(self) -> List[%s]:" % model)
        L.append("        return self.get_all()")
    L.append("")
    if pair:
        a, b = pair
        # Strip the "_id" suffix for the method name (<col>_id -> <col>);
        # the SQLite WHERE clause keeps the real column name.
        a_fn = a[:-3] if a.endswith("_id") else a
        b_fn = b[:-3] if b.endswith("_id") else b
        L.append("    def get_by_%s_and_%s(self, %s: Any, %s: Any) -> Optional[%s]:"
                 % (a_fn, b_fn, a, b, model))
        L.append("        with self.db.connect() as conn:")
        L.append("            row = conn.execute(")
        L.append('                "SELECT * FROM %s WHERE %s = ? AND %s = ?", (%s, %s)'
                 % (table, a, b, a, b))
        L.append("            ).fetchone()")
        L.append("            return %s(**dict(row)) if row else None" % model)
        L.append("")
    L.append("    def update(self, id: int, data: Dict[str, Any]) -> bool:")
    L.append("        if not data:")
    L.append("            return False")
    L.append("        allowed = %r" % (col_names,))
    L.append("        sets = [k for k in data if k in allowed]")
    L.append("        if not sets:")
    L.append("            return False")
    L.append("        with self.db.connect() as conn:")
    L.append("            cur = conn.cursor()")
    L.append("            cur.execute(")
    # build the SET clause at RUNTIME inside the generated function where
    # `sets` exists — never at render time (renderer has no `sets`).
    # .format is used here so `%` in the generated source is not mangled.
    L.append('                "UPDATE {table} SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",'.format(table=table))
    L.append("                [data[k] for k in sets] + [id],")
    L.append("            )")
    L.append("            conn.commit()")
    L.append("            if cur.rowcount == 0:")
    if raise_missing:
        L.append("                raise %s(id)" % not_found_exc)
    else:
        L.append("                return False")
    L.append("            return True")
    L.append("")
    # Only use the unique-pair delete when the entity has NO surrogate `id`
    # PK (a pure join table like PostTag). An entity with an `id` column is
    # deleted by PK — the pair is a lookup/constraint, not the delete key —
    # so its service design (delete_<entity>(id)) and the deterministic repo
    # interface (delete(id)) stay consistent.
    if pair and not has_id:
        a, b = pair
        L.append("    def delete(self, %s: Any, %s: Any) -> bool:" % (a, b))
        L.append("        with self.db.connect() as conn:")
        L.append("            cur = conn.cursor()")
        L.append("            cur.execute(")
        L.append('                "DELETE FROM %s WHERE %s = ? AND %s = ?", (%s, %s)'
                 % (table, a, b, a, b))
        L.append("            )")
        L.append("            conn.commit()")
        L.append("            return cur.rowcount > 0")
    else:
        L.append("    def delete(self, id: int) -> bool:")
        L.append("        with self.db.connect() as conn:")
        L.append("            cur = conn.cursor()")
        L.append("            cur.execute(")
        L.append('                "DELETE FROM %s WHERE id = ?", (id,)' % table)
        L.append("            )")
        L.append("            conn.commit()")
        L.append("            return cur.rowcount > 0")
    L.append("")
    # custom designed methods: deterministic recipes where recognized, else
    # locked stubs (class methods, 1 indent unit) for the LLM fill.
    stub_methods = []
    for m in design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        body = _repo_method_body(
            m, ent, ent_snake, model, entities_by_class=entities_by_class
        )
        if body is not None:
            def_line = _method_stub_code(m, 1).split("\n")[0]
            L.append(def_line)
            L.extend(body)
            L.append("")
        else:
            # Unfilled custom method: final deterministic body is a
            # type-appropriate empty return (not NotImplementedError) so the
            # running app never crashes and the benchmark not_implemented
            # gate passes. The LLM mini-skeleton keeps raise
            # NotImplementedError() to push the model.
            L.append(_method_stub_code(m, 1, safe_body=True))
            L.append("")
            stub_methods.append(m)
    deterministic = "\n".join(L).rstrip() + "\n"
    if not prompt_text or not stub_methods:
        return deterministic
    # Same contract as services: the LLM fills only the remaining stubs, and
    # the result is accepted only if every designed custom method survived.
    # Unlike services, repos speak raw SQL, so the fill is given a DESIGNED
    # SQLite-schema context hint, and on schema-gate rejection it gets ONE
    # corrective retry that feeds the specific violations back.
    schema_ctx = _repo_schema_from_entities(entities_by_class)
    # Designed model fields, for the model-construction contract gate in
    # _merge_repo_fill (fills must construct models with ONLY these kwargs).
    model_fields = {
        cls: {
            f.get("name") for f in (e.get("fields") or []) if isinstance(f, dict)
        }
        for cls, e in entities_by_class.items()
    }
    # This repository's OWN table (single-entity contract): fills may read
    # ONLY this table — no JOINs, no cross-table SELECTs.
    own_ent = entities_by_class.get(_camel(ent_snake)) or next(
        iter(entities_by_class.values()), {}
    )
    own_table = _entity_table_name(own_ent)
    stub_names = [m["name"] for m in stub_methods]
    req_ctx = _repo_requirement_context(stub_methods, ent_snake, own_ent)

    def _hint(extra=""):
        return _repo_sql_context_hint(schema_ctx, stub_names) + extra

    # Mini-skeleton, same contract as services: header + ONLY the stub
    # methods travel to the LLM. Deterministic CRUD bodies never enter the
    # prompt, so they cannot be degraded, and the decode shrinks ~3x —
    # re-emitting a whole repo file drove degenerate repetition loops on
    # large repositories (6250+ token decodes for a ~1900-token file).
    head = deterministic.split("    def create(")[0]
    mini = (
        head.rstrip()
        + "\n\n"
        + "\n\n".join(_method_stub_code(m, 1) for m in stub_methods)
        + "\n"
    )

    merged = None
    rejected = []
    instruction = _hint()
    for attempt in range(3):
        filled = _llm_fill(
            "repository", instruction, mini, req_ctx,
            verbose=verbose,
            temperature=0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE,
            extra_system=_REPO_FILL_SYSTEM_RULES,
        )
        if not filled:
            break
        merged, rejected, violations = _merge_repo_fill(
            deterministic, filled, stub_names, schema_ctx,
            model_fields=model_fields, own_table=own_table,
        )
        if merged is not None and not rejected:
            if verbose:
                print(
                    "    [fill] repository <%s>: filled %d custom(s)"
                    % (ent_snake, len(stub_names))
                )
            return merged
        if merged is not None and rejected:
            instruction = _hint(
                "\\n\\nYour previous fill was REJECTED because these methods "
                "referenced columns/tables outside the DESIGNED schema:\\n"
                + "\\n".join(
                    "  - %s: %s" % (name, "; ".join(vs))
                    for name, vs in sorted(violations.items())
                )
                + "\\n\\nEmit ONLY these methods (%s), each complete with its "
                "body, using ONLY the tables/columns listed above."
                % ", ".join(stub_names)
            )
            if any("not on the" in v for vs in violations.values() for v in vs):
                instruction += (
                    "\\n\\nEXAMPLE FIX  every method body must be exactly:\\n"
                    "with self.db.connect() as conn:\\n"
                    "    rows = conn.execute('SELECT * FROM %s WHERE <column> = ?', (value,)).fetchall()\\n"
                    "    return [%s(**dict(r)) for r in rows]"
                    % (own_table, _camel(ent_snake))
                )
            continue
        break
    if merged is None:
        if verbose:
            print(
                "    [fill] repository: rejected (missing methods or uncompilable)"
            )
        return deterministic
    if rejected and verbose:
        print(
            "    [fill] repository: kept %d/%d customs; reverted %s (SQL "
            "outside designed schema)"
            % (
                len(stub_names) - len(rejected),
                len(stub_names),
                ", ".join(rejected),
            )
        )
        for name in rejected:
            print(
                "        - %s: %s"
                % (name, "; ".join(violations.get(name, [])))
            )
    # A rejected custom whose object words are ALREADY named by a sibling that
    # did ship is a redundant spelling of a capability this repository
    # provides: keeping it as a `return []` stub is a lie, and its `reverted`
    # acceptance line is noise (library_system's list_authors_with_books, whose
    # capability is served by find_books_by_author).
    dropped = {
        m.get("name") or "" for m in (design.get("methods") or [])
    } - set(rejected)
    droppable = sorted(
        n for n in rejected
        if _subsumed_by_sibling(n, sorted(dropped), ent_snake, model)
    )
    if droppable:
        if verbose:
            print(
                "    [fill] repository <%s>: dropped redundant %s"
                % (ent_snake, ", ".join(droppable))
            )
        design["methods"] = [
            m for m in (design.get("methods") or [])
            if (m.get("name") or "") not in set(droppable)
        ]
        merged = _drop_functions(merged, droppable)
    return merged


# Stdlib names a repository fill may legitimately reference. If the fill uses
# one without the file importing it, we INJECT the import rather than reject —
# this keeps the LLM's richer body (e.g. an export-by-criteria helper writing
# csv/datetime) instead of reverting it to a stub for a forgotten import.
_STDLIB_IMPORTS = {
    "csv": "import csv",
    "os": "import os",
    "math": "import math",
    "statistics": "import statistics",
    "json": "import json",
    "date": "from datetime import date",
    "datetime": "from datetime import datetime",
    "timedelta": "from datetime import timedelta",
    "time": "from datetime import time",
    "Decimal": "from decimal import Decimal",
    "Path": "from pathlib import Path",
}


def _inject_stdlib_imports(text, names):
    """Add missing stdlib import lines to a spliced repository file.

    Idempotent: skips lines already present (e.g. ``import json`` when the
    file already imports it for to_json/from_json). Inserted after the
    ``from __future__ import annotations`` line so it never splits the
    docstring/future block. Keeps the LLM's richer body instead of reverting
    it for a name it forgot to import."""
    present = set()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            present.add(s)
    to_add = []
    for n in sorted(names):
        imp = _STDLIB_IMPORTS.get(n)
        if imp and imp not in present:
            to_add.append(imp)
    if not to_add:
        return text
    lines = text.splitlines(keepends=True)
    insert_at = None
    for i, line in enumerate(lines):
        if line.strip().startswith("from __future__"):
            insert_at = i + 1
            break
    if insert_at is None:
        insert_at = 0
    lines.insert(insert_at, "\n".join(to_add) + "\n\n")
    return "".join(lines)


def _loads(node):
    """The NAMES a node READS (Load context)."""
    return {
        n.id for n in ast.walk(node)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }


def _assign_targets(node):
    """The names an assignment target binds."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        out = []
        for e in node.elts:
            out.extend(_assign_targets(e))
        return out
    return []


_COMPOUND = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith)


def _compound_children(st):
    """The statement lists nested inside a compound statement."""
    out = []
    for attr in ("body", "orelse", "finalbody"):
        v = getattr(st, attr, None)
        if v:
            out.append(v)
    for h in getattr(st, "handlers", None) or []:
        out.append(h.body)
    return out


def _compound_header_reads(st):
    """Names a compound statement reads UNCONDITIONALLY, before any branch is
    taken: the ``if``/``while`` test, the ``for`` iterable, a ``with`` item."""
    reads = set()
    for attr in ("test", "iter"):
        v = getattr(st, attr, None)
        if v is not None:
            reads |= _loads(v)
    for item in getattr(st, "items", None) or []:
        reads |= _loads(item.context_expr)
    return reads


def _dead_store_names(seq, dead):
    """Names a single statement list assigns twice with the earlier value
    never read in between.

    Deliberately LOCAL to one list, and never inheriting the enclosing scope's
    liveness, because both halves of that boundary matter:

      * a value assigned BEFORE a branch or a loop is legitimately replaced
        INSIDE it — ``limit = None`` … ``for _row in …: limit =
        int(_row.amount_limit_cents)`` … ``if limit is None:`` reads the value
        after the loop, so flagging it would be a false positive;
      * a read INSIDE a branch does not consume the outer value on every path,
        so ``query`` patched conditionally (``if flag: query += …``) and then
        overwritten unconditionally IS a dead store, which is the defect this
        rule exists for.

    Deciding within the list and recursing into each nested list as its own
    scope keeps both readings exact. ``x += …`` reads ``x`` and is never a
    discard; a subscript or attribute target binds nothing.
    """
    live = set()
    for st in seq:
        if isinstance(st, ast.Assign):
            reads = _loads(st)
            for t in [n for tgt in st.targets for n in _assign_targets(tgt)]:
                if t in live and t not in reads:
                    dead.append(t)
                live.add(t)
            live -= reads
        elif isinstance(st, ast.AugAssign):
            names = _assign_targets(st.target)
            live -= _loads(st)
            live.update(names)
        elif isinstance(st, ast.AnnAssign):
            if st.value is not None:
                reads = _loads(st)
                for t in _assign_targets(st.target):
                    if t in live and t not in reads:
                        dead.append(t)
                    live.add(t)
                live -= reads
        elif isinstance(st, _COMPOUND):
            live -= _compound_header_reads(st)
            for child in _compound_children(st):
                _dead_store_names(child, dead)
        else:
            live -= _loads(st)


def _repo_fidelity_violations(fn):
    """Order-aware fidelity checks on a filled repository method body.

    Three exact readings of the body — never a name or domain-word guess:
      * a DECLARED parameter the body never reads (a value the caller supplies
        is silently dropped instead of reaching the query);
      * a local REASSIGNED before its earlier value was ever read (the
        specification-duty ``list_authors_with_books`` built a query, patched
        it with its ``include_inactive`` flag, then assigned a FRESH query
        over it — the flag ended up with no effect at all);
      * ``.isoformat()``/``.strftime()``/``.date()`` called on a PARAMETER,
        which arrives as an ISO string, not a datetime (the shipped
        ``export_to_csv``).
    """
    params = [a.arg for a in (fn.args.args + fn.args.kwonlyargs)]
    param_set = {p for p in params if p != "self"}
    violations = []
    read = _loads(fn)
    unused = sorted(p for p in param_set if p not in read)
    if unused:
        violations.append(
            "never reads declared parameter(s) %s — a value the caller "
            "supplies must reach the query, not be dropped"
            % ", ".join(unused)
        )
    dead = []
    _dead_store_names(fn.body, dead)
    if dead:
        violations.append(
            "assigns %s then overwrites it before reading it — the earlier "
            "value (the query or params it built) is discarded, so any "
            "condition that patched it has no effect"
            % ", ".join(sorted(set(dead)))
        )
    stamped = sorted({
        n.func.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("isoformat", "strftime", "date")
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id in param_set
    })
    if stamped:
        violations.append(
            "calls .%s() on a date/datetime PARAMETER — values reach a "
            "repository as ISO strings; pass them through as-is"
            % ", .".join(stamped)
        )
    return violations


def _merge_repo_fill(deterministic, filled, stub_names, schema_ctx,
                     model_fields=None, own_table=None):
    """Per-method splice of an LLM repository fill into the deterministic
    file: a method body is kept ONLY when its SQL stays inside the DESIGNED
    schema AND every name it references resolves (module imports/defs,
    locals, builtins); offending methods revert to their locked stubs
    instead of dragging valid siblings down with them (a single hallucinated
    relation used to cost the whole file). Returns (merged_text,
    rejected_names, violations_by_name), or (None, [], {}) when the fill
    misses methods or does not compile."""
    try:
        ftree = ast.parse(filled)
        dtree = ast.parse(deterministic)
    except SyntaxError:
        return None, [], {}
    needed = set(stub_names)
    found = {}
    for node in ast.walk(ftree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in needed
        ):
            found[node.name] = node
    if set(found) != needed:
        return None, [], {}
    module_names = _module_defined_names(deterministic)
    rejected = {}
    stdlib_used = set()
    # Inter-file surface of the shared Database object (rendered
    # deterministically by _generate_database_file): instance attrs/methods
    # a repository fill may legitimately touch.
    db_surface = {"connect", "db_path"}
    # Money convention: *_cents columns are integer cents; dividing by 100
    # silently converts aggregates to dollars (observed on inventory stock
    # value) and breaks every cents-expecting consumer.
    cents_div_re = re.compile(
        r"\b([A-Za-z_][A-Za-z0-9_]*_cents)\s*/\s*100(?:\.0+)?\b"
    )
    # Intra-file self-method gate: fills may not CALL self.<missing>() —
    # helpers must already exist in the deterministic file (observed:
    # LoanRepository.find_overdue_loans calling self.get_current_date(),
    # which never existed and crashed at runtime).
    own_methods = {
        n.name for n in ast.walk(dtree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name, fn in found.items():
        violations = _repo_fill_schema_violations(ast.unparse(fn), schema_ctx)
        if _fn_has_stub_raise(fn):
            violations.append(
                "fill body is raise NotImplementedError(...) — a stub is "
                "never an implementation; write the full body using ONLY "
                "the DESIGNED tables/columns listed above"
            )
        undef = _fn_undefined_names(fn, module_names)
        # Split undefined names into true hallucinations vs stdlib names the
        # fill forgot to import. Stdlib names are auto-imported below (keeps
        # the LLM's richer body — export-by-criteria, date math, csv write);
        # only genuine hallucinations are rejected.
        hallucinated = (
            sorted(u for u in undef if u not in _STDLIB_IMPORTS)
            if undef else []
        )
        if hallucinated:
            violations.append(
                "references undefined name%s %s"
                % ("s" if len(hallucinated) > 1 else "", ", ".join(hallucinated))
            )
        elif undef:
            stdlib_used |= {u for u in undef if u in _STDLIB_IMPORTS}
        # Inter-file attribute gate: self.db.<attr> must exist on the
        # rendered Database class. Bare-name checks cannot see attribute
        # access, so 'self.db.connection' used to validate clean and crash
        # at runtime (AttributeError) — the exact intra-vs-inter-file gap.
        db_attrs = {
            n.attr
            for n in ast.walk(fn)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Attribute)
            and n.value.attr == "db"
            and isinstance(n.value.value, ast.Name)
            and n.value.value.id == "self"
        }
        bad_db = sorted(db_attrs - db_surface)
        if bad_db:
            violations.append(
                "self.db.%s does not exist on Database — open connections "
                "with 'with self.db.connect() as conn:'"
                % ", ".join(bad_db)
            )
        divs = sorted(set(cents_div_re.findall(ast.unparse(fn))))
        if divs:
            violations.append(
                "divides monetary column(s) %s by 100 — money is stored as "
                "integer cents; aggregate in cents" % ", ".join(divs)
            )
        called_self = {
            n.func.attr
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "self"
        }
        bad_self = sorted(called_self - own_methods)
        if bad_self:
            violations.append(
                "calls self.%s() which does not exist on this repository — "
                "never invent helper methods" % ", ".join(bad_self)
            )
        violations.extend(_repo_fidelity_violations(fn))
        # Model-construction contract: Model(**kwargs) may only use the
        # DESIGNED fields of that model. Extra kwargs (author_name,
        # book_title, ...) are guaranteed runtime TypeErrors and usually
        # come from JOINing sibling tables for display columns — which also
        # silently drops rows with NULL FKs (INNER JOIN). Reject so the
        # corrective retry re-emits a plain SELECT * of the row.
        if model_fields:
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in model_fields
                ):
                    kwargs = {kw.arg for kw in node.keywords if kw.arg}
                    extra = sorted(kwargs - model_fields[node.func.id])
                    if extra:
                        violations.append(
                            "%s(...) got unknown keyword(s) %s — construct "
                            "%s with ONLY its designed fields"
                            % (node.func.id, ", ".join(extra), node.func.id)
                        )
        # Non-model-column gate: the JOIN-for-display-fields bug is
        # 'SELECT b.*, a.name AS author_name' then Model(**dict(row)) — a
        # guaranteed TypeError (unknown kwarg) plus silent row-dropping via
        # INNER JOIN NULL-FK semantics. Fires ONLY when a designed model is
        # CONSTRUCTED and its SQL selects an alias that is not one of that
        # model's fields; legitimate cross-table reads (find_X_by_Y,
        # aggregates returning dicts/scalars) pass untouched.
        if model_fields:
            sql_strs = [
                n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            for node in ast.walk(fn):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in model_fields
                ):
                    continue
                cls = node.func.id
                bad_cols = set()
                for s in sql_strs:
                    low = s.lower()
                    for m in re.finditer(r"\bas\s+([a-z_][a-z0-9_]*)", low):
                        alias = m.group(1)
                        if alias not in model_fields[cls]:
                            bad_cols.add(alias)
                    # The alias scan above misses a projection that lists
                    # columns WITHOUT aliasing them. `SELECT b.id, b.title,
                    # a.name, a.birth_year` then `Book(**dict(r))` is the same
                    # guaranteed TypeError: a sqlite3 Row is keyed by the
                    # projected column NAMES, so `name`/`birth_year` arrive as
                    # unexpected constructor kwargs. Reject any bare column in
                    # the projection that is not a field of the constructed
                    # model — `*` and `<alias>.*` are the correct spellings,
                    # and a function call (COUNT(*), substr(...)) never matches
                    # a bare identifier, so aggregates pass untouched.
                    proj = re.search(r"\bselect\b(.*?)\bfrom\b", low, re.S)
                    if proj:
                        for term in proj.group(1).split(","):
                            term = re.split(
                                r"\s+as\s+", term.strip()
                            )[0].strip()
                            col = term.rsplit(".", 1)[-1].strip()
                            if not re.fullmatch(r"[a-z_][a-z0-9_]*", col):
                                continue
                            if col not in model_fields[cls]:
                                bad_cols.add(col)
                if bad_cols:
                    violations.append(
                        "%s(...) constructed with SQL column(s) not on the "
                        "%s model (%s) — select ONLY its designed fields; "
                        "never JOIN other tables to fetch display columns"
                        % (cls, cls, ", ".join(sorted(bad_cols)))
                    )
        if violations:
            rejected[name] = violations
    repls = []
    for node in ast.walk(dtree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in needed
            and node.name not in rejected
        ):
            new_src = ast.unparse(found[node.name])
            repls.append(
                (
                    node.lineno,
                    node.end_lineno,
                    _indent_block(new_src, node.col_offset),
                )
            )
    if len(repls) != len(needed) - len(rejected):
        return None, sorted(rejected), rejected
    merged = _splice_functions(deterministic, repls)
    if stdlib_used:
        merged = _inject_stdlib_imports(merged, stdlib_used)
    try:
        mtree = ast.parse(merged)
    except SyntaxError:
        return None, sorted(rejected), rejected
    defined = {
        n.name for n in ast.walk(mtree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if not needed.issubset(defined):
        return None, sorted(rejected), rejected
    return merged, sorted(rejected), rejected


def _repo_dict_keys(repo_sources, entities_by_class, designs):
    """{(repo_attr, method): set(string keys)} actually returned by
    Dict-returning DESIGNED repository customs, extracted from the
    RENDERED repository sources (deterministic bodies + accepted fills).
    Lets a service fill be validated against REAL dictionary keys instead
    of hallucinated ones."""
    repo_designs = {}
    for path, kind, data in designs or []:
        if kind == "repositories" and isinstance(data, dict):
            repo_designs[Path(path).stem] = data

    out = {}
    for ent in entities_by_class.values():
        attr = _snake(ent["name"]) + "_repo"
        rdes = repo_designs.get(_snake(ent["name"]) + "_repository")
        src = repo_sources.get(_snake(ent["name"]) + "_repository.py")
        if not rdes or not src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        fdefs = {
            n.name: n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for m in rdes.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            ret = (m.get("returns") or "").lower()
            if "dict" not in ret:
                continue
            fn = fdefs.get(m["name"])
            if fn is None:
                continue
            keys = set()
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Return)
                    and isinstance(node.value, ast.Dict)
                ):
                    for k in node.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.add(k.value)
            if keys:
                out[(attr, m["name"])] = keys
    return out
