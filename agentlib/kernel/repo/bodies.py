"""Repository method-body group recipe (verbatim from agent.py).

The giant deterministic dispatcher for designed custom repository methods,
moved out of agent.py as a single "group" recipe so all downstream
signature/return/field checks stay byte-identical. Registered as a
discoverable `RECIPES` list under the kernel repo package.
"""
import re

from ...design import (
    _camel_to_snake,
    _entity_token,
    _feas_token_resolves,
    _is_aggregate_bound,
    _param_is_child_fk,
    _param_is_other_entity_field,
)
from ...naming import _camel, _entity_table_name
from ..recipe_types import Recipe
from ..service.common import _filter_params
from .aggregates import _repo_extra_body
from .limit_status import _limit_status_body
from .threshold_compare import _threshold_compare_body


def _repo_method_body(m, ent, ent_snake, model, entities_by_class=None):
    """Deterministic body lines for a designed custom repository method, or
    None (=> stub, then LLM fill).

    Declarative-first, then signature-shape recipes bounded by the DESIGNED
    schema (every column reference must resolve to a real designed field):

      impl {"kind": "list_filtered"}          -> delegate to self.list(...)
      CRUD shadow  create_<e>/get_<e>_by_id/
                   delete_<e>/update_<e>      -> alias the canonical CRUD body
      params subset of declared filters       -> delegate to self.list(...)
      *_count[_by_<col>]                      -> COUNT(*) [GROUP BY col]
      unique numeric col, scalar total        -> SUM(col)
      _by_<col> over unique numeric col       -> SUM(col) GROUP BY col
      _highest_<col>/_lowest_<col>/latest...  -> ORDER BY col LIMIT 1
      LIKE params (<field>_prefix/_contains,
                   lone term over unique str) -> WHERE col LIKE ?
      pagination (limit[/offset] + filters)   -> LIMIT/OFFSET query
      tuple[<Ent>, int]-shaped child count    -> JOIN + COUNT top-N
      dict[..., int]-shaped fk counts         -> GROUP BY fk counts
      dict[<Ent>, <Other>]                    -> per-row joined lookup
      <col>_prefix/_pattern/_domain + page_*  -> LIKE x pagination composer
      days_ago-style duration                 -> recency window over date col
      *_range over start/end pair             -> bounded date comparison
      *_count_by_month/year                   -> substr bucket GROUP BY
      export/import <e>_(to|from)_json        -> json.dumps / validated insert
      unresolvable discriminator param        -> honest empty set (never a
                                                 stub: no row can match
                                                 data the schema cannot hold)

    Anything unmatched stays a locked stub for _llm_fill. No domain
    vocabulary: every recipe keys on signatures, return annotations, and
    the designed fields/filters of THIS entity.
    """
    if not ent:
        return None
    name = m.get("name") or ""
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    ret = (m.get("returns") or "").strip()
    ret_l = ret.lower()
    fields = {
        f.get("name"): f
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }
    table = _entity_table_name(ent)
    lfmap = {
        s.get("param"): s
        for s in (ent.get("list_filters") or [])
        if isinstance(s, dict) and s.get("param")
    }
    num_cols = [
        n for n, f in fields.items()
        if f.get("type") in ("int", "float")
        and n != "id" and not n.endswith("_id")
    ]
    str_cols = [n for n, f in fields.items() if f.get("type") == "str"]
    date_cols = [
        n for n, f in fields.items()
        if f.get("type") in ("date", "datetime")
    ]

    # ---- declared-filter WHERE builder ------------------------------------
    def _where(ps):
        conds, binds = [], []
        for p in ps:
            spec = lfmap.get(p)
            if not spec:
                return None, None
            col, op = spec.get("column"), spec.get("op")
            if op == "eq":
                conds.append("%s = ?" % col)
                binds.append(p)
            elif op == "gte":
                conds.append("%s >= ?" % col)
                binds.append(p)
            elif op == "lte":
                conds.append("%s <= ?" % col)
                binds.append(p)
            elif op == "eq_true":
                conds.append("%s = 1" % col)
            elif op == "gt_zero":
                conds.append("%s > 0" % col)
            else:
                return None, None
        frag = (" WHERE " + " AND ".join(conds)) if conds else ""
        return frag, binds

    # Suffixes a BOOLEAN filter param carries when it GUARDS a column rather
    # than filtering it by value ("available_only" -> "available_copies").
    flag_suffixes = ("_only", "_flag", "_present", "_exists", "_active")

    def _own_filter_specs(ps):
        """[(param, (column, op))] for params filtering the OWNER's columns.

        Returns None when any param cannot be explained. A designed field
        name filters by equality; a declared list-filter param keeps its
        declared column/op; a bool param naming a column through a bounded
        suffix rule (``available_only`` -> the unique field starting with
        ``available_``, i.e. ``available_copies``) guards that column. This is
        what lets an owner-ref list emit a CONDITIONAL WHERE: an omitted
        optional filter must drop its clause, never bind NULL (which matches
        no row at all — library's ``library book list`` listed nothing).
        """
        out = []
        for p in ps:
            spec = lfmap.get(p)
            if spec and spec.get("column"):
                out.append((p, (spec.get("column"), spec.get("op") or "eq")))
                continue
            if p in fields:
                out.append((p, (p, "eq")))
                continue
            base = next(
                (p[: -len(s)] for s in flag_suffixes if p.endswith(s)), None
            )
            col = None
            if base:
                if base in fields:
                    col = base
                else:
                    starts = [n for n in fields if n.startswith(base + "_")]
                    ends = [n for n in fields if n.endswith("_" + base)]
                    cands = starts or ends
                    col = cands[0] if len(cands) == 1 else None
            if col is None:
                return None
            ftype = fields[col].get("type")
            if ftype == "bool":
                out.append((p, (col, "eq_true")))
            elif ftype in ("int", "float"):
                out.append((p, (col, "gt_zero")))
            else:
                return None
        return out

    def _tup(srcs):
        """Python tuple-literal source for SQL parameter binding. A
        single-element list MUST emit '(x,)': bare '(x)' is just x in
        call position, and sqlite3 rejects it ('parameters are of
        unsupported type')."""
        if len(srcs) == 1:
            return "(%s,)" % srcs[0]
        return "(%s)" % ", ".join(srcs)

    def _exec_scalar(sql, binds):
        lines = [
            "        with self.db.connect() as conn:",
            "            row = conn.execute(",
            '                "%s",' % sql,
        ]
        if binds:
            lines.append("                %s" % _tup(binds))
        lines += [
            "            ).fetchone()",
            '            return int(row["n"])',
        ]
        return lines

    # ---- 0. limit-status verdict ------------------------------------------
    # Ahead of every list route: a method DECLARING a status string over a
    # limit entity ("check if a category has exceeded its budget") must
    # compare spending to the stored limit, never delegate to self.list().
    # Rendered only when the designed shape pins every column involved.
    status_lines = _limit_status_body(
        m, ent, params, ret, entities_by_class, model
    )
    if status_lines is not None:
        return status_lines

    # ---- 0.5 below-the-referenced-threshold list ---------------------------
    # The threshold lives on the REFERENCED row, which no single-table recipe
    # can express — such a method shipped `return []`, so the command behind
    # it listed nothing even when the condition held.
    threshold_lines = _threshold_compare_body(
        m, ent, model, params, ret, entities_by_class
    )
    if threshold_lines is not None:
        return threshold_lines

    # ---- 1. declared impl: list_filtered -----------------------------------
    # Delegate when the method's params map onto declared filters; when they
    # do NOT, fall through to the shape recipes below instead of bailing —
    # a stale/defaulted stamp must never shadow count/sum/top/join bodies.
    impl = m.get("impl")
    if isinstance(impl, dict) and impl.get("kind") == "list_filtered":
        # ``self.list(...)`` yields the entity's ROWS: a method declaring a
        # scalar or a status string must never take this route. Budget's
        # ``check_budget_exceeded -> str`` shipped ``return self.list(...)``
        # — a List[Budget] under a str annotation, so the capability the
        # specification requires returned no verdict at all.
        if ret_l and "list" not in ret_l and model not in ret:
            return None
        valid = _filter_params(ent)
        args = [p for p in params if p in valid]
        if args and len(args) == len(params):
            lines = ["        return self.list("]
            lines += ["            %s=%s," % (p, p) for p in args]
            lines += ["        )"]
            return lines

    esnake = re.escape(ent_snake)

    # ---- 2. CRUD shadows ---------------------------------------------------
    if re.fullmatch(r"create_%s" % esnake, name):
        cols = [p for p in params if p in fields and p != "id"]
        if cols and len(cols) == len(params):
            kw = ", ".join("%s=%s" % (c, c) for c in cols)
            return [
                "        obj = %s(%s)" % (model, kw),
                "        self.create(obj)",
                "        return obj",
            ]
        return None
    if re.fullmatch(r"get_%s_by_id" % esnake, name) and params == ["id"]:
        return ["        return self.get_by_id(id)"]
    if (
        re.fullmatch(r"(?:delete|remove)_%s" % esnake, name)
        and params == ["id"]
    ):
        return ["        return self.delete(id)"]
    if re.fullmatch(r"update_%s" % esnake, name) and params:
        if params[0] != "id":
            return None
        upd_cols = [p for p in params[1:] if p in fields]
        if not upd_cols or len(upd_cols) != len(params) - 1:
            return None
        items = ", ".join('"%s": %s' % (c, c) for c in upd_cols)
        lines = [
            "        data = {%s}" % items,
            "        updated = self.update(id, data)",
        ]
        if "bool" in ret_l:
            lines.append("        return updated")
            return lines
        lines += [
            "        if not updated:",
            "            return None",
            "        return self.get_by_id(id)",
        ]
        return lines

    is_list_model = (
        (model in ret and ("List[" in ret or "list[" in ret))
        or ret_l == "list"
    )
    is_opt_model = model in ret and "Optional[" in ret

    # ---- 3. filtered-list delegation (declared or aliasable params) --------
    # Exact filter-param match first; then bound aliases: min_<x>/max_<x>
    # may bind to ANY declared gte/lte filter over the resolved column
    # (the LLM often declares the same bound under a different name, e.g.
    # method min_price vs declared filter "price" op=gte).
    if params and is_list_model:
        kwargs = []
        resolvable = True
        for p in params:
            if p in lfmap:
                kwargs.append((p, p))
                continue
            alias = None
            bm = re.fullmatch(r"(min|max)_(.+)", p)
            if bm:
                pre, suf = bm.group(1), bm.group(2)
                want_op = "gte" if pre == "min" else "lte"
                comparable = [
                    n for n, f in fields.items()
                    if f.get("type")
                    in ("int", "float", "date", "datetime")
                ]
                col = None
                if suf in comparable:
                    col = suf
                else:
                    suffixed = [
                        c for c in comparable if c.endswith("_" + suf)
                    ]
                    if len(suffixed) == 1:
                        col = suffixed[0]
                    elif len(comparable) == 1:
                        col = comparable[0]
                if col is not None:
                    spec = next(
                        (
                            s for s in (ent.get("list_filters") or [])
                            if isinstance(s, dict)
                            and s.get("column") == col
                            and s.get("op") == want_op
                        ),
                        None,
                    )
                    if spec:
                        alias = spec.get("param")
            if alias is None:
                resolvable = False
                break
            kwargs.append((alias, p))
        if resolvable:
            lines = ["        return self.list("]
            lines += ["            %s=%s," % (a, p) for a, p in kwargs]
            lines += ["        )"]
            return lines

    # ---- 4. counts ----------------------------------------------------------
    cm = re.search(r"_count(?:_by_([a-z][a-z0-9_]*))?$", name)
    if cm:
        bycol = cm.group(1)
        frag, binds = _where(params)
        if frag is not None:
            if bycol is None and "int" in ret_l and "dict" not in ret_l:
                return _exec_scalar(
                    "SELECT COUNT(*) AS n FROM %s%s" % (table, frag), binds
                )
            if (
                bycol is not None
                and bycol in fields
                and "dict" in ret_l
                and not binds
            ):
                # Grouped + bound filters would need an ordering contract;
                # leave those to the fill rather than guess semantics.
                return [
                    "        with self.db.connect() as conn:",
                    "            rows = conn.execute(",
                    '                "SELECT %s AS k, COUNT(*) AS n FROM %s'
                    ' GROUP BY %s"' % (bycol, table, bycol),
                    "            ).fetchall()",
                    '            return {r["k"]: int(r["n"]) for r in rows}',
                ]

    # ---- 5. sums over the unique numeric column ----------------------------
    # Column resolution: prefer the unique numeric whose declared type
    # matches the annotated return type (float total over money columns,
    # int total over counters); fall back to overall uniqueness.
    if (
        ret_l in ("float", "int")
        and not name.endswith("_count")
        and (not params or set(params) <= set(lfmap))
    ):
        typed = [
            n for n in num_cols if fields[n].get("type") == ret_l
        ]
        ncol = None
        if len(typed) == 1:
            ncol = typed[0]
        elif len(num_cols) == 1:
            ncol = num_cols[0]
        frag, binds = _where(params)
        if ncol is not None and frag is not None:
            lines = [
                "        with self.db.connect() as conn:",
                "            row = conn.execute(",
                '                "SELECT COALESCE(SUM(%s), 0) AS v'
                ' FROM %s%s",' % (ncol, table, frag),
            ]
            if binds:
                lines.append("                %s" % _tup(binds))
            lines += [
                "            ).fetchone()",
                '            return float(row["v"])'
                if ret_l == "float"
                else '            return int(row["v"])',
            ]
            return lines
    sm = re.search(r"_by_([a-z][a-z0-9_]*)$", name)
    if (
        sm
        and "dict" in ret_l
        and sm.group(1) in fields
        and len(num_cols) == 1
        and not params
    ):
        gb, ncol = sm.group(1), num_cols[0]
        return [
            "        with self.db.connect() as conn:",
            "            rows = conn.execute(",
            '                "SELECT %s AS k, SUM(%s) AS v FROM %s'
            ' GROUP BY %s"' % (gb, ncol, table, gb),
            "            ).fetchall()",
            '            return {r["k"]: float(r["v"] or 0)'
            ' for r in rows}',
        ]

    # ---- 6. top-1 / top-N by designed column --------------------------------
    tm = re.search(
        r"_(highest|lowest|max|min|latest|newest|earliest|oldest)_"
        r"([a-z][a-z0-9_]*)$",
        name,
    )

    def _qual_col(t):
        """Schema grounding for a qualifier token: exact field match, else
        the UNIQUE field whose name ends with it ('lowest_copies' ->
        'available_copies')."""
        if t in fields:
            return t
        cands = [f for f in fields if f.endswith(t)]
        return cands[0] if len(cands) == 1 else None

    if tm and is_opt_model:
        word = tm.group(1)
        qcol = _qual_col(tm.group(2))
        if qcol is not None:
            desc = word in ("highest", "max", "latest", "newest")
            return [
                "        with self.db.connect() as conn:",
                "            row = conn.execute(",
                '                "SELECT * FROM %s ORDER BY %s %s'
                ' LIMIT 1"' % (table, qcol, "DESC" if desc else "ASC"),
                "            ).fetchone()",
                '            return %s(**dict(row)) if row else None'
                % model,
            ]
        # Unresolvable qualifier: locked stub for the LLM fill — never
        # fall through to generic pagination, which would misorder rows.
        return None
    if tm and is_list_model:
        word = tm.group(1)
        desc = word in ("highest", "max", "latest", "newest")
        qcol = _qual_col(tm.group(2))
        if set(params) <= {"limit"} and qcol is not None:
            # Top-N with an explicit limit param: deterministic ordering
            # contract (ORDER BY the grounded column, bound LIMIT).
            return [
                "        with self.db.connect() as conn:",
                "            rows = conn.execute(",
                '                "SELECT * FROM %s ORDER BY %s %s'
                ' LIMIT ?",' % (table, qcol, "DESC" if desc else "ASC"),
                "                %s" % _tup(["limit"]),
                "            ).fetchall()",
                '            return [%s(**dict(r)) for r in rows]' % model,
            ]
        if (
            not params
            and word in ("latest", "newest")
            and (qcol is not None or len(date_cols) == 1)
        ):
            dcol = qcol if qcol is not None else date_cols[0]
            return [
                "        with self.db.connect() as conn:",
                "            rows = conn.execute(",
                '                "SELECT * FROM %s ORDER BY %s DESC"'
                % (table, dcol),
                "            ).fetchall()",
                '            return [%s(**dict(r)) for r in rows]' % model,
            ]
        return None

    # ---- 7. LIKE searches ---------------------------------------------------
    like_pairs = []
    for p in params:
        for suf in ("_prefix", "_contains", "_pattern", "_substring"):
            if p.endswith(suf) and p[: -len(suf)] in str_cols:
                like_pairs.append((p, p[: -len(suf)]))
                break
    if (
        not like_pairs
        and len(params) == 1
        and params[0] in ("term", "query", "keyword")
        and len(str_cols) == 1
    ):
        like_pairs.append((params[0], str_cols[0]))
    if like_pairs and is_list_model and set(params) == {
        p for p, _ in like_pairs
    }:
        conds = ["%s LIKE ?" % c for _, c in like_pairs]
        binds = ['"%%" + %s + "%%"' % p for p, _ in like_pairs]
        return [
            "        with self.db.connect() as conn:",
            "            rows = conn.execute(",
            '                "SELECT * FROM %s WHERE %s",' % (table, " AND ".join(conds)),
            "                %s" % _tup(binds),
            "            ).fetchall()",
            '            return [%s(**dict(r)) for r in rows]' % model,
        ]

    # ---- 8. pagination -------------------------------------------------------
    if is_list_model and "limit" in params:
        extra = [p for p in params if p not in ("limit", "offset")]
        if set(extra) <= set(lfmap):
            frag, binds = _where(extra)
            if frag is not None:
                order = binds + (["limit"] + (["offset"] if "offset" in params else []))
                lim = " LIMIT ? OFFSET ?" if "offset" in params else " LIMIT ?"
                lines = [
                    "        with self.db.connect() as conn:",
                    "            rows = conn.execute(",
                    '                "SELECT * FROM %s%s%s",' % (table, frag, lim),
                ]
                if order:
                    lines.append("                %s" % _tup(order))
                lines += [
                    "            ).fetchall()",
                    '            return [%s(**dict(r)) for r in rows]'
                    % model,
                ]
                return lines

    # ---- 8.5 search x pagination composer -----------------------------------
    # Covers the shapes the strict recipes above decline:
    #   * suffixed search params (<col>_prefix/_pattern/_domain/...) whose
    #     column resolves by suffix-stripping, plus bare query/pattern/domain
    #     terms searching EVERY text column (OR);
    #   * page/page_size (or page_number/per_page) pagination aliases;
    #   * both at once (WHERE ... LIKE ... LIMIT ? OFFSET ?).
    # Declared-filter params ride along through the shared _where builder;
    # anything else unresolved aborts the composer so stricter blocks or
    # the final fallback can decide.
    page_roles = {}
    for p in params:
        if p in ("page", "page_number", "page_no"):
            page_roles[p] = "num"
        elif p in ("page_size", "size", "per_page", "limit"):
            page_roles[p] = "size"
        elif p == "offset":
            page_roles[p] = "off"

    def _fk_text_cols():
        """[(qualified column, LEFT JOIN clause)] for FK-reachable text.

        A search must reach the text a user actually types. A query LIKE'ing
        only the entity's own columns silently ignores a joined neighbour's
        name — library_system's ``search_book(query)`` searched ``title`` and
        ``isbn`` but not the AUTHOR, which the spec names as a search field
        ("searches across title/author/isbn", S17) and which lives on the
        entity the FK points at. Generic shape: for every ``<ref>_id`` column
        of the searching entity, LEFT JOIN the referenced table and search its
        text columns too. Structural, never domain vocabulary; an entity with
        no ``_id`` reference yields nothing.
        """
        extra = []
        if not entities_by_class:
            return extra
        for fname in fields:
            if fname == "id" or not fname.endswith("_id"):
                continue
            ref_ent = entities_by_class.get(_camel(fname[: -len("_id")]))
            if not isinstance(ref_ent, dict):
                continue
            ref_tbl = _entity_table_name(ref_ent)
            ref_cols = [
                f.get("name") for f in (ref_ent.get("fields") or [])
                if isinstance(f, dict) and f.get("name")
                and f.get("name") != "id" and f.get("type") == "str"
            ]
            if not ref_cols:
                continue
            join = "LEFT JOIN %s ON %s.%s = %s.id" % (
                ref_tbl, table, fname, ref_tbl)
            for c in ref_cols:
                extra.append(("%s.%s" % (ref_tbl, c), join))
        return extra

    def _compose_search_pages():
        """Shared emitter: LIKE groups + declared filters + paging."""
        conds, binds = [], []
        groups = []
        leftover = []
        for p in params:
            placed = False
            for suf in ("_prefix", "_contains", "_pattern", "_substring",
                        "_suffix", "_domain"):
                if p.endswith(suf):
                    base = p[: -len(suf)]
                    if base in str_cols:
                        groups.append((p, [base], False))
                        placed = True
                    else:
                        cands = [
                            c for c in str_cols
                            if c.endswith("_" + base)
                        ]
                        if len(cands) == 1:
                            groups.append((p, cands, False))
                            placed = True
                    break
            if not placed and p in (
                "term", "query", "keyword", "search", "pattern", "domain",
            ) and str_cols:
                # A bare term is a SEARCH, so it is WIDENED to the FK-reachable
                # text columns: a joined name (books -> authors.name) is found
                # alongside the entity's own text.
                groups.append((p, list(str_cols), True))
                placed = True
            if not placed:
                leftover.append(p)
        filt = [p for p in leftover if p in lfmap]
        pages = [p for p in leftover if p in page_roles]
        unknown = [
            p for p in leftover
            if p not in lfmap and p not in page_roles
        ]
        if unknown or not (groups or pages):
            return None
        # Resolve every group's column refs first, so each referenced table is
        # joined once and the entity's own columns are qualified exactly when a
        # join makes an unqualified name ambiguous.
        used_joins, resolved = [], []
        for p, cols, joinable in groups:
            refs = list(cols)
            if joinable:
                for ref, join in _fk_text_cols():
                    refs.append(ref)
                    if join not in used_joins:
                        used_joins.append(join)
            resolved.append((p, refs))
        for p, refs in resolved:
            defs = [
                ("%s.%s" % (table, c)) if used_joins and "." not in c else c
                for c in refs
            ]
            frag = " OR ".join("%s LIKE ?" % d for d in defs)
            conds.append("(%s)" % frag if len(refs) > 1 else frag)
            binds.extend(['"%%" + %s + "%%"' % p] * len(refs))
        if filt:
            ffrag, fbinds = _where(filt)
            if ffrag is None:
                return None
            if ffrag:
                conds.append(ffrag[len(" WHERE "):])
                binds.extend(fbinds)
        size = next((p for p in pages if page_roles[p] == "size"), None)
        num = next((p for p in pages if page_roles[p] == "num"), None)
        off = next((p for p in pages if page_roles[p] == "off"), None)
        lim, extra = "", []
        if size and (num or off):
            lim = " LIMIT ? OFFSET ?"
            extra = [size, "(%s - 1) * %s" % (num, size) if num else off]
        elif size:
            lim = " LIMIT ?"
            extra = [size]
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        join_sql = (" " + " ".join(used_joins)) if used_joins else ""
        # A join must not leak the joined table's columns into the entity
        # constructor: select the entity's OWN columns explicitly.
        select = ("%s.*" % table) if used_joins else "*"
        out = [
            "        with self.db.connect() as conn:",
            "            rows = conn.execute(",
            '                "SELECT %s FROM %s%s%s",'
            % (select, table + join_sql, where, lim),
        ]
        if binds or extra:
            out.append("                %s" % _tup(binds + extra))
        out += [
            "            ).fetchall()",
            '            return [%s(**dict(r)) for r in rows]' % model,
        ]
        return out

    # ---- 7.1 lone-term search over the entity's FK-reachable text ----------
    # The spec names a search over SEVERAL fields, and one of them may live on
    # a JOINed entity ("search_books(query): searches across title/author/isbn",
    # S17) — library's search_book LIKE'd only title/isbn and silently missed
    # the author. A single bare search term is an unambiguous shape, so render
    # it deterministically: LIKE over every text column of THIS entity plus
    # every text column of the entities it references through a ``<ref>_id``
    # column, joined in.
    #
    # This covers the design's ``List[Dict[str, Any]]`` row-list return as well
    # as an entity list: the repository builds ENTITY instances from each row
    # for that annotation too (the executor's convention, not a type claim).
    # Anything richer (extra filters, paging) is left to the composer below.
    _squashed = ret_l.replace(" ", "")
    is_row_list = _squashed.startswith("list[dict") or _squashed.startswith("list[list")
    if (
        (is_list_model or is_row_list)
        and len(params) == 1
        and params[0] in (
            "term", "query", "keyword", "search", "pattern", "domain",
        )
        and str_cols
    ):
        refs = ["%s.%s" % (table, c) for c in str_cols]
        joins, seen = [], set()
        for ref, join in _fk_text_cols():
            refs.append(ref)
            if join not in seen:
                seen.add(join)
                joins.append(join)
        if not joins:
            # No FK-reachable text: keep the unqualified form the composer and
            # the strict recipe have always emitted.
            refs = list(str_cols)
        frag = " OR ".join("%s LIKE ?" % r for r in refs)
        binds = ['"%%" + %s + "%%"' % params[0]] * len(refs)
        join_sql = (" " + " ".join(joins)) if joins else ""
        # A join must not leak the joined table's columns into the entity
        # constructor: select the entity's OWN columns explicitly.
        select = ("%s.*" % table) if joins else "*"
        return [
            "        with self.db.connect() as conn:",
            "            rows = conn.execute(",
            '                "SELECT %s FROM %s%s WHERE %s",'
            % (select, table, join_sql, frag),
            "                %s" % _tup(binds),
            "            ).fetchall()",
            '            return [%s(**dict(r)) for r in rows]' % model,
        ]

    if is_list_model:
        body = _compose_search_pages()
        if body is not None:
            return body

    # ---- 8.6 recency window (days_ago over the activity timestamp) ----------
    if is_list_model and date_cols and params:
        dur = next(
            (p for p in params if re.fullmatch(
                r"\w*?(days?_ago|days?_back)|within_days|recent_days|last_n_days",
                p,
            )),
            None,
        )
        if dur is not None:
            act = next(
                (c for c in date_cols if c in (
                    "updated_at", "modified_at", "last_seen_at",
                    "last_active_at",
                )),
                None,
            )
            if act is None and len(date_cols) == 1:
                act = date_cols[0]
            others = [
                p for p in params if p != dur and p not in page_roles
            ]
            if act is not None and not others:
                size = next(
                    (p for p in page_roles
                     if page_roles[p] == "size"),
                    None,
                )
                num = next(
                    (p for p in page_roles if page_roles[p] == "num"),
                    None,
                )
                lim, extra = "", []
                if size and num:
                    lim = " LIMIT ? OFFSET ?"
                    extra = [size, "(%s - 1) * %s" % (num, size)]
                elif size:
                    lim = " LIMIT ?"
                    extra = [size]
                lines = [
                    "        with self.db.connect() as conn:",
                    "            rows = conn.execute(",
                    '                "SELECT * FROM %s WHERE %s >='
                    " datetime('now', '-' || ? || ' days')%s\","
                    % (table, act, lim),
                ]
                binds = [dur] + extra
                lines.append("                %s" % _tup(binds))
                lines += [
                    "            ).fetchall()",
                    '            return [%s(**dict(r)) for r in rows]'
                    % model,
                ]
                return lines

    # ---- 8.7 overdue / expired ----------------------------------------------
    # ``is_row_list`` covers a design that annotates the method
    # ``List[Dict[str, Any]]`` (the row-list spelling the executor also builds
    # entity instances from). Requiring the ENTITY spelling left library's
    # ``get_overdue_loans`` without a body at all — a bare ``pass``/``return
    # []`` stub, which reported no overdue loan ever.
    if (is_list_model or is_row_list) and not params and re.search(
        r"_(?:is_)?(?:overdue|expired|past_due)", name
    ):
        due_cands = [
            c for c in date_cols if "due" in c or "expir" in c
        ]
        col = due_cands[0] if len(due_cands) == 1 else None
        if col is None:
            donly = [
                c for c in date_cols if fields[c].get("type") == "date"
            ]
            col = donly[0] if len(donly) == 1 else None
        if col is not None:
            # "Overdue" also means STILL OPEN: a row already closed out (a
            # returned loan) is past its due date but is not overdue. The
            # closure column is the design's own other nullable date column
            # whose name says the row was settled (returned/actual/closed/
            # completed/end/resolved/paid) — name-shape over the designed
            # schema, never domain vocabulary, and only when exactly one such
            # column exists.
            closure_cands = [
                c for c in date_cols
                if c != col and fields[c].get("nullable")
                and any(
                    tok in c for tok in (
                        "return", "actual", "closed", "completed",
                        "end", "resolved", "paid",
                    )
                )
            ]
            conds = ["%s IS NOT NULL" % col, "%s < date('now')" % col]
            if len(closure_cands) == 1:
                conds.append("%s IS NULL" % closure_cands[0])
            return [
                "        with self.db.connect() as conn:",
                "            rows = conn.execute(",
                '                "SELECT * FROM %s WHERE %s",'
                % (table, " AND ".join(conds)),
                "            ).fetchall()",
                '            return [%s(**dict(r)) for r in rows]' % model,
            ]

    # ---- 8.8 bounded date range (start/end pair) ----------------------------
    # Trigger on the bound parameter pair alone (start_/end_/from_/to_/min_/
    # max_/begin_ or _start/_end suffixes) over a unique date column — no
    # reliance on the method-name suffix, so e.g. get_sales_with_product_names
    # still compiles to a real date-range SELECT.
    if is_list_model and len(params) == 2:
        a, b = params

        def _bound(p):
            return bool(
                re.match(r"^(start|end|from|to|min|max|begin)", p)
                or p.endswith(("_start", "_end", "_from", "_to"))
            )

        if _bound(a) and _bound(b):
            col = None
            donly = [
                c for c in date_cols if fields[c].get("type") == "date"
            ]
            if len(donly) == 1:
                col = donly[0]
            elif len(date_cols) == 1:
                col = date_cols[0]
            if col is None:
                # Year-range shape: bound params over an int year column
                # (start_year/end_year -> published_year). A clear single
                # year column makes this real data, not honest-empty.
                year_cols = [
                    n for n in num_cols
                    if n.endswith("_year") or n == "year"
                ]
                if len(year_cols) == 1:
                    col = year_cols[0]
            if col is not None:
                return [
                    "        with self.db.connect() as conn:",
                    "            rows = conn.execute(",
                    '                "SELECT * FROM %s WHERE %s >= ?'
                    ' AND %s <= ?", (%s)'
                    % (table, col, col, _tup([a, b])),
                    "            ).fetchall()",
                    '            return [%s(**dict(r)) for r in rows]'
                    % model,
                ]

    # ---- 8.9 calendar-bucket counts (*_count_by_month/year/day) -------------
    bkm = re.search(r"_count_by_(month|year|day)$", name)
    if bkm and "dict" in ret_l and not params and date_cols:
        span = {"month": 7, "year": 4, "day": 10}[bkm.group(1)]
        col = date_cols[0] if len(date_cols) == 1 else None
        if col is None:
            dts = [
                c for c in date_cols
                if fields[c].get("type") == "datetime"
            ]
            col = dts[0] if len(dts) == 1 else None
        if col is not None:
            return [
                "        with self.db.connect() as conn:",
                "            rows = conn.execute(",
                '                "SELECT substr(%s, 1, %d) AS k,'
                " COUNT(*) AS n FROM %s GROUP BY k\""
                % (col, span, table),
                "            ).fetchall()",
                '            return {r["k"]: int(r["n"]) for r in rows}',
            ]

    # ---- 8.10 JSON export / import ------------------------------------------
    if re.fullmatch(r"export_%ss?_to_json" % esnake, name) \
            and ret_l == "str" and not params:
        return [
            "        with self.db.connect() as conn:",
            "            rows = conn.execute(",
            '                "SELECT * FROM %s ORDER BY id"' % table,
            "            ).fetchall()",
            "            payload = [",
            "                {k: row[k] for k in row.keys()}",
            "                for row in rows",
            "            ]",
            "            return json.dumps(payload)",
        ]
    if re.fullmatch(r"import_%ss?_from_json" % esnake, name) \
            and len(params) == 1 and ("bool" in ret_l or "int" in ret_l):
        allowed = ", ".join(
            '"%s"' % c for c in sorted(set(fields) | {"id"})
        )
        return [
            "        try:",
            "            data = json.loads(%s)" % params[0],
            "        except (ValueError, TypeError):",
            "            return False",
            "        if not isinstance(data, list):",
            "            return False",
            "        allowed = {%s}" % allowed,
            "        with self.db.connect() as conn:",
            "            try:",
            "                for item in data:",
            "                    if not isinstance(item, dict):",
            "                        return False",
            "                    values = {k: item[k] for k in item",
            "                               if k in allowed}",
            "                    if not values:",
            "                        return False",
            "                    cols = \", \".join(values)",
            "                    marks = \", \".join(\"?\" for _ in values)",
            "                    conn.execute(",
            "                        \"INSERT INTO %s ({}) VALUES ({})\""
            ".format(cols, marks)," % table,
            "                        tuple(values.values()),",
            "                    )",
            "                conn.commit()",
            "            except sqlite3.IntegrityError:",
            "                return False",
            "        return True",
        ]

    # ---- 8.11b flag list / dict aggregates (extra tier) --------------------
    # Bounded extra recipes (see .aggregates): a bool-flag List[<This>] gets a
    # real WHERE instead of the honest-empty [] further down, and a
    # Dict-returning custom gets a real SUM aggregate instead of the
    # cross-entity JOIN's raw-row list (expense's get_category_spending is
    # annotated Dict[str, int] yet 8.12b answered with [Expense(...)]).
    extra = _repo_extra_body(
        m, ent, model, name, params, ret_l, fields, table, lfmap,
        num_cols, date_cols, is_list_model, _where, _tup,
        entities_by_class=entities_by_class,
    )
    if extra is not None:
        return extra

    # ---- 8.12 cross-entity routing (child / owner-ref JOIN / m2m JOIN) ------
    # Repo customs that operate on ANOTHER designed entity (not the owner):
    #   child : get_customer_orders_with_pagination (customer repo) -> query
    #           orders via orders.customer_id FK (discriminator param)
    #   ref   : get_order_items_by_product_and_date_range (order_item repo) ->
    #           orderitems JOIN products via orderitems.product_id FK
    #   m2m   : get_posts_by_tag / search_posts -> posts JOIN posttags JOIN
    #           tags via a junction PostTag(post_id, tag_id)
    # Each emits a real deterministic SELECT. Shapes the engine cannot pin
    # fall through to the honest-empty/LLM-fill path — never a silent [].
    if entities_by_class and (is_list_model or "dict" in ret_l):
        ents = entities_by_class
        other_cls = None
        o_snake = None
        best = None
        for cls2, e2 in ents.items():
            if cls2 == model:
                continue
            sn2 = _camel_to_snake(cls2)
            f2 = {f.get("name") for f in (e2.get("fields") or [])
                  if isinstance(f, dict) and f.get("name")}
            is_child = (ent_snake + "_id") in f2
            is_ref = (sn2 + "_id") in fields
            has_junction = any(
                (ent_snake + "_id") in {
                    f.get("name") for f in (e3.get("fields") or [])
                    if isinstance(f, dict) and f.get("name")
                }
                and (sn2 + "_id") in {
                    f.get("name") for f in (e3.get("fields") or [])
                    if isinstance(f, dict) and f.get("name")
                }
                for e3 in ents.values()
                if e3 is not e2
            )
            if not (is_child or is_ref or has_junction):
                continue
            referenced = any(
                _entity_token(p, ents) == cls2 for p in params
            ) or any(
                t in (sn2, sn2 + "s", cls2.lower(), cls2.lower() + "s")
                for t in re.split(r"_+", name)
            )
            if not referenced:
                continue
            rank = 2 if any(_entity_token(p, ents) == cls2 for p in params) else 1
            if best is None or rank > best[0]:
                best = (rank, cls2, sn2)
        if best:
            other_cls, o_snake = best[1], best[2]
        if other_cls:
            o_ent = ents[other_cls]
            o_tbl = _entity_table_name(o_ent)
            o_fields = {
                f.get("name"): f for f in (o_ent.get("fields") or [])
                if isinstance(f, dict) and f.get("name")
            }
            child_fk = ent_snake + "_id"
            ref_fk = o_snake + "_id"
            junction = None
            for cls3, e3 in ents.items():
                if cls3 in (model, other_cls):
                    continue
                f3 = {f.get("name") for f in (e3.get("fields") or [])
                      if isinstance(f, dict) and f.get("name")}
                if child_fk in f3 and ref_fk in f3:
                    junction = (cls3, e3, _entity_table_name(e3))
                    break
            fk_param = next((p for p in params if p in (child_fk, ref_fk)), None)
            name_param = next((
                p for p in params if _entity_token(p, ents) == other_cls
            ), None)

            # ---- 8.12a child direction (owner repo -> child table) ----------
            if child_fk in o_fields and fk_param is not None:
                page_num = next((p for p in params if page_roles.get(p) == "num"), None)
                page_size = next((p for p in params if page_roles.get(p) == "size"), None)
                others = [p for p in params if p != fk_param and p not in page_roles]
                if page_num and page_size and not others:
                    cmodel = _camel(other_cls)
                    lines = [
                        "        with self.db.connect() as conn:",
                        "            offset = (%s - 1) * %s" % (page_num, page_size),
                        "            rows = conn.execute(",
                        '                "SELECT * FROM %s WHERE %s = ? ORDER BY id LIMIT ? OFFSET ?",'
                        % (o_tbl, child_fk),
                        "                %s" % _tup([fk_param, page_size, "offset"]),
                        "            ).fetchall()",
                    ]
                    if "dict" in ret_l:
                        lines.append("            return {'items': [%s(**dict(r)) for r in rows]}" % cmodel)
                    else:
                        lines.append("            return [%s(**dict(r)) for r in rows]" % cmodel)
                    return lines

            # ---- 8.12b owner-ref JOIN (owner -> other via owner FK) ---------
            if ref_fk in fields and name_param is not None:
                starts = [p for p in params if re.match(r"^(start|from|begin|min)", p) or p.endswith("_start")]
                ends = [p for p in params if re.match(r"^(end|to|max)", p) or p.endswith("_end")]
                if starts and ends and date_cols:
                    dc = date_cols[0]
                    conds = ["o.name = ?", "r.%s >= ?" % dc, "r.%s <= ?" % dc]
                    binds = [name_param, starts[0], ends[0]]
                    return [
                        "        with self.db.connect() as conn:",
                        "            rows = conn.execute(",
                        '                "SELECT r.* FROM %s r JOIN %s o ON r.%s = o.id WHERE %s",'
                        % (table, o_tbl, ref_fk, " AND ".join(conds)),
                        "                %s" % _tup(binds),
                        "            ).fetchall()",
                        "            return [%s(**dict(r)) for r in rows]" % model,
                    ]
                # Cross-entity equality filter (no date bounds): the method
                # filters owner rows by a column of the OTHER entity, e.g.
                # get_orders_with_customer_name_filter -> o.name. The filter
                # column is the <entity>_<col> suffix of the name param
                # (customer_name -> name on Customer), else the other
                # entity's unique str field. SELECT r.* keeps the row shape
                # on the OWNER model so the repo-body guard accepts it.
                # A filter on the OWNER's own FK column (the param IS
                # ``<other>_id``) needs no JOIN, and it must be CONDITIONAL:
                # the caller may omit an optional filter, and a hard
                # ``WHERE o.id = ?`` bound to NULL matches no row at all —
                # library's ``library book list`` (both options optional)
                # listed nothing. Remaining params resolve against the
                # owner's own columns (``available_only`` ->
                # ``available_copies > 0``).
                if name_param == ref_fk:
                    own = _own_filter_specs(
                        [p for p in params if p != name_param]
                    )
                    if own is not None:
                        lines = [
                            "        with self.db.connect() as conn:",
                            '            query = "SELECT * FROM %s WHERE 1=1"'
                            % table,
                            "            binds = []",
                            "            if %s is not None:" % name_param,
                            "                query += ' AND %s = ?'" % ref_fk,
                            "                binds.append(%s)" % name_param,
                        ]
                        for p, (col, op) in own:
                            if op == "gt_zero":
                                lines += [
                                    "            if %s:" % p,
                                    "                query += ' AND %s > 0'"
                                    % col,
                                ]
                            elif op == "eq_true":
                                lines += [
                                    "            if %s:" % p,
                                    "                query += ' AND %s = 1'"
                                    % col,
                                ]
                            else:
                                lines += [
                                    "            if %s is not None:" % p,
                                    "                query += ' AND %s = ?'"
                                    % col,
                                    "                binds.append(%s)" % p,
                                ]
                        lines += [
                            '            rows = conn.execute('
                            'query + " ORDER BY id", binds).fetchall()',
                            "            return [%s(**dict(r)) for r in rows]"
                            % model,
                        ]
                        return lines

                prefix = o_snake + "_"
                filt_col = None
                if name_param.startswith(prefix):
                    cand = name_param[len(prefix):]
                    if cand in o_fields:
                        filt_col = cand
                if filt_col is None:
                    str_cols_other = [
                        n for n, f in o_fields.items()
                        if f.get("type") == "str"
                    ]
                    if len(str_cols_other) == 1:
                        filt_col = str_cols_other[0]
                if filt_col is not None:
                    return [
                        "        with self.db.connect() as conn:",
                        "            rows = conn.execute(",
                        '                "SELECT r.* FROM %s r JOIN %s o'
                        ' ON r.%s = o.id WHERE o.%s = ?",'
                        % (table, o_tbl, ref_fk, filt_col),
                        "                %s" % _tup([name_param]),
                        "            ).fetchall()",
                        "            return [%s(**dict(r)) for r in rows]"
                        % model,
                    ]

            # ---- 8.12c many-to-many junction JOIN --------------------------
            if junction is not None and name_param is not None:
                j_cls, j_ent, j_tbl = junction
                conds = ["o.name = ?"]
                binds = [name_param]
                rest = [p for p in params if p != name_param and p not in page_roles]
                ok = True
                for p in rest:
                    if p in fields:
                        conds.append("r.%s = ?" % p)
                        binds.append(p)
                        continue
                    matched = False
                    for suf in ("_contains", "_prefix", "_pattern", "_substring"):
                        if p.endswith(suf) and p[: -len(suf)] in fields:
                            conds.append("r.%s LIKE ?" % p[: -len(suf)])
                            binds.append('"%%" + %s + "%%"' % p)
                            matched = True
                            break
                    if matched:
                        continue
                    ok = False
                    break
                if ok:
                    return [
                        "        with self.db.connect() as conn:",
                        "            rows = conn.execute(",
                        '                "SELECT r.* FROM %s r JOIN %s j ON r.id = j.%s_id JOIN %s o ON j.%s_id = o.id WHERE %s",'
                        % (table, j_tbl, ent_snake, o_tbl, o_snake, " AND ".join(conds)),
                        "                %s" % _tup(binds),
                        "            ).fetchall()",
                        "            return [%s(**dict(r)) for r in rows]" % model,
                    ]

    # ---- 8.12d zero-param dict[int] aggregate over a JOINed entity name ----
    # Repo custom like aggregate_stock_value_by_category() -> dict[str, int]:
    # the owner entity has an FK to another designed entity, the method takes
    # no params and returns a dict whose value is int/float, and its name ends
    # with _by_<fk_base>. Emit
    #   SELECT o.<label> AS k, SUM(<value_expr>) AS v
    #   FROM <owner> e JOIN <other> o ON e.<fk> = o.id GROUP BY o.<label>
    # Deterministic from the FK + entity schema + zero-param dict shape;
    # <value_expr> = the unique numeric column, or the product of the two
    # numeric columns when grouping across a join (price x qty). This is the
    # inter-file counterpart of the intra-file GROUP BY sum recipes above.
    if entities_by_class and not params and "dict" in ret_l:
        vm = re.search(
            r"dict\s*\[\s*[^,]+,\s*([^\]]+)\]", ret, re.IGNORECASE
        )
        val_type = (vm.group(1).strip().lower() if vm else "")
        if val_type in ("int", "integer", "float"):
            fk_matches = []
            for n in fields:
                if not n.endswith("_id") or n == "id":
                    continue
                base = n[: -len("_id")]
                cls = _camel(base)
                if cls in entities_by_class:
                    fk_matches.append((n, base, cls, entities_by_class[cls]))
            for fk, base, cls, o_ent in fk_matches:
                if not re.search(r"_by_%s$" % re.escape(base), name):
                    continue
                o_tbl = _entity_table_name(o_ent)
                o_fields = {
                    f.get("name"): f
                    for f in (o_ent.get("fields") or [])
                    if isinstance(f, dict) and f.get("name")
                }
                label = (
                    "name" if "name" in o_fields else next(
                        (n for n in o_fields if n != "id"), None
                    )
                )
                if label is None:
                    continue
                expr = None
                if len(num_cols) == 1:
                    expr = "e.%s" % num_cols[0]
                elif len(num_cols) == 2:
                    expr = "e.%s * e.%s" % (num_cols[0], num_cols[1])
                if expr is None:
                    continue
                cast = "float" if val_type == "float" else "int"
                return [
                    "        with self.db.connect() as conn:",
                    "            rows = conn.execute(",
                    '                "SELECT o.%s AS k, SUM(%s) AS v'
                    ' FROM %s e JOIN %s o ON e.%s = o.id'
                    ' GROUP BY o.%s",'
                    % (label, expr, table, o_tbl, fk, label),
                    "            ).fetchall()",
                    '            return {r["k"]: %s(r["v"] or 0)'
                    ' for r in rows}' % cast,
                ]

    # ---- 8.11 unsatisfiable discriminator -> honest empty set ---------------
    # A required param matches no designed field/entity/FK and there is no
    # cross-entity/aggregate resolution path: no row can ever satisfy it, so
    # [] is the truthful result. Params that name another entity (tag_name ->
    # Tag), are a child FK (customer_id), or are an aggregate boundary
    # (min_total_value / threshold) are NOT honest-empty — they fall through
    # to the LLM fill, which can build the JOIN/aggregate.
    if is_list_model and params:
        classes = set((entities_by_class or {}).keys())
        any_cross = any(
            _entity_token(p, entities_by_class) is not None
            or _is_aggregate_bound(p)
            or _param_is_child_fk(p, ent_snake, entities_by_class)
            or _param_is_other_entity_field(p, model, entities_by_class)
            for p in params
        )
        if any_cross:
            return None  # fall through to the LLM fill
        unresolved = [
            p for p in params
            if p not in lfmap and p not in page_roles
            and not _feas_token_resolves(p, fields, classes)
        ]
        if unresolved:
            return ["        return []"]

    # ---- 9. child-count joins (tuple[X, int] / dict[..., int]) --------------
    ents = entities_by_class or {}
    children = []
    for cls_o, e_o in ents.items():
        if cls_o == model:
            continue
        fks = [
            f.get("name")
            for f in (e_o.get("fields") or [])
            if isinstance(f, dict)
            and (f.get("name") or "").endswith("_id")
            and _camel((f.get("name"))[:-3]) == model
        ]
        if len(fks) == 1:
            children.append((cls_o, e_o, fks[0]))
    if len(children) == 1 and not params:
        c_cls, c_ent, fk = children[0]
        c_tbl = _entity_table_name(c_ent)
        c_model = _camel(c_cls)
        if "tuple" in ret_l and model in ret and "int" in ret_l:
            allowed = "{%s}" % ", ".join(
                sorted(set(fields) | {"id"})
            )
            return [
                "        with self.db.connect() as conn:",
                "            rows = conn.execute(",
                '                "SELECT p.*, COUNT(*) AS n FROM %s p'
                ' JOIN %s c ON c.%s = p.id'
                ' GROUP BY p.id ORDER BY n DESC LIMIT 5"' % (table, c_tbl, fk),
                "            ).fetchall()",
                "            return [",
                "                (%s({k: v for k, v in dict(r).items()"
                " if k in %s}), int(r[\"n\"]))" % (model, allowed),
                "                for r in rows",
                "            ]",
            ]
        if ret_l.startswith(("dict", "Dict")) and "int" in ret_l:
            return [
                "        with self.db.connect() as conn:",
                "            rows = conn.execute(",
                '                "SELECT %s AS k, COUNT(*) AS n FROM %s'
                ' GROUP BY %s ORDER BY n DESC"' % (fk, c_tbl, fk),
                "            ).fetchall()",
                '            return {r["k"]: int(r["n"]) for r in rows}',
            ]

    # ---- 10. joined pair lookup: dict[<This>, <Other>] ----------------------
    jm = re.match(
        r"[Dd]ict\[\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*\]$", ret
    )
    if jm and jm.group(1) == model and entities_by_class:
        o_cls = jm.group(2)
        o_ent = entities_by_class.get(o_cls)
        fks = [
            f.get("name")
            for f in (ent.get("fields") or [])
            if isinstance(f, dict)
            and (f.get("name") or "").endswith("_id")
            and _camel((f.get("name"))[:-3]) == o_cls
        ]
        if o_ent and len(fks) == 1:
            fk = fks[0]
            o_tbl = _entity_table_name(o_ent)
            o_model = _camel(o_cls)
            ours = "{%s}" % ", ".join(sorted(set(fields) | {"id"}))
            theirs = "{%s}" % ", ".join(
                sorted(
                    {f.get("name") for f in (o_ent.get("fields") or [])
                     if isinstance(f, dict) and f.get("name")}
                    | {"id"}
                )
            )
            return [
                "        with self.db.connect() as conn:",
                '            rows = conn.execute("SELECT * FROM %s").fetchall()'
                % table,
                "            out = {}",
                "            for r in rows:",
                "                obj = %s({k: v for k, v in dict(r).items()"
                " if k in %s})" % (model, ours),
                "                rel = conn.execute(",
                '                    "SELECT * FROM %s WHERE id = ?", (%s(obj).%s,)'
                % (o_tbl, "", fk),
                "                ).fetchone()",
                "                if rel:",
                "                    out[obj] = %s({k: v for k, v in"
                " dict(rel).items() if k in %s})" % (o_model, theirs),
                "            return out",
            ]

    return None


RECIPES = [Recipe("repo_method_body", 1, _repo_method_body)]
