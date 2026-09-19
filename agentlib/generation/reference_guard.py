"""Enforce a spec-declared REFERENTIAL guard on DELETE (C5).

``reference_rules.extract_reference_rules`` reads the prompt ("A category
cannot be deleted while products still belong to it", prompt 36); this module
makes the refusal hold:

* the CATEGORY repository gains ``has_products(category_id)`` — a referential
  existence test. Note the asymmetry: the method lives on the CATEGORY
  repository (that is the class whose ``delete`` is guarded) but queries the
  PRODUCT table, whose name is read back from the PRODUCT repository's own
  ``FROM`` clause;
* the category service's DELETE path refuses BEFORE removing the row, so a
  referenced category is never deleted and its products never orphaned.

This is a GUARD (a refusal), deliberately distinct from the CASCADE behaviour
prompt 37 asks for: the specification decides which of the two applies, and
here it says the delete must not happen.
"""
from __future__ import annotations

from .field_guard import _snake_name, inject_guards
from .overlap_guard import _class_body_end

_MARKER = "# referential delete guard (spec)"
_DEFAULT_EXCEPTION = "ValidationError"
_GENERIC_EXCEPTIONS = (
    "ValidationError",
    "InvalidValueError",
    "ConflictError",
    "ValueError",
)
# Exception names that describe a refusal to delete a REFERENCED row.
_REFERENCE_HINTS = ("notempty", "not_empty", "referenc", "conflict", "invalid")


def pick_reference_exception(exception_names, item_snake):
    """The exception a blocked delete should raise.

    A design that declares ``CategoryHasProductsError`` names the refusal
    exactly, so an exception mentioning the ITEM (``product``) is preferred —
    design-derived, not invented. Then the generic referential hints, then the
    validation names, then the builtin ``ValueError``.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    # The referential hints come FIRST. Matching on the item name alone is too
    # broad: prompt 36's design declares BOTH ``CategoryNotEmptyError`` (the
    # right class) and ``ProductNotFoundError``, and "product" matches the
    # latter — a blocked delete would then report a missing product.
    for hint in _REFERENCE_HINTS:
        for name in sorted(names):
            if hint in name.lower():
                return name
    if item_snake:
        for name in sorted(names):
            low = name.lower()
            if item_snake in low and "notfound" not in low and "missing" not in low:
                return name
    for want in _GENERIC_EXCEPTIONS:
        if want in names:
            return want
    return _DEFAULT_EXCEPTION if _DEFAULT_EXCEPTION in names else "ValueError"


def repo_reference_method(res_snake, item_snake, fk, item_table, method_name):
    """The ``has_<items>`` method on the RESOURCE repository."""
    sql = "SELECT 1 FROM %s WHERE %s = ? LIMIT 1" % (item_table, fk)
    return [
        "    def %s(self, %s: int) -> bool:" % (method_name, fk),
        '        """True when %s still belong to this %s."""'
        % (item_snake + "s", res_snake),
        "        with self.db.connect() as conn:",
        "            row = conn.execute(",
        '                "%s",' % sql,
        "                (%s,)," % fk,
        "            ).fetchone()",
        "        return row is not None",
    ]


def _method_args(source, method_name):
    """The parameter names of ``method_name``, or None."""
    from .overlap_guard import _service_args

    return _service_args(source, method_name)


def service_guard_lines(rule, res_snake, args, exception_names):
    """The delete-path guard lines, or None when the id argument is missing."""
    item_snake = rule["item"]
    method_name = "has_%ss" % item_snake
    if args is None or "id" not in args:
        return None
    exc = pick_reference_exception(exception_names, item_snake)
    message = "cannot delete %s while %ss still belong to it" % (
        res_snake, item_snake,
    )
    return [
        "        " + _MARKER,
        "        if self.%s_repo.%s(id):" % (res_snake, method_name),
        "            raise %s(%r)" % (exc, message),
    ]


def apply_reference_guard(res_repo_source, svc_source, res_cls, rule, item_table,
                          exception_names):
    """Return (repo_source, svc_source) with the referential guard applied.

    ``res_repo_source`` is the RESOURCE (category) repository and
    ``item_table`` the ITEM (product) table, read from the product repository
    by the caller. Additive and idempotent; either half may be skipped.
    """
    if not rule or not item_table:
        return res_repo_source, svc_source
    res_snake = _snake_name(res_cls)
    item_snake = rule["item"]
    fk = rule["fk_field"]
    method_name = "has_%ss" % item_snake
    if res_repo_source and _MARKER not in res_repo_source:
        end = _class_body_end(res_repo_source)
        if end is not None:
            lines = res_repo_source.splitlines(keepends=True)
            block = "".join(
                line + "\n" for line in repo_reference_method(
                    res_snake, item_snake, fk, item_table, method_name
                )
            )
            res_repo_source = (
                "".join(lines[:end]) + "\n" + block + "".join(lines[end:])
            )
    for delete_name in ("delete_" + res_snake, "remove_" + res_snake):
        args = _method_args(svc_source, delete_name)
        guard = service_guard_lines(rule, res_snake, args, exception_names)
        if guard:
            svc_source = inject_guards(svc_source, delete_name, guard)
    return res_repo_source, svc_source
