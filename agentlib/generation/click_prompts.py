"""Deterministic removal of interactive prompts on optional click options.

Prompt 03 asks for a todo tool where "Users can add tasks, list tasks, mark a
task as completed and delete a task". The single-pass output declared

    @click.option('--add', '-a', prompt='Task to add', help=...)
    @click.option('--list', '-l', is_flag=True, help=...)

``--add`` is optional (nothing marks it required), yet ``prompt='…'`` tells
click to ASK for a value whenever the option is omitted — so plain
``todo_app.py --list`` printed ``Task to add:`` and aborted. A prompt belongs
to a REQUIRED value: it is click's way of filling one in a terminal, and an
optional option that carries one turns every other command of the tool into an
interactive question.

The repair deletes the ``prompt=`` keyword from an option that is not declared
``required=True``. It declines a call whose arguments are spread over several
lines (the splice is textual and must stay exact), and never touches an option
that IS required, where the prompt is the intended behaviour.
"""

import ast

from agentlib.generation.cli_wiring import _apply_edits, _call_kind


def _is_required(call):
    """True when the click option declares ``required=True``."""
    for keyword in call.keywords:
        if keyword.arg != "required":
            continue
        value = keyword.value
        if isinstance(value, ast.Constant) and value.value is True:
            return True
    return False


def _prompt_keyword(call):
    """The ``prompt=`` keyword of a click option, or None."""
    for keyword in call.keywords:
        if keyword.arg == "prompt":
            return keyword
    return None


def _removal_edit(call, keyword):
    """The single-line edit that deletes ``keyword=…`` (with its comma).

    Everything must sit on ONE line: the splice is a character range, so a
    multi-line call declines rather than risk cutting a line in half.
    """
    ordered = list(call.args) + list(call.keywords)
    ordered.sort(key=lambda node: (node.lineno, node.col_offset))
    positions = []
    for node in ordered:
        line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", line)
        positions.append((line, node.col_offset, end_line, node.end_col_offset))
    try:
        index = ordered.index(keyword)
    except ValueError:
        return None
    line, col, end_line, end_col = positions[index]
    if line != end_line:
        return None
    for entry in positions:
        if entry[0] != line or entry[2] != line:
            return None
    if index + 1 < len(positions):
        # Delete up to the next item: this drops the keyword AND its comma.
        return (line, col, line, positions[index + 1][1], "")
    if index > 0:
        # Last item: delete back from the previous item's end.
        return (line, positions[index - 1][3], line, end_col, "")
    return None


def drop_unneeded_prompts(files):
    """Remove ``prompt=`` from click options that are not required.

    ``files`` is ``{path: source}``. Returns ``(files, fixed)`` where ``fixed``
    counts the files rewritten. A file without click, without such an option,
    or that does not parse is returned unchanged.
    """
    fixed = 0
    result = {}
    for path, text in files.items():
        if not path.endswith(".py") or "prompt=" not in text or "click" not in text:
            result[path] = text
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            result[path] = text
            continue
        edits = []
        for node in ast.walk(tree):
            if _call_kind(node) != "option" or _is_required(node):
                continue
            keyword = _prompt_keyword(node)
            if keyword is None:
                continue
            edit = _removal_edit(node, keyword)
            if edit is not None:
                edits.append(edit)
        if not edits:
            result[path] = text
            continue
        spliced = _apply_edits(text.split("\n"), edits)
        if spliced is None:
            result[path] = text
            continue
        candidate = "\n".join(spliced)
        try:
            ast.parse(candidate)
        except SyntaxError:
            result[path] = text
            continue
        result[path] = candidate
        fixed += 1
    return result, fixed
