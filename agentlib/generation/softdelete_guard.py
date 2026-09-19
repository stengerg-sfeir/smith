"""Impose the soft-delete rule on a rendered repository (prompt 14).

The repository is the place the rule lives: the service forwards
``delete_project(id)`` to ``repo.delete(id)``, and the listing that must hide
the row is ``repo.list(...)``/``get_all()``. Three textual edits, all driven by
the design's OWN column (``deleted_at``):

1. ``DELETE FROM <table> WHERE id = ?`` becomes
   ``UPDATE <table> SET <col> = datetime('now') WHERE id = ?`` — the row stays
   in the database, stamped.
2. Each listing SELECT gains ``<col> IS NULL``, so the row stops being
   returned. The listing is recognised by its SHAPE (``SELECT * FROM <table>``
   that orders or has no restriction at all); a by-id lookup is not a listing
   and is left alone.
3. The design's own ``if <col> is not None:`` filter is deleted: with (2) in
   place it could only ever contradict the rule.

The edits are splices on string literals and whole lines, so the file keeps its
comments, spacing and structure; a repository that is already soft is returned
byte-for-byte.
"""

import ast
import re

from agentlib.generation.cli_wiring import _apply_edits

_TABLE_RE = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)")


def _repo_entity_stem(path):
    """``project_repository.py`` -> ``project``."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    for suffix in (".py",):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    for suffix in ("_repository", "_repo"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _strings(tree):
    """Every string constant of the module, with its span."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node)
    return found


def _is_listing(sql, table):
    """True for a listing SELECT over ``table`` (not a by-id lookup)."""
    if not sql.upper().startswith("SELECT"):
        return False
    if not re.search(r"\bFROM\s+%s\b" % re.escape(table), sql):
        return False
    upper = sql.upper()
    if "ORDER BY" in upper or "WHERE 1=1" in upper:
        return True
    return " WHERE " not in upper


def _filtered(sql, column):
    """``sql`` restricted to rows whose ``column`` is unset."""
    if "WHERE 1=1" in sql:
        return sql.replace("WHERE 1=1", "WHERE %s IS NULL" % column)
    if " WHERE " in sql:
        return sql.replace(" WHERE ", " WHERE %s IS NULL AND " % column, 1)
    for tail in (" ORDER BY", " GROUP BY", " LIMIT"):
        index = sql.upper().find(tail)
        if index != -1:
            return sql[:index] + " WHERE %s IS NULL" % column + sql[index:]
    return sql + " WHERE %s IS NULL" % column


def _soft_delete_statement(sql, table, column):
    """``DELETE FROM <table> WHERE id = ?`` -> an UPDATE that stamps the row."""
    if not sql.upper().startswith("DELETE"):
        return None
    return "UPDATE %s SET %s = datetime('now') WHERE id = ?" % (table, column)


def _drop_column_filter(source, column):
    """Delete the ``if <column> is not None:`` block, if the design has one.

    Only that exact comparison is removed (``is not None`` against the column
    itself): a neighbouring ``if`` that merely mentions the name is left alone.
    Returns ``(source, removed_blocks)``.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, 0
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if not isinstance(test.left, ast.Name) or test.left.id != column:
            continue
        if not any(isinstance(op, ast.IsNot) for op in test.ops):
            continue
        if not any(
            isinstance(c, ast.Constant) and c.value is None for c in test.comparators
        ):
            continue
        spans.append((node.lineno, node.end_lineno))
    if not spans:
        return source, 0
    lines = source.split("\n")
    for start, end in sorted(spans, reverse=True):
        del lines[start - 1:end]
    return "\n".join(lines), len(spans)


def apply_soft_delete_guard(repo_source, rule):
    """Make ``repo_source`` soft-delete. Returns ``(source, notes)``."""
    column = (rule or {}).get("column")
    if not column or not repo_source:
        return repo_source, []
    table_match = _TABLE_RE.search(repo_source)
    if not table_match:
        return repo_source, []
    table = table_match.group(1)

    source, removed = _drop_column_filter(repo_source, column)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return repo_source, []

    edits = []
    stamped = 0
    filtered = 0
    replace_value = None
    for node in _strings(tree):
        sql = node.value
        statement = _soft_delete_statement(sql, table, column)
        if statement is not None and statement != sql:
            replace_value = (node, statement)
            stamped += 1
            continue
        if _is_listing(sql, table) and column not in sql:
            filtered += 1
            edits.append(
                (node.lineno, node.col_offset + 1, node.end_lineno,
                 node.end_col_offset - 1, _filtered(sql, column))
            )
    if replace_value is not None:
        node, statement = replace_value
        edits.append(
            (node.lineno, node.col_offset + 1, node.end_lineno,
             node.end_col_offset - 1, statement)
        )
    if not edits:
        return repo_source, []
    spliced = _apply_edits(source.split("\n"), edits)
    if spliced is None:
        return repo_source, []
    candidate = "\n".join(spliced)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return repo_source, []
    notes = []
    if stamped:
        notes.append("soft delete stamps %s" % column)
    if filtered:
        notes.append("%d listing(s) hide deleted rows" % filtered)
    if removed:
        notes.append("dropped %d column filter(s)" % removed)
    return candidate, notes


def apply_soft_delete_guards(files, repo_files, rules):
    """Apply the rule to every repository whose entity declares one.

    ``files`` is ``{path: source}``; ``repo_files`` limits the sweep to the
    repositories of this design. Returns ``(files, notes)``.
    """
    all_notes = []
    for path in repo_files or []:
        source = files.get(path)
        if not source:
            continue
        stem = _repo_entity_stem(path)
        rule = None
        for cls, candidate in (rules or {}).items():
            if cls.lower() == stem.lower():
                rule = candidate
                break
        if rule is None:
            continue
        source, notes = apply_soft_delete_guard(source, rule)
        if notes:
            files[path] = source
            all_notes.append("%s: %s" % (path, "; ".join(notes)))
    return files, all_notes
