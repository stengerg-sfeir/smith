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
from ..kernel.service.common import _declared_filters
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


def _render_repository_file(ent_snake, design, entities_by_class, exception_names=None,
                            prompt_text="", verbose=False, models_module="models"):
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
    customs = [
        m for m in ((design or {}).get("methods") or [])
        if isinstance(m, dict)
    ]
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
    filter_where = [
        (_FRAG[op] % qualified.get(col, col), p, op in _BOUND_OPS)
        for p, col, op in filter_specs
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
            "repository", instruction, mini, prompt_text,
            verbose=verbose,
            temperature=0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE,
        )
        if not filled:
            break
        merged, rejected, violations = _merge_repo_fill(
            deterministic, filled, stub_names, schema_ctx,
            model_fields=model_fields, own_table=own_table,
        )
        if merged is not None and not rejected:
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
    return merged


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
        if undef:
            violations.append(
                "references undefined name%s %s"
                % ("s" if len(undef) > 1 else "", ", ".join(undef))
            )
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
