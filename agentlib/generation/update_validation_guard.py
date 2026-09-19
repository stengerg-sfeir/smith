"""Remove a CREATE-only validation from an update path (prompt 35).

Prompt 35 asks for "normal product CRUD operations and a bulk update operation
that changes the stock quantity of multiple products. The entire bulk update
must succeed or fail as a single transaction." The shipped bulk update carried
the CREATE recipe's required-field rule:

    def bulk_update_product(self, ids, name=None, ..., stock_quantity=None):
        required_fields = ['name', 'price']
        for field in required_fields:
            if ... and (name is None and field == 'name' or ...):
                raise ValidationError(f"Required field '{field}' is missing.")

so

    product bulk-update --ids 1 --stock-quantity 9

answered ``Error: Required field 'name' is missing.`` — it demanded the very
fields it was not updating. Updating means changing a SUBSET; a rule that
every field must be supplied belongs to creation, where the row is built whole.

The law deletes a raise whose message is the required-field rule when it lives
in a method that UPDATES — a method whose name carries ``update`` as one of its
tokens, which covers ``update_product`` and ``bulk_update_product`` alike —
together with the loop or condition that carries it and the list it iterates.
A create path keeps its rule untouched.
"""

import ast
import re

_REQUIRED_RE = re.compile(
    r"required field .{0,40}is missing|is required|must be provided",
    re.I,
)


def _required_raise(node):
    """The raise node inside ``node`` whose message states a required field."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Raise) or sub.exc is None:
            continue
        text = " ".join(
            part.value for part in ast.walk(sub.exc)
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
        if text and _REQUIRED_RE.search(text):
            return sub
    return None


def _assignment_lines(tree, name):
    """The line span of ``name = [...]`` inside the module, or None."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return (node.lineno, node.end_lineno)
    return None


def _span(node):
    return (node.lineno, node.end_lineno or node.lineno)


def drop_update_required_guards(source):
    """``(source, dropped)`` removing required-field rules from updates."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, 0
    lines = source.split("\n")
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "update" not in node.name.lower().split("_"):
            continue
        for sub in node.body:
            raise_node = _required_raise(sub)
            if raise_node is None:
                continue
            spans.append(_span(sub))
            if isinstance(sub, ast.For) and isinstance(sub.iter, ast.Name):
                carried = _assignment_lines(tree, sub.iter.id)
                if carried is not None:
                    spans.append(carried)
    if not spans:
        return source, 0
    unique = sorted(set(spans), reverse=True)
    for start, end in unique:
        if start < 1 or end > len(lines) or end < start:
            return source, 0
        del lines[start - 1:end]
    candidate = "\n".join(lines)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return source, 0
    return candidate, len(unique)


def apply_update_validation_guards(files, service_files):
    """Remove the create-only rule from every update method of the design.

    ``files`` is ``{path: source}``. Returns ``(files, notes)``.
    """
    notes = []
    for path in service_files or []:
        source = files.get(path)
        if not source:
            continue
        candidate, dropped = drop_update_required_guards(source)
        if dropped:
            files[path] = candidate
            notes.append("%s: %d create-only rule(s) removed" % (path, dropped))
    return files, notes
