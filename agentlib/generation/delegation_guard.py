"""Restore the delegation a service method owes its repository (prompt 17).

The repository method is right and the service method of the SAME NAME ignores
its own parameter:

    # product_repository.py
    def search_product(self, term: str) -> List[Product]:
        rows = conn.execute(
            "SELECT * FROM products WHERE name LIKE ? OR category LIKE ?", ...)

    # product_service.py  (shipped)
    def search_product(self, term: str) -> List[Dict[str, Any]]:
        results = {}
        for row in self.product_repo.list():
            key = row.category                     # 'term' is never read
            results[key] = results.get(key, 0) + row.price
        return results

so ``product search --term Widget`` answered ``{'tools': 10.0, 'food': 20.0}``:
a category summary, not a search. The fill phase had produced an aggregation
and left the caller's own parameter unused.

A parameter that a method never reads, while its repository exposes a method
of the same name that accepts exactly those parameters, is a delegation that
was meant to be written. The repair replaces the BODY only — the signature and
its annotations are the file's own convention (``list_product`` above delegates
with the same ``List[Dict[str, Any]]``) — and it declines whenever the pairing
is not exact.
"""

import ast


def _entity_stem(path):
    """``product_service.py`` -> ``product``."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if name.endswith(".py"):
        name = name[: -len(".py")]
    for suffix in ("_service", "_repo", "_repository"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _functions(tree):
    """Every function/method of a module, by name."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault(node.name, node)
    return found


def _params(node):
    """The parameter names of a function, in signature order."""
    args = node.args
    names = [
        arg.arg for arg in
        list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    ]
    return names


def _mentioned(node):
    """Every identifier named anywhere under ``node``."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.arg):
            names.add(sub.arg)
        elif isinstance(sub, ast.Attribute):
            names.add(sub.attr)
        elif isinstance(sub, ast.keyword) and sub.arg:
            names.add(sub.arg)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            names.update(sub.value.replace("{", " ").replace("}", " ").split())
    return names


def _body_mentions(node):
    """Identifiers used in the BODY of a function (the signature excluded)."""
    used = set()
    for statement in node.body:
        used |= _mentioned(statement)
    return used


def _rewrite(service_source, repo_source, repo_attr):
    """``(source, applied)`` rewriting the delegated methods of one service."""
    try:
        service_tree = ast.parse(service_source)
        repo_tree = ast.parse(repo_source)
    except SyntaxError:
        return service_source, []
    repo_functions = _functions(repo_tree)
    service_lines = service_source.split("\n")
    edits = []
    for node in _functions(service_tree).values():
        if node.name.startswith("_") or not isinstance(node, ast.FunctionDef):
            continue
        repo_node = repo_functions.get(node.name)
        if repo_node is None:
            continue
        params = [name for name in _params(node) if name != "self"]
        if not params:
            continue
        if set(_params(repo_node)) != set(_params(node)):
            continue
        unused = [name for name in params if name not in _body_mentions(node)]
        if not unused:
            continue
        def_line = service_lines[node.lineno - 1]
        if not def_line.rstrip().endswith(":"):
            continue  # signature spans several lines: decline
        indent = " " * (node.col_offset + 4)
        replacement = []
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            last = first.end_lineno or first.lineno
            for index in range(first.lineno - 1, last):
                replacement.append(indent + service_lines[index].strip())
        arguments = ", ".join("%s=%s" % (name, name) for name in params)
        replacement.append(
            "%sreturn self.%s.%s(%s)" % (indent, repo_attr, node.name, arguments)
        )
        edits.append((node.lineno, node.end_lineno, def_line, replacement))
    if not edits:
        return service_source, []
    for start, end, def_line, replacement in sorted(edits, reverse=True):
        service_lines[start - 1:end] = [def_line] + replacement
    candidate = "\n".join(service_lines)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return service_source, []
    return candidate, [line for _, _, _, repl in edits for line in repl]


def apply_delegation_guards(files, service_files, repo_files):
    """Delegate every service method whose repository has the same contract.

    ``files`` is ``{path: source}``. Only the pair
    ``<entity>_service.py`` / ``<entity>_repository.py`` is considered, so a
    service never delegates to another entity's repository. Returns
    ``(files, notes)``.
    """
    repos = {}
    for path in repo_files or []:
        source = files.get(path)
        if source:
            repos[_entity_stem(path)] = source
    notes = []
    for path in service_files or []:
        source = files.get(path)
        if not source:
            continue
        stem = _entity_stem(path)
        repo_source = repos.get(stem)
        if not repo_source:
            continue
        rewritten, applied = _rewrite(source, repo_source, "%s_repo" % stem)
        if applied:
            files[path] = rewritten
            notes.append("%s: %d delegation(s)" % (path, len(applied)))
    return files, notes
