"""Bind exactly the values the SQL clause was built from (prompt 35).

Prompt 35 asks for "a bulk update operation that changes the stock quantity of
multiple products. The entire bulk update must succeed or fail as a single
transaction." The shipped repository built the SET clause conditionally and
then bound EVERY parameter at once:

    updates = []
    if stock_quantity is not None:
        updates.append('stock_quantity = ?')
    ...
    query += ', '.join(updates)
    query += ' WHERE id IN (' + ','.join(['?'] * len(product_ids)) + ')'
    conn.execute(query, list(product_ids) + [name, description, category,
                                             price, stock_quantity, is_active])

With one column supplied the statement holds two markers and six values, so
EVERY bulk update died on ``sqlite3.ProgrammingError: Incorrect number of
bindings supplied`` — the operation could not run at all.

The law: the clause list and the value list are built by the SAME conditions.
Each ``<list>.append('<column> = ?')`` guarded by ``if <param> is not None``
also appends ``<param>`` to a values list, and the ``execute`` call binds that
list. The SQL, the conditions and the parameters then agree by construction.
"""

import ast
import re

_CLAUSE_RE = re.compile(r"^\s*'?\s*\w+\s*=\s*\?")
_INSERT_HINT = ("execute", "executemany")


def _single_line(node):
    return node.lineno == getattr(node, "end_lineno", node.lineno)


def _append_target(node):
    """``(list name, clause text)`` for ``X.append('<col> = ?')``, else None."""
    if not isinstance(node, ast.Call):
        return None, None
    function = node.func
    if not (isinstance(function, ast.Attribute) and function.attr == "append"):
        return None, None
    if not isinstance(function.value, ast.Name) or not node.args:
        return None, None
    first = node.args[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None, None
    if not _CLAUSE_RE.match("'%s'" % first.value.strip()):
        return None, None
    return function.value.id, first.value


def _tested_name(test):
    """``param`` for ``if param is not None:``, else None."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], ast.IsNot):
        return None
    if not (isinstance(test.left, ast.Name) and len(test.comparators) == 1):
        return None
    right = test.comparators[0]
    if not (isinstance(right, ast.Constant) and right.value is None):
        return None
    return test.left.id


def _init_line(tree, name):
    """The line of ``name = []``, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.lineno
    return None


def _execute_param_span(tree):
    """The single-line span of the parameter argument of an ``execute`` call."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        function = node.func
        name = getattr(function, "attr", None) or getattr(function, "id", None)
        if name not in _INSERT_HINT:
            continue
        params = node.args[1]
        if not _single_line(params):
            continue
        return (
            params.lineno, params.col_offset,
            params.lineno, params.end_col_offset,
        )
    return None


def _binding_plan(params, source):
    """The span of the parameter LIST inside an ``execute`` argument.

    The shipped argument is ``list(product_ids) + [name, ...] if updates else
    []``: the list holds the SET clause's parameters, the other addend supplies
    the WHERE clause's ids. The SET clause READS BEFORE the WHERE clause, so the
    repaired argument is ``values + <ids>`` — the ids kept, and in the order the
    statement binds them.
    """
    node = params.body if isinstance(params, ast.IfExp) else params
    span = (params.lineno, params.col_offset or 0, params.end_col_offset or 0)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        for side, other in ((node.right, node.left), (node.left, node.right)):
            if not isinstance(side, ast.List) or isinstance(other, ast.List):
                continue
            other_text = ast.get_source_segment(source, other)
            if not other_text:
                return None
            return span, "values + %s" % other_text
        return None
    if isinstance(node, ast.List):
        return span, "values"
    return None


def _plan_function(node, lines):
    """``(insertions, span, replacement)`` for one function, or three ``None``.

    Everything is scoped to THIS function's statements: the clause list, the
    guarded appends, and the ``execute`` call that binds them. A module-wide
    search would edit the first ``execute`` of the file — a different method,
    where the collected values do not exist — and leave the real call alone.
    """
    clause_of = {}
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            target, _clause = _append_target(sub)
            if target:
                clause_of[sub.lineno] = target
    if not clause_of:
        return [], None, None
    names = sorted(set(clause_of.values()))
    init_lines = []
    for name in names:
        line = _init_line(node, name)
        if line is None:
            return [], None, None
        init_lines.append(line)
    insertions = []
    for parent in ast.walk(node):
        if not isinstance(parent, ast.If):
            continue
        hits = [
            sub.lineno for sub in ast.walk(parent)
            if isinstance(sub, ast.Call) and sub.lineno in clause_of
        ]
        if not hits:
            continue
        parameter = _tested_name(parent.test)
        if parameter is None:
            continue
        # The LAST clause append of the block carries the value, so a block
        # that appends two clauses never doubles a parameter.
        insertions.append((max(hits), parameter))
    if not insertions:
        return [], None, None
    source = "\n".join(lines)
    span = None
    replacement = None
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call) or len(sub.args) < 2:
            continue
        function = sub.func
        name = getattr(function, "attr", None) or getattr(function, "id", None)
        if name not in _INSERT_HINT:
            continue
        plan = _binding_plan(sub.args[1], source)
        if plan is not None:
            span, replacement = plan
    if span is None or replacement is None:
        return [], None, None
    for line in init_lines:
        insertions.append((line, None))
    return insertions, span, replacement


def fix_bulk_binding(source):
    """``(source, changed)`` binding the values the clause conditions choose."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, 0
    lines = source.split("\n")
    values_name = "values"
    insertions = []
    replacements = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        planned, span, replacement = _plan_function(node, lines)
        if not planned or span is None or replacement is None:
            continue
        for line, parameter in planned:
            if line < 1 or line > len(lines):
                return source, 0
            raw = lines[line - 1]
            indent = raw[: len(raw) - len(raw.lstrip())]
            text = (
                "%s%s = []" % (indent, values_name)
                if parameter is None
                else "%s%s.append(%s)" % (indent, values_name, parameter)
            )
            insertions.append((line, text))
        replacements.append((span, replacement))
    if not insertions or not replacements:
        return source, 0
    for line_index, text in sorted(insertions, reverse=True):
        lines.insert(line_index, text)
    # Every insertion ABOVE a span shifts it down by one; recount on the
    # spliced text before touching it.
    for (start_line, start_col, end_col), replacement in replacements:
        shifted = start_line + sum(
            1 for index, _text in insertions if index < start_line
        )
        if shifted < 1 or shifted > len(lines):
            return source, 0
        target_line = lines[shifted - 1]
        if end_col > len(target_line):
            return source, 0
        lines[shifted - 1] = (
            target_line[:start_col] + replacement + target_line[end_col:]
        )
    candidate = "\n".join(lines)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return source, 0
    return candidate, len(insertions) + len(replacements)


def apply_bulk_binding_guards(files, repo_files):
    """Fix every repository whose SET clause and bindings disagree.

    ``files`` is ``{path: source}``. Returns ``(files, notes)``.
    """
    notes = []
    for path in repo_files or []:
        source = files.get(path)
        if not source:
            continue
        if "conn.execute" not in source and "cursor.execute" not in source:
            continue
        candidate, changed = fix_bulk_binding(source)
        if changed:
            files[path] = candidate
            notes.append("%s: %d binding(s) realigned" % (path, changed))
    return files, notes
