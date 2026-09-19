"""Synthesize the repository INTERFACE a specification demands (prompt 30).

Prompt 30 asks for a task application "using a repository pattern. The
application must have a repository interface, a SQLite implementation and a
service layer." The shipped tree had the SQLite implementation and the service
layer, and no interface at all:

    task_repository.py   class TaskRepository:      # the only repository
    task_service.py      class TaskService:         # depends on that class
    (nothing declaring what a task repository must provide)

so the deliverable the specification names FIRST — the interface — was missing.
The law derives the interface FROM the shipped implementation (method names and
signatures are copied, bodies become ``raise NotImplementedError``) and makes
that implementation inherit it: one abstraction, one implementation behind it,
which is what a repository pattern describes.

Deriving it from the implementation (rather than inventing methods) is what
keeps the concrete class instantiable: every abstract method is implemented by
construction.
"""

import ast


def _class_def(tree):
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return node
    return None


def _import_lines(source):
    """The module's top-level import lines, in order."""
    return [
        line for line in source.split("\n")
        if line.startswith(("import ", "from "))
        and "abc import" not in line
    ]


def _method_headers(node, source):
    """``[(name, header)]`` for the class's own public methods."""
    found = []
    for sub in node.body:
        if not isinstance(sub, ast.FunctionDef) or sub.name.startswith("_"):
            continue
        try:
            segment = ast.get_source_segment(source, sub)
        except (TypeError, ValueError):
            segment = None
        if not segment:
            continue
        found.append((sub.name, segment.split("\n")[0].rstrip()))
    return found


def concrete_class_name(repo_source):
    """The class the repository module declares, or None."""
    try:
        tree = ast.parse(repo_source)
    except SyntaxError:
        return None
    node = _class_def(tree)
    return node.name if node is not None else None


def render_repository_interface(repo_source, interface_name):
    """``(interface source, concrete class name)`` for a shipped repository."""
    try:
        tree = ast.parse(repo_source)
    except SyntaxError:
        return None, None
    node = _class_def(tree)
    if node is None:
        return None, None
    methods = _method_headers(node, repo_source)
    if not methods:
        return None, None
    out = [
        '"""The repository INTERFACE.',
        "",
        'The specification: "The application must have a repository interface, a',
        'SQLite implementation and a service layer." This module is the',
        "abstraction — what any task store must provide. The SQLite class in",
        "``%s`` implements it, so the service layer depends on the" % node.name,
        "contract rather than on a database.",
        '"""',
        "from __future__ import annotations",
        "",
        "from abc import ABC, abstractmethod",
    ]
    for line in _import_lines(repo_source):
        if line not in out:
            out.append(line)
    out += [
        "",
        "",
        "class %s(ABC):" % interface_name,
        '    """What a repository must provide, and nothing else."""',
        "",
    ]
    for _name, header in methods:
        out.append("    @abstractmethod")
        out.append("    %s" % header)
        out.append('        """The contract of the implementation below."""')
        out.append("        raise NotImplementedError")
        out.append("")
    return "\n".join(out).rstrip() + "\n", node.name


def _make_concrete_inherit(repo_source, class_name, interface_name, module):
    """``(source, changed)`` with the concrete class implementing the interface."""
    lines = repo_source.split("\n")
    plain = "class %s:" % class_name
    inherited = "class %s(" % class_name
    changed = False
    for index, line in enumerate(lines):
        if line.startswith(plain):
            lines[index] = "class %s(%s):" % (class_name, interface_name)
            changed = True
            break
        if line.startswith(inherited):
            bases = line[len(inherited):].rstrip()
            if not bases.endswith("):"):
                break
            lines[index] = "class %s(%s, %s)" % (
                class_name, bases[:-2], interface_name,
            )
            changed = True
            break
    if not changed:
        return repo_source, False
    insert_at = 0
    for index, line in enumerate(lines[:60]):
        if line.startswith(("import ", "from ")):
            insert_at = index + 1
    lines.insert(insert_at, "from %s import %s" % (module, interface_name))
    candidate = "\n".join(lines)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return repo_source, False
    return candidate, True


def apply_repository_interface_guards(files, repo_files):
    """Give the design the repository interface it was asked for.

    ``files`` is ``{path: source}``. Returns ``(files, notes)``.
    """
    notes = []
    for path in repo_files or []:
        source = files.get(path)
        if not source:
            continue
        stem = path.replace("\\", "/").rsplit("/", 1)[-1]
        if not stem.endswith("_repository.py"):
            continue
        module = stem[: -len("_repository.py")] + "_repository_interface"
        interface_path = module + ".py"
        if interface_path in files:
            continue
        concrete = concrete_class_name(source)
        if not concrete:
            continue
        interface_name = "%sInterface" % concrete
        interface_source, _ = render_repository_interface(source, interface_name)
        if not interface_source:
            continue
        candidate, changed = _make_concrete_inherit(
            source, concrete, interface_name, module,
        )
        if not changed:
            continue
        files[interface_path] = interface_source
        files[path] = candidate
        notes.append(
            "%s: %s created and implemented by %s"
            % (path, interface_name, concrete)
        )
    return files, notes
