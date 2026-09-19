"""Deterministic repair of integer-only arithmetic in a calculator script.

Prompt 02 asks for "addition, subtraction, multiplication and division of two
numbers". The single-pass output shipped

    @click.argument('num1', type=click.INT)
    ...
    result = num1 // num2

so ``7 2 divide`` printed ``Result: 3``. Two choices together produce that: the
operands are declared as integers, and the quotient is taken with floor
division. Division is the one operation whose result is not generally a whole
number, so a program that offers it cannot be integer-only.

The repair is confined to a file that DISPATCHES on the operation's NAME: it
mentions ``divide`` as a literal next to at least one of add/subtract/multiply.
That is the shape of an arithmetic command line and of nothing else. Ordinary
programs do divide by counts on purpose — a page count, an average over whole
items — and are returned byte-for-byte.
"""

import ast

from agentlib.generation.cli_wiring import _apply_edits, _call_kind

_OPS = ("add", "subtract", "multiply")
_INT_TYPES = ("INT", "IntRange", "int")


def _is_arithmetic_dispatcher(text):
    """True for a file that dispatches on an operation name (a calculator)."""
    lowered = text.lower()
    if "divide" not in lowered and "division" not in lowered:
        return False
    return sum(op in lowered for op in _OPS) >= 1


def _int_type_keyword(call):
    """The ``type=`` keyword of a click call when it names an integer type."""
    for keyword in call.keywords:
        if keyword.arg != "type":
            continue
        value = keyword.value
        if isinstance(value, ast.Attribute) and value.attr in _INT_TYPES:
            return keyword
        if isinstance(value, ast.Name) and value.id in _INT_TYPES:
            return keyword
    return None


def _declared_name(call, kind):
    """The operand name a click decorator declares (its dest)."""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            name = arg.value.lstrip("-").replace("-", "_")
            if name:
                return name
    return None


def _name_keywords(call):
    """Every string keyword a click call passes (``'--x'``, ``dest='x'``)."""
    names = []
    for keyword in call.keywords:
        if keyword.arg == "dest" and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                names.append(keyword.value.value.replace("-", "_"))
    return names


def _precision_edits(tree):
    """``edits`` making a calculator's operands real and its quotient exact."""
    edits = []
    converted = set()
    for node in ast.walk(tree):
        kind = _call_kind(node)
        if kind is None:
            continue
        keyword = _int_type_keyword(node)
        if keyword is None:
            continue
        value = keyword.value
        edits.append((value.lineno, value.col_offset, value.end_lineno,
                      value.end_col_offset, "click.FLOAT"))
        declared = _declared_name(node, kind)
        for name in (declared, *_name_keywords(node)):
            if name and name.isidentifier():
                converted.add(name)
    # A floor division on the operands is the second half of the defect: with
    # real operands, ``7.0 // 2.0`` would still print 3.0. The OPERATOR node
    # itself carries no reliable position, so the span is taken between the
    # two operands (the slice that holds the ``//``).
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.FloorDiv):
            left, right = node.left, node.right
            if left.end_lineno != right.lineno:
                continue          # split over two lines: decline
            edits.append(
                (right.lineno, left.end_col_offset, right.lineno,
                 right.col_offset, "/")
            )
    # The annotation must not contradict the value click now parses.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = (list(node.args.posonlyargs) + list(node.args.args)
                  + list(node.args.kwonlyargs))
        for param in params:
            ann = param.annotation
            if param.arg in converted and isinstance(ann, ast.Name) and ann.id == "int":
                edits.append((ann.lineno, ann.col_offset, ann.end_lineno,
                              ann.end_col_offset, "float"))
    return edits


def fix_arithmetic_precision(files):
    """Make a calculator's operands and quotients real (not integer).

    ``files`` is ``{path: source}``. Returns ``(files, fixed)`` where ``fixed``
    counts the files rewritten. A file that is not an arithmetic dispatcher,
    that does not parse, or whose arithmetic is already real is unchanged.
    """
    fixed = 0
    result = {}
    for path, text in files.items():
        if not path.endswith(".py") or not _is_arithmetic_dispatcher(text):
            result[path] = text
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            result[path] = text
            continue
        edits = _precision_edits(tree)
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
