"""Enforce a spec-declared STOCK MOVEMENT on the creation of a line.

``stock_rules.extract_stock_rules`` reads the prompt ("... any product has
insufficient stock. When an order is successfully created, the corresponding
stock quantities must be decreased", prompt 53); this module makes it hold in
the service's create path for the LINE:

    _stock_row = self.product_repo.get_by_id(product_id)
    if _stock_row is not None and (_stock_row.stock_quantity or 0) < quantity:
        raise InsufficientStockError(...)
    if _stock_row is not None:
        self.product_repo.update(_stock_row.id, {
            'stock_quantity': (_stock_row.stock_quantity or 0) - quantity,
        })

Three details are deliberate:

* the counter is moved THROUGH the referenced entity's own repository
  (``update(id, data)``), the same deterministic API every other path uses —
  never a raw SQL write invented here;
* the guard's arguments are the SERVICE method's own parameter names, matched
  against the model's field names; when a name does not line up the whole guard
  is dropped rather than invented, because moving the wrong column (or reading
  the wrong argument) would silently corrupt the counter;
* the refusal is emitted BEFORE the move, so nothing is written when the stock
  is insufficient — the specification's own demand.
"""
from __future__ import annotations

import ast

from .field_guard import _method_named, _snake_name, inject_guards

_MARKER = "# stock guard (spec)"
_STOCK_HINTS = ("insufficient", "stock", "unavailable", "inventory", "outofstock")
_GENERIC_EXCEPTIONS = (
    "ValidationError",
    "InvalidValueError",
    "ConflictError",
    "ValueError",
)
_DEFAULT_EXCEPTION = "ValidationError"


def pick_stock_exception(exception_names):
    """The exception an under-stocked creation should raise.

    The design's own naming decides (``InsufficientStockError`` names this
    refusal exactly); failing that the generic validation names, then the
    builtin ``ValueError`` — a refusal is never a silent pass.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    for hint in _STOCK_HINTS:
        for name in sorted(names):
            if hint in name.lower():
                return name
    for want in _GENERIC_EXCEPTIONS:
        if want in names:
            return want
    return _DEFAULT_EXCEPTION if _DEFAULT_EXCEPTION in names else "ValueError"


def _service_args(source, method_name):
    """The parameter names of ``method_name``, or None."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return None
    method = _method_named(tree, method_name)
    if method is None:
        return None
    return [a.arg for a in method.args.args]


def _arg_for(args, field):
    """The service parameter carrying ``field``, or None.

    Exact name first (the renderer names parameters after the model fields),
    then a bounded singular/plural form — never an arbitrary substring match.
    """
    if args is None or not field:
        return None
    if field in args:
        return field
    variants = {field.rstrip("s"), field + "s"}
    for cand in args:
        if cand in variants and cand != "self":
            return cand
    return None


def service_guard_lines(rule, method_name, args, exception_names):
    """The create-path guard lines, or None when a needed name is missing."""
    fk = rule["fk_param"]
    qty_field = rule["qty_field"]
    fk_arg = _arg_for(args, fk)
    qty_arg = _arg_for(args, qty_field) if qty_field else None
    if not fk_arg:
        return None
    # A line with no quantity of its own moves the counter by ONE: a loan is a
    # single copy (prompts 41/52), and the move is still the prompt's own.
    qty_arg = qty_arg or "1"
    ref_snake = rule["ref_snake"]
    field = rule["stock_field"]
    sign = "-" if rule["sign"] < 0 else "+"
    row = "_stock_%s" % ref_snake
    counter = "%s.%s" % (row, field)
    lines = [
        "        " + _MARKER,
        "        %s = self.%s_repo.get_by_id(%s)" % (row, ref_snake, fk_arg),
    ]
    if rule.get("refuse"):
        exc = pick_stock_exception(exception_names)
        lines += [
            "        if %s is not None and (%s or 0) < %s:"
            % (row, counter, qty_arg),
            "            raise %s(%r)" % (exc, "insufficient %s" % field),
        ]
    lines += [
        "        if %s is not None:" % row,
        "            self.%s_repo.update(%s.id, {'%s': (%s or 0) %s %s})"
        % (ref_snake, row, field, counter, sign, qty_arg),
    ]
    return lines


def apply_stock_guard(svc_source, cls_line, rule, exception_names):
    """Return ``svc_source`` with the stock movement enforced on creation.

    Additive and idempotent: the guard is spliced at the top of the create
    body, and a re-render (marker present) is a no-op. When the create method
    is absent, or a parameter name does not line up, the source is returned
    untouched.
    """
    if not rule or not svc_source:
        return svc_source
    if _MARKER in svc_source:
        # Already enforced: inject_guards checks ITS OWN marker (the field
        # validation one), so this guard must refuse to double itself here.
        return svc_source
    line_snake = _snake_name(cls_line)
    for create_name in ("add_" + line_snake, "create_" + line_snake):
        args = _service_args(svc_source, create_name)
        guard = service_guard_lines(rule, create_name, args, exception_names)
        if guard:
            svc_source = inject_guards(svc_source, create_name, guard)
    return svc_source


_RESTORE_MARKER = "# stock restore (spec)"


def restore_guard_lines(restore, args):
    """The return-path lines for the operation that hands the quantities back.

    The lines of the container are walked with the deterministic repository API
    only (``get_all()`` then a filter on the line's own foreign key), so the
    guard never depends on which filters the design declared on ``list()``.
    Returns None when the operation's own container argument cannot be
    resolved — a guard is dropped rather than invented.
    """
    # The operation names its HOST: a cancellation names the container
    # (cancel_order), a return names the counter itself ("when it is returned"
    # -> return_book). Both walk the container's lines and move the counter;
    # only the filter column and the host argument differ.
    host = restore.get("host_snake") or restore.get("container_snake") or ""
    id_arg = _arg_for(args, host + "_id") or _arg_for(args, "id")
    line_ref_fk = restore.get("counter_fk") or restore.get("line_ref_fk")
    line_fk = restore.get("host_fk") or restore.get("line_fk")
    if not id_arg or not line_ref_fk or not line_fk:
        return None
    qty = restore.get("qty_field")
    # A line with no quantity of its own hands back ONE (a loan).
    amount = ("_line.%s" % qty) if qty else "1"
    ref_snake = restore["ref_snake"]
    field = restore["stock_field"]
    row = "_stock_%s" % ref_snake
    counter = "%s.%s" % (row, field)
    return [
        "        " + _RESTORE_MARKER,
        "        for _line in self.%s_repo.get_all():" % restore["line_snake"],
        "            if _line.%s != %s:" % (line_fk, id_arg),
        "                continue",
        "            %s = self.%s_repo.get_by_id(_line.%s)"
        % (row, ref_snake, line_ref_fk),
        "            if %s is not None:" % row,
        "                self.%s_repo.update(%s.id, {'%s': (%s or 0) + %s})"
        % (ref_snake, row, field, counter, amount),
    ]


def apply_stock_restore(svc_source, restore, exception_names=None):
    """Return ``svc_source`` with the return path enforced, or it unchanged.

    The operation is ``<op>_<container>`` (``cancel_order``); it may live in ANY
    service, so this is offered to every rendered service and applied where the
    method exists — a no-op otherwise, and idempotent through its own marker.
    """
    if not restore or not svc_source:
        return svc_source
    if _RESTORE_MARKER in svc_source:
        return svc_source
    # The operation may be named after EITHER end: `cancel_order` (the
    # container) or `return_book` ("when it is returned" — the counter).
    op = restore.get("op") or ""
    host = (restore.get("host_snake") or restore.get("container_snake") or "")
    if not op or not host:
        return svc_source
    for name in ("%s_%s" % (op, host), "%s_%s" % (host, op)):
        args = _service_args(svc_source, name)
        if args is None:
            continue
        guard = restore_guard_lines(restore, args)
        if guard:
            svc_source = inject_guards(svc_source, name, guard)
    return svc_source
