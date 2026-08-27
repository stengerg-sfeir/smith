"""Repository SQL-schema contract: designed schema mapping, LLM prompt
context hint, and semantic validation of LLM repository fills.

Extracted from agent.py. The LLM never sees raw sibling SQL; instead it is
given ONLY the designed tables/columns, and every fill is validated against
that same schema so hallucinated relations (books_authors, budgets.amount,
...) are rejected at the schema gate instead of crashing at runtime.
"""
import ast
import re

from ..naming import _entity_table_name


def _repo_schema_from_entities(entities_by_class):
    """{table_name: set(columns)} from the DESIGNED entities (+ id), honouring
    declared irregular table names — the same mapping the deterministic DDL
    and repository renderers use."""
    schema = {}
    for cls, ent in entities_by_class.items():
        cols = {"id"}
        for f in ent.get("fields") or []:
            if isinstance(f, dict) and f.get("name"):
                cols.add(f["name"])
        schema[_entity_table_name(ent)] = cols
    return schema


def _repo_sql_context_hint(schema_ctx, stub_names):
    """Render the DESIGNED SQLite schema + stub-method list for the LLM
    repository fill prompt. Without this the model must guess table/column
    names from sibling CRUD SQL, so cross-table customs reference invented
    relations (books_authors, budgets.budget_amount, ...) and the schema gate
    reverts them to locked stubs."""
    lines = [
        "Fill ONLY these repository custom methods; keep every other method, "
        "signature, import, and class exact: %s." % ", ".join(stub_names),
        "Use ONLY the DESIGNED SQLite tables/columns below. SQLite dialect; "
        "parameter placeholders '?'. Never invent a table or column. A column "
        "ending in _id is a foreign key to the table of that name (minus id).",
        "Never import datetime/date/time. All date/datetime columns are "
        "ISO-8601 TEXT: compare them as plain strings (WHERE expense_date "
        "BETWEEN '2024-01-01' AND '2024-12-31') and derive year/month with "
        "substr(col,1,4)/substr(col,1,7).",
        "Open connections EXACTLY like the existing methods do: "
        "'with self.db.connect() as conn:' then fetch rows DIRECTLY on "
        "the result of conn.execute(...): 'rows = conn.execute(...).fetchall()' "
        "or 'row = conn.execute(...).fetchone()'. NEVER call conn.fetchall() "
        "or conn.fetchone() — conn is a sqlite3.Connection and has NO "
        "fetchall/fetchone; only the Cursor returned by conn.execute(...) does. "
        "The Database class has NO get_connection/get_db/connection methods — "
        "self.db.get_connection(...) does not exist.",
        "Each method reads ONLY its own table: 'SELECT * FROM <table> ...' "
        "then 'return [Model(**dict(r)) for r in rows]'. NEVER join other "
        "tables, NEVER select columns from them, NEVER pass extra keyword "
        "arguments to the model constructor (use ONLY its designed fields).",
        "",
        "TABLES:",
    ]
    for table in sorted(schema_ctx):
        cols = ", ".join(sorted(schema_ctx[table]))
        lines.append("  %s(%s)" % (table, cols))
    return "\n".join(lines)


_TABLE_REF_RE = re.compile(
    r"\b(?:from|join|into|update)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE
)
_ALIAS_DECL_RE = re.compile(
    r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:as\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)


def _check_sql_segment(segment, schema):
    """Schema violations inside ONE SQL statement segment.

    Narrow, false-positive-averse checks over the DESIGNED schema:
    - table names after FROM/JOIN/INTO/UPDATE must be designed;
    - INSERT column lists, UPDATE SET columns, and WHERE left-hand
      identifiers must be designed columns of their (resolved) table.
    Dynamic concat fragments carry no FROM of their own and are therefore
    never scoped — they are skipped, not guessed.
    """
    violations = []
    tables = {m.group(1).lower() for m in _TABLE_REF_RE.finditer(segment)}
    aliases = {
        m.group(2).lower(): m.group(1).lower()
        for m in _ALIAS_DECL_RE.finditer(segment)
        if m.group(1).lower() in schema
    }
    # Output aliases declared via "<expr> AS <name>" in this statement —
    # referencing them later (ORDER BY book_count) is legal, not a column.
    sql_aliases = {
        m.group(1).lower()
        for m in re.finditer(
            r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)",
            segment, re.IGNORECASE,
        )
    }
    unknown = sorted(t for t in tables if t not in schema)
    if unknown:
        violations.append(
            "references unknown table(s) %s (designed: %s)"
            % (", ".join(unknown), ", ".join(sorted(schema)))
        )

    def _resolve(ident):
        """(table, column) for a possibly aliased identifier; None when the
        table cannot be resolved (unresolvable => skipped, never rejected)."""
        if "." in ident:
            alias, col = ident.split(".", 1)
            tbl = aliases.get(alias.lower())
            return (tbl, col) if tbl else None
        known = [t for t in tables if t in schema]
        owners = [t for t in known if ident in schema[t]]
        if len(owners) == 1:
            return (owners[0], ident)
        if len(known) == 1 and ident.lower() not in ("true", "false", "null"):
            return (known[0], ident)
        return None

    def _flag(ident, label):
        """Flag `ident` when it cannot denote a real column of the DESIGNED
        schema: resolved to a table that lacks it, or unqualified and absent
        from EVERY referenced table (SQLite would raise OperationalError).
        Rowid pseudo-columns and AS aliases declared here are exempt."""
        resolved = _resolve(ident)
        if resolved:
            if resolved[1] not in schema[resolved[0]]:
                violations.append(
                    "%s uses unknown column %r (table %s)"
                    % (label, ident, resolved[0])
                )
            return
        if "." in ident:
            return  # unknown qualifier: cannot judge, skip
        low = ident.lower()
        if low in ("rowid", "oid", "_rowid_", "true", "false", "null"):
            return
        if low in sql_aliases:
            return
        if any(ident in schema[t] for t in tables if t in schema):
            return  # ambiguous but resolvable somewhere in scope
        violations.append("%s uses unknown column %r" % (label, ident))

    im = re.search(
        r"\binsert\s+into\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)",
        segment, re.IGNORECASE,
    )
    if im:
        tbl = im.group(1).lower()
        if tbl in schema:
            for raw in im.group(2).split(","):
                col = raw.strip().strip('"').strip("'").strip("`").strip()
                if col and col not in schema[tbl]:
                    violations.append(
                        "INSERT into %s uses unknown column %r" % (tbl, col)
                    )

    um = re.search(
        r"\bupdate\s+([A-Za-z_][A-Za-z0-9_]*)\s+set\s+(.*)",
        segment, re.IGNORECASE | re.DOTALL,
    )
    if um:
        tbl = um.group(1).lower()
        if tbl in schema:
            set_part = re.split(
                r"\bwhere\b", um.group(2), flags=re.IGNORECASE
            )[0]
            for cm in re.finditer(
                r"(?:^|,)\s*([A-Za-z_][A-Za-z0-9_.]*)\s*=", set_part
            ):
                resolved = _resolve(cm.group(1))
                if (
                    resolved and resolved[0] == tbl
                    and resolved[1] not in schema[tbl]
                ):
                    violations.append(
                        "UPDATE %s sets unknown column %r"
                        % (tbl, cm.group(1))
                    )

    wm = re.search(r"\bwhere\b(.*)", segment, re.IGNORECASE | re.DOTALL)
    if wm:
        tail = wm.group(1)
        for stop in ("group by", "order by", "limit", "having", "returning"):
            tail = re.split(r"\b%s\b" % stop, tail, flags=re.IGNORECASE)[0]
        for term in re.split(r"\band\b|\bor\b", tail, flags=re.IGNORECASE):
            tm = re.match(
                r"\s*\(?\s*([A-Za-z_][A-Za-z0-9_.]*)\s*"
                r"(?:=|>=|<=|<>|!=|>|<|\bbetween\b|\blike\b|\bin\b)",
                term, re.IGNORECASE,
            )
            if not tm:
                continue
            ident = tm.group(1)
            if ident.lower() in ("select", "exists", "case", "when"):
                continue
            _flag(ident, "WHERE clause")

    def _check_ident_list(text, label):
        """Validate bare column identifiers in a comma-separated clause
        (GROUP BY / ORDER BY). Functions, literals and expressions are
        skipped — only bare refs are checked."""
        for raw in text.split(","):
            ident = raw.strip().rstrip(";").strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", ident):
                continue
            _flag(ident, label)

    # JOIN conditions: both sides of every ON a.x = b.y must be designed
    for om in re.finditer(
        r"\bon\b\s+([A-Za-z_][A-Za-z0-9_.]*)\s*=\s*"
        r"([A-Za-z_][A-Za-z0-9_.]*)",
        segment, re.IGNORECASE,
    ):
        for ident in om.groups():
            _flag(ident, "JOIN condition")
    # GROUP BY / ORDER BY bare column refs
    gm = re.search(
        r"\bgroup\s+by\b(.*?)(?:\border\s+by\b|\blimit\b|\bhaving\b|$)",
        segment, re.IGNORECASE | re.DOTALL,
    )
    if gm:
        _check_ident_list(gm.group(1), "GROUP BY")
    om2 = re.search(
        r"\border\s+by\b(.*?)(?:\blimit\b|\bhaving\b|$)",
        segment, re.IGNORECASE | re.DOTALL,
    )
    if om2:
        _check_ident_list(om2.group(1), "ORDER BY")
    # Bare column refs in the SELECT list (functions/expressions skipped)
    sm = re.search(
        r"\bselect\s+(.*?)\s+\bfrom\b", segment, re.IGNORECASE | re.DOTALL
    )
    if sm:
        for raw in sm.group(1).split(","):
            m2 = re.fullmatch(
                r"(?:distinct\s+)?([A-Za-z_][A-Za-z0-9_.]*)",
                raw.strip(), re.IGNORECASE,
            )
            if not m2:
                continue
            ident = m2.group(1)
            if ident.lower() == "distinct":
                continue
            _flag(ident, "SELECT list")
    return violations


def _repo_fill_schema_violations(source, schema):
    """Schema-aware semantic validation of an LLM repository fill: every SQL
    statement literal in the filled source must reference only DESIGNED
    tables/columns. Catches fills written against hallucinated relations
    (e.g. books.author_id when the Book model defines no such field) that
    compile fine and crash only at runtime with OperationalError."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["output does not compile"]
    violations = []

    def _has_sql(text):
        return bool(
            re.search(r"\b(select|insert|update|delete)\b", text, re.IGNORECASE)
        )

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        sql = node.value
        if not _has_sql(sql):
            continue
        seen = set()
        for segment in sql.split(";"):
            if not _has_sql(segment):
                continue
            for v in _check_sql_segment(segment, schema):
                if v not in seen:
                    seen.add(v)
                    violations.append(v)
    return violations
