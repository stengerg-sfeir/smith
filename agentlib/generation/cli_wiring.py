"""Deterministic repair of click option -> callback-parameter wiring.

``click`` binds a callback's parameters BY NAME: ``Command.invoke`` builds a
dict keyed by each option's ``dest`` and calls ``callback(**params)``. An
option written ``--list`` therefore REQUIRES a callback parameter literally
named ``list``; a small model that renames it ``list_flag`` (to avoid
shadowing the builtin) leaves click with a keyword the callback does not
accept, and every invocation of that command dies with

    TypeError: cli() got an unexpected keyword argument 'list'

which is exactly the prompt-03 failure — a command that is present, listed,
and crashes on every call.

The repair runs on the GENERATED source, so it is the same law for the
deterministic manifest-first renderer and for the single-pass path (which is
where 03 comes from). It renames a parameter ONLY when click cannot bind it,
and it declines whenever the rename could not be applied unambiguously, so a
file whose wiring is already consistent is returned byte-for-byte.
"""

import ast
import keyword


def _call_kind(node):
    """``"argument"``/``"option"`` for a click decorator call, else None.

    Shared by the wiring, arithmetic-precision and prompt laws: each of them
    has to recognise a click declaration on ANY receiver (``click.option``)
    and on a bare imported name (``@option``).
    """
    if not isinstance(node, ast.Call):
        return None
    fn = node.func
    if isinstance(fn, ast.Attribute) and fn.attr in ("argument", "option"):
        return fn.attr
    if isinstance(fn, ast.Name) and fn.id in ("argument", "option"):
        return fn.id
    return None


def _option_dest(names):
    """The callback parameter name click derives from an option's declarations.

    Mirrors click's own rule: ``Option.__init__`` scans the declarations for
    a plain (non-dash) name and uses it verbatim; otherwise it takes the
    LONGEST long option (``--x``) and turns it into an identifier. Returns
    None when no declaration can yield a name.
    """
    strings = [n for n in names if isinstance(n, str) and n]
    explicit = [n for n in strings if not n.startswith("-")]
    if explicit:
        return explicit[0].replace("-", "_")
    longs = [n for n in strings if n.startswith("--")]
    shorts = [n for n in strings if n.startswith("-") and not n.startswith("--")]
    if longs:
        pick = max(longs, key=len)
    elif shorts:
        pick = shorts[0]
    else:
        return None
    return pick.lstrip("-").replace("-", "_")


def _decorator_dest(dec):
    """The dest contributed by one decorator, or None when it is not a click
    option/argument.

    ``click.option``/``click.argument`` are recognised by the attribute name
    on ANY receiver (``click.option``, ``click.decorators.option``) and by a
    bare imported name (``@option``); the caller only reaches here for a file
    that imports click.
    """
    if not isinstance(dec, ast.Call):
        return None
    fn = dec.func
    if isinstance(fn, ast.Attribute) and fn.attr in ("option", "argument"):
        kind = fn.attr
    elif isinstance(fn, ast.Name) and fn.id in ("option", "argument"):
        kind = fn.id
    else:
        return None
    values = [
        a.value for a in dec.args
        if isinstance(a, ast.Constant) and isinstance(a.value, str)
    ]
    if kind == "argument":
        if not values:
            return None
        return values[0].lstrip("-").replace("-", "_")
    return _option_dest(values)


def _function_dests(node):
    """Parameter names click will pass to this function, in decorator order."""
    dests = []
    for dec in node.decorator_list:
        dest = _decorator_dest(dec)
        if dest and dest not in dests:
            dests.append(dest)
    return dests


def _param_args(node):
    """Every parameter ``ast.arg`` of a function, in signature order."""
    a = node.args
    return list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)


def _name_spans(node, name):
    """(lineno, col, end_lineno, end_col) of every Name ``name`` under node."""
    spans = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == name:
            spans.append(
                (sub.lineno, sub.col_offset, sub.end_lineno, sub.end_col_offset)
            )
    return spans


def _is_used_as_keyword_or_attr(tree, name):
    """True when ``name`` is also a call keyword or an attribute anywhere.

    Renaming a parameter is textually safe only if the identifier is used
    purely as a bare name: a ``foo(list_flag=...)`` keyword or a
    ``obj.list_flag`` attribute would keep the old spelling and break. Such a
    file is left untouched rather than half-renamed.
    """
    for sub in ast.walk(tree):
        if isinstance(sub, ast.keyword) and sub.arg == name:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == name:
            return True
    return False


def _edits_for_function(node, renames):
    """Textual (lineno, col, end_lineno, end_col, new) edits for one function.

    ``renames`` is ``[(old, new), ...]``. The parameter's ``ast.arg`` spans
    the signature and every bare ``ast.Name`` spans a body use; both are
    single-line, so the caller can splice them back without reformatting the
    file (an ``ast.unparse`` round-trip would drop comments and blank lines).
    """
    edits = []
    for old, new in renames:
        for arg in _param_args(node):
            if arg.arg == old:
                edits.append(
                    (arg.lineno, arg.col_offset, arg.end_lineno,
                     arg.end_col_offset, new)
                )
        for (l, c, el, ec) in _name_spans(node, old):
            edits.append((l, c, el, ec, new))
    return edits


def _apply_edits(lines, edits):
    """Splice edits into ``lines`` from the end so earlier offsets stay valid."""
    for (lineno, col, end_lineno, end_col, new) in sorted(
        edits, key=lambda e: (e[0], e[1]), reverse=True
    ):
        if lineno != end_lineno:
            return None  # multi-line span: unsupported, decline
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            return None
        line = lines[idx]
        if col < 0 or end_col > len(line) or end_col < col:
            return None
        lines[idx] = line[:col] + new + line[end_col:]
    return lines


def _rename_plan(node, dests):
    """``[(old, new)]`` closing the click-dest gaps, or None to decline.

    Only an UNAMBIGUOUS, same-size gap is repaired: the parameters click
    cannot bind must be exactly as many as the parameters no option claims,
    so the pairing is forced (``list`` unbound + ``list_flag`` unclaimed ->
    rename). Any other shape (two gaps, an extra name, a name used as a
    keyword/attribute) declines, so a working file is never touched.
    """
    params = [a.arg for a in _param_args(node)]
    missing = [d for d in dests if d not in params]
    if not missing:
        return []
    extras = [p for p in params if p not in dests]
    if len(missing) != len(extras):
        return None
    plan = []
    for dest, old in zip(missing, extras):
        if keyword.iskeyword(dest) or not dest.isidentifier():
            return None
        plan.append((old, dest))
    return plan


def fix_click_option_params(files):
    """Repair click option -> callback-parameter name mismatches in ``files``.

    ``files`` is ``{path: source}``. Returns ``(files, fixed)`` where
    ``fixed`` counts the files rewritten. A file that does not import click,
    does not parse, or already binds every option is returned unchanged.
    """
    fixed = 0
    result = {}
    for path, text in files.items():
        if not path.endswith(".py") or "click" not in text:
            result[path] = text
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            result[path] = text
            continue
        lines = text.split("\n")
        edits = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            dests = _function_dests(node)
            if not dests:
                continue
            plan = _rename_plan(node, dests)
            if not plan:
                continue
            if any(
                _is_used_as_keyword_or_attr(tree, old) for old, _ in plan
            ):
                continue
            edits.extend(_edits_for_function(node, plan))
        if not edits:
            result[path] = text
            continue
        spliced = _apply_edits(lines, edits)
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
