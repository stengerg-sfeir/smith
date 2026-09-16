"""Deterministic annotation floor for the script (single-pass) path.

A spec that asks for "type hints" must get them even when the small model
omits them on a trivial file — the observed ``def main():`` with no
annotation at all, while ``SYSTEM_CONTEXT`` only ever *states* the rule and
nothing verified it.

This module adds the ONE annotation that is derivable without guessing the
author's intent: a function with no return annotation whose body neither
returns a value nor yields gets ``-> None``. Parameter types are NOT
recoverable from the source, so they are left to the model's prompt rule —
inventing them would be worse than leaving the parameter bare.
"""

import ast


def _body_outcome(node):
    """What the function body can produce: 'value', 'yield' or 'none'.

    Nested function scopes do not count — a ``return`` inside an inner def
    belongs to that def, not to the one being annotated. A generator
    (``yield`` anywhere) must never be labelled ``-> None``.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        for child in ast.iter_child_nodes(current):
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            ):
                continue
            if isinstance(child, (ast.Yield, ast.YieldFrom)):
                return "yield"
            if isinstance(child, ast.Return) and child.value is not None:
                return "value"
            stack.append(child)
    return "none"


def _single_line_signature(text, node):
    """True when `node`'s signature is confined to one comment-free line.

    A multi-line signature is skipped rather than guessed at — locating its
    closing colon reliably needs the parser, and the prompt rule still
    covers the model's own authoring.
    """
    lines = text.split("\n")
    if node.lineno < 1 or node.lineno > len(lines):
        return False
    if not node.body or node.body[0].lineno != node.lineno + 1:
        return False
    line = lines[node.lineno - 1]
    if "#" in line or '"""' in line or "'''" in line:
        return False
    return line.rstrip().endswith(":")


def _colon_offset(text, node):
    """Character offset of the colon closing `node`'s single-line signature."""
    lines = text.split("\n")
    before = sum(len(part) + 1 for part in lines[: node.lineno - 1])
    return before + len(lines[node.lineno - 1].rstrip()) - 1


def _unannotated_none_returners(tree, text):
    """Offsets of the signatures that need `-> None`."""
    offsets = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.returns is not None:
            continue
        if _body_outcome(node) != "none":
            continue
        if not _single_line_signature(text, node):
            continue
        offsets.append(_colon_offset(text, node))
    return offsets


def add_missing_none_returns(files):
    """Annotate ``-> None`` on every unannotated nothing-returning function.

    ``files`` is ``{path: source}``. Returns ``(files, added)`` where
    ``added`` counts the annotations inserted across the project. A file
    whose edit would not re-parse is left byte-for-byte untouched, so a
    mis-located colon can never ship.
    """
    added = 0
    result = {}
    for path, text in files.items():
        if not path.endswith(".py"):
            result[path] = text
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            result[path] = text
            continue
        offsets = _unannotated_none_returners(tree, text)
        if not offsets:
            result[path] = text
            continue
        edited = text
        for offset in sorted(offsets, reverse=True):
            edited = edited[:offset] + " -> None" + edited[offset:]
        try:
            ast.parse(edited)
        except SyntaxError:
            result[path] = text
            continue
        added += len(offsets)
        result[path] = edited
    return result, added
