"""Deterministic entry-point guarantee for generated command modules.

A script whose file is not named ``cli.py`` was shipping with NO
``if __name__ == "__main__":`` block at all: the model writes
``@click.command() def main(): ...`` and stops. ``python csv_to_json.py
data.csv`` then exits 0 having done nothing — no output, no file written, a
missing input "accepted" — which is exactly the observed cli_tool failure
(and it silently disabled the whole project for the facade suite).

The rule is narrow on purpose: a module gets a guard only when it owns a
top-level click command/group (the thing a user is meant to run), or when it
is ``main.py``. Everything else is left alone.
"""

import ast


def _click_command_name(tree):
    """Name of the module's top-level click command/group, or None."""
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Attribute) and target.attr in (
                "command", "group"
            ):
                return node.name
            if isinstance(target, ast.Name) and target.id in ("command", "group"):
                return node.name
    return None


def _guard(name):
    return '\n\nif __name__ == "__main__":\n    %s()\n' % name


def ensure_entry_point(files):
    """Append a ``__main__`` guard to every runnable module that lacks one.

    ``files`` is ``{path: source}``. Returns ``(files, added)`` where
    ``added`` counts the guards inserted. A module that already has an
    ``__main__`` block, does not parse, or owns no click command is left
    byte-for-byte untouched.
    """
    added = 0
    result = {}
    for path, text in files.items():
        if not path.endswith(".py") or "if __name__" in text:
            result[path] = text
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            result[path] = text
            continue
        name = _click_command_name(tree)
        if name is None and path.rsplit("/", 1)[-1] == "main.py":
            name = "main"
        if name is None:
            result[path] = text
            continue
        patched = text.rstrip() + _guard(name)
        try:
            ast.parse(patched)
        except SyntaxError:
            result[path] = text
            continue
        added += 1
        result[path] = patched
    return result, added
