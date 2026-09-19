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


def _repo_signatures(repo_source):
    """``{method_name: {parameter names}}`` for a rendered repository."""
    try:
        tree = ast.parse(repo_source)
    except (SyntaxError, TypeError):
        return {}
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            args = node.args
            found[node.name] = {
                arg.arg for arg in
                list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            }
    return found


def _target_local(stmt):
    """The local a single-target assignment writes, or None."""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _refuses_local(stmt, local):
    """True for ``if not <local>: raise ...`` (an existence refusal)."""
    if not isinstance(stmt, ast.If) or not isinstance(stmt.test, ast.UnaryOp):
        return False
    if not isinstance(stmt.test.op, ast.Not):
        return False
    operand = stmt.test.operand
    if not isinstance(operand, ast.Name) or operand.id != local:
        return False
    return any(isinstance(sub, ast.Raise) for sub in ast.walk(stmt))


def drop_unsupported_repo_checks(source, repo_source):
    """``(source, dropped)`` removing a check the repository cannot serve.

    The shipped bulk update began with

        existing_ids = self.product_repo.list(product_ids=product_ids)
        if not existing_ids:
            raise NotFoundError(...)

    and ``ProductRepository.list`` accepts no ``product_ids``: the call raised
    ``TypeError`` on EVERY invocation, so the operation could never run. A call
    to a repository method with a keyword that method does not declare is an
    unresolved contract; when its only use is a refusal immediately after, the
    check is dropped and the repository's own update path reports the miss.
    """
    try:
        tree = ast.parse(source)
        signatures = _repo_signatures(repo_source)
    except (SyntaxError, TypeError):
        return source, 0
    if not signatures:
        return source, 0
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        for index, statement in enumerate(body[:-1]):
            call = statement.value if isinstance(statement, ast.Assign) else None
            if not isinstance(call, ast.Call):
                continue
            function = call.func
            if not (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Attribute)
            ):
                continue
            declared = signatures.get(function.attr)
            if declared is None:
                continue
            unsupported = [
                keyword.arg for keyword in call.keywords
                if keyword.arg and keyword.arg not in declared
            ]
            if not unsupported:
                continue
            local = _target_local(statement)
            if local is None or not _refuses_local(body[index + 1], local):
                continue
            spans.append(_span(statement))
            spans.append(_span(body[index + 1]))
    if not spans:
        return source, 0
    lines = source.split("\n")
    for start, end in sorted(set(spans), reverse=True):
        if start < 1 or end > len(lines) or end < start:
            return source, 0
        del lines[start - 1:end]
    candidate = "\n".join(lines)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return source, 0
    return candidate, len(set(spans))


def apply_update_validation_guards(files, service_files, repo_files=None):
    """Remove the create-only rule, and the checks a repository cannot serve.

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
            source = candidate
        stem = path.replace("\\", "/").rsplit("/", 1)[-1]
        if stem.endswith("_service.py"):
            stem = stem[: -len("_service.py")]
        repo_source = next(
            (
                files.get(candidate_path)
                for candidate_path in repo_files or []
                if candidate_path.endswith("%s_repository.py" % stem)
            ),
            None,
        )
        if not repo_source:
            continue
        candidate, dropped = drop_unsupported_repo_checks(source, repo_source)
        if dropped:
            files[path] = candidate
            notes.append(
                "%s: %d unsupported repository check(s) removed"
                % (path, dropped)
            )
    return files, notes
