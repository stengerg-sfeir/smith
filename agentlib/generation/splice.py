"""Shared AST splice and name-resolution helpers for LLM fills.

Extracted from agent.py. Both repository and service renderers splice
LLM-produced method bodies into deterministic skeletons and gate each fill
against a name-resolution contract. These helpers are common to both and
carry no behaviour change.
"""
import ast
import builtins


def _indent_block(src, spaces):
    pad = " " * spaces
    return "\n".join(pad + ln if ln.strip() else ln for ln in src.split("\n"))


def _splice_functions(text, replacements):
    """Apply (start_line, end_line, new_src) replacements (1-based, inclusive)
    bottom-up so earlier offsets stay valid."""
    lines = text.split("\n")
    for start, end, new_src in sorted(replacements, reverse=True):
        lines[start - 1 : end] = new_src.split("\n")
    return "\n".join(lines)


def _merge_stub_bodies(deterministic, filled, stub_names):
    """Splice the implementations of `stub_names` from `filled` into
    `deterministic`, leaving every other byte of the deterministic file
    untouched. Returns the merged text, or None when the fill does not
    provide exactly the expected methods."""
    # A mismatched merge (or an earlier fill that returned None) must never
    # reach ast.parse with None — that raised a TypeError deep in the
    # salvage loop (observed on a service whose design carried garbage
    # "impl"-named methods). Fail the merge cleanly instead.
    if not isinstance(deterministic, str) or not isinstance(filled, str):
        return None
    try:
        ftree = ast.parse(filled)
        dtree = ast.parse(deterministic)
    except SyntaxError:
        return None
    needed = set(stub_names)
    found = {}
    for node in ast.walk(ftree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in needed
        ):
            found[node.name] = node
    if set(found) != needed:
        return None
    repls = []
    for node in ast.walk(dtree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in needed
        ):
            new_src = ast.unparse(found[node.name])
            repls.append(
                (
                    node.lineno,
                    node.end_lineno,
                    _indent_block(new_src, node.col_offset),
                )
            )
    if len(repls) != len(needed):
        return None
    return _splice_functions(deterministic, repls)


def _target_names(t):
    """All identifier names bound by an assignment target."""
    if isinstance(t, ast.Name):
        return {t.id}
    if isinstance(t, (ast.Tuple, ast.List)):
        out = set()
        for elt in t.elts:
            out |= _target_names(elt)
        return out
    if isinstance(t, ast.Starred):
        return _target_names(t.value)
    return set()


def _module_defined_names(source):
    """Module-level names DEFINED or IMPORTED in `source` — the visible
    namespace a spliced fill body may legally reference."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                names |= _target_names(t)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            names |= _target_names(node.target)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def _fn_defined_names(fn):
    """Names bound inside one function: params, assignments, loop/comprehension
    targets, nested defs/classes, except-handlers, walrus."""
    names = {a.arg for a in fn.args.args + fn.args.kwonlyargs
             + fn.args.posonlyargs}
    if fn.args.vararg:
        names.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        names.add(fn.args.kwarg.arg)
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                names |= _target_names(t)
        elif isinstance(node, ast.AnnAssign):
            names |= _target_names(node.target)
        elif isinstance(node, ast.For):
            names |= _target_names(node.target)
        elif isinstance(node, ast.comprehension):
            names |= _target_names(node.target)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.With):
            for item in node.items:
                if item.optional_vars is not None:
                    names |= _target_names(item.optional_vars)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            names |= _target_names(node.target)
    return names


_PY_BUILTINS = set(dir(builtins)) | {"self", "cls"}


def _fn_undefined_names(fn, module_names):
    """Names LOADED anywhere in `fn` that resolve to nothing visible:
    not module-level defined/imported, not locally bound, not builtins.
    Catches the classic landmine of fills referencing sibling model classes
    (`Loan(**dict(r))`) without importing them — a guaranteed NameError at
    runtime. Returns sorted list of offending names."""
    visible = _fn_defined_names(fn) | module_names | _PY_BUILTINS
    undefined = {
        n.id for n in ast.walk(fn)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        and n.id not in visible
    }
    return sorted(undefined)


def _fn_has_stub_raise(fn):
    """True when the function body raises NotImplementedError anywhere.

    A refusal is never an implementation: a fill whose body IS (or contains)
    `raise NotImplementedError(...)` used to pass every schema/name gate
    (a stub references nothing) and shipped verbatim — the benchmark
    `not_implemented` failures on runs 10/13/16/19 all shipped this way,
    some carrying the kernel's own justification string ("the 'active'
    column does not exist ..."). Rejecting the fill feeds it back into the
    corrective retry instead of silently locking the refusal in place.
    """
    for node in ast.walk(fn):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            exc = exc.func
        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            return True
        if (
            isinstance(exc, ast.Attribute)
            and exc.attr == "NotImplementedError"
        ):
            return True
    return False
