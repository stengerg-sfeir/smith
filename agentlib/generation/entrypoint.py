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


def _package_entry_name(tree):
    """Name of the callable a package's ``__main__.py`` should invoke.

    The click command/group a module owns is what a user runs; otherwise a
    top-level ``main``. None when the module owns neither, so a package of
    plain helpers is left alone.
    """
    name = _click_command_name(tree)
    if name is not None:
        return name
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return "main"
    return None


def _package_main_source(dotted, entry):
    """Source of a package launcher running ``<dotted>.<entry>``.

    ``python -m <pkg>`` executes ``<pkg>/__main__.py``; without it the command
    fails with "No module named <pkg>.__main__" even though the package's
    ``__init__.py`` already defines ``main`` (prompt 01). The launcher uses an
    ABSOLUTE import of the package, which is what ``python -m`` resolves.
    """
    return (
        '"""Package entry point so `python -m %s` runs the application."""\n\n'
        "from %s import %s\n\n"
        'if __name__ == "__main__":\n'
        "    %s()\n" % (dotted, dotted, entry, entry)
    )


def _add_package_mains(files, added):
    """Emit ``<pkg>/__main__.py`` for every top-level package that lacks one.

    A runnable package whose only entry is ``main()`` in ``__init__.py``
    cannot be started as ``python -m <pkg>`` without a ``__main__.py``. Only
    a package that owns a click command or a ``main`` function gets one, so a
    package of plain modules is untouched. Returns ``(files, added)``.
    """
    for path in sorted(list(files)):
        if not path.endswith("/__init__.py"):
            continue
        pkg_dir = path[: -len("/__init__.py")]
        dotted = pkg_dir.replace("/", ".")
        if not dotted or not all(p.isidentifier() for p in dotted.split(".")):
            continue
        main_path = pkg_dir + "/__main__.py"
        if main_path in files:
            continue
        try:
            tree = ast.parse(files[path])
        except SyntaxError:
            continue
        entry = _package_entry_name(tree)
        if entry is None:
            continue
        files[main_path] = _package_main_source(dotted, entry)
        added += 1
    return files, added


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
    result, added = _add_package_mains(result, added)
    return result, added
