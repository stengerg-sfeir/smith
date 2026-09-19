"""Render the spec-declared AUDIT TRAIL (E1).

Two halves, both forced by prompt 33:

1. ``strip_audit_cascade`` — the design gives the audit table
   ``FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE``.
   That single clause makes the deletion's own audit row impossible: written
   BEFORE the delete it is cascaded away, written AFTER it violates the FK.
   An audit log is a historical record and must OUTLIVE its subject, so the
   audit entity's foreign key is dropped (it keeps the id column, as
   historical data, not as a live reference).

2. ``apply_audit_guards`` — splice the missing write into each of the create,
   update and delete service methods. The write goes AFTER the operation and
   only when it succeeded: the create's new id is captured from the
   repository's return value, update/delete use their ``id`` parameter. The
   audit row is built with the audit entity's OWN constructor, whose
   ``__post_init__`` supplies the timestamp — so the record always carries the
   operation, the id and the time, as the specification requires.
"""
from __future__ import annotations

import ast
import re

from .field_guard import _snake_name

_MARKER = "# audit trail (spec)"
_CREATE_NAMES = ("add_%s", "create_%s")
_UPDATE_NAMES = ("update_%s",)
_DELETE_NAMES = ("delete_%s", "remove_%s")


def strip_audit_cascade(entities_by_class, audit_cls):
    """Drop the audit entity's FKs so its rows do not cascade away.

    In place. The id column stays (it is the historical reference the spec
    asks for); only the live foreign key — and with it ``ON DELETE CASCADE``
    — is removed, because an audit row must survive the delete it records.
    """
    ent = (entities_by_class or {}).get(audit_cls)
    if isinstance(ent, dict) and ent.get("fks"):
        ent["fks"] = []
    return ent


def _method_def(source, name):
    """The ``ast.FunctionDef`` named ``name`` (class bodies included)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _method_args(node):
    args = [a.arg for a in node.args.args]
    args += [a.arg for a in node.args.posonlyargs]
    args += [a.arg for a in node.args.kwonlyargs]
    return args


def _import_audit_class(source, audit_cls, audited_cls):
    """Ensure the audit class is imported where the service imports its entity.

    ``from models import Customer`` becomes ``from models import Customer,
    AuditRecord`` — the constructor the spliced write calls must resolve, and
    this reuses the import line the design already wrote rather than guessing
    a module name.
    """
    head = source.split("\nclass ")[0]
    if re.search(r"\b%s\b" % re.escape(audit_cls), head):
        return source
    pattern = re.compile(
        r"^(from\s+\S+\s+import\s+)([^\n]*\b%s\b[^\n]*)$" % re.escape(audited_cls),
        re.M,
    )
    m = pattern.search(source)
    if not m:
        return source
    return source[: m.end(2)] + ", " + audit_cls + source[m.end(2):]


def _audit_statement(rule, op, indent):
    """The ``self.<audit_repo>.create(<AuditCls>(...))`` line for ``op``."""
    audit_cls = rule["audit_cls"]
    repo = "%s_repo" % _snake_name(audit_cls)
    return "%sself.%s.create(%s(%s=%s, %s=%r))%s" % (
        indent, repo, audit_cls, rule["id_field"], rule["_id_expr"],
        rule["operation_field"], op, "  " + _MARKER,
    )


def _splice(source, method_name, op, rule):
    """Rewrite the method's final return so it audits on success.

    ``source`` is returned unchanged when the method is absent, already
    audited, or does not end in a plain return (a body the fill shaped
    differently is left alone rather than corrupted).
    """
    node = _method_def(source, method_name)
    if node is None or not node.body:
        return source
    # Idempotence is PER METHOD: checking the whole source would make the
    # first splice mask every later method (only the create would be audited).
    all_lines = source.splitlines()
    end = getattr(node, "end_lineno", None) or node.body[-1].lineno
    if _MARKER in "\n".join(all_lines[node.lineno - 1:end]):
        return source
    last = node.body[-1]
    if not isinstance(last, ast.Return) or last.value is None:
        return source
    lines = source.splitlines(keepends=True)
    idx = last.lineno - 1
    if idx >= len(lines):
        return source
    raw = lines[idx]
    stripped = raw.lstrip()
    indent = raw[: len(raw) - len(stripped)]
    if "return " not in stripped:
        return source
    expr = stripped[len("return "):].rstrip("\n").rstrip()
    rule = dict(rule)
    tmp = "_audit_%s" % _snake_name(rule["audit_cls"])
    if "id" not in _method_args(node):
        # create: the repository returns the NEW id, which is what the audit
        # record must carry — so capture it before returning it.
        rule["_id_expr"] = tmp
        new = [
            "%s%s = %s\n" % (indent, tmp, expr),
            "%sif %s is not None:\n" % (indent, tmp),
            "    " + _audit_statement(rule, op, indent) + "\n",
            "%sreturn %s\n" % (indent, tmp),
        ]
    else:
        # update / delete: the id is already the caller's argument; audit only
        # a write that actually happened.
        rule["_id_expr"] = "id"
        new = [
            "%s%s = %s\n" % (indent, tmp, expr),
            "%sif %s:\n" % (indent, tmp),
            "    " + _audit_statement(rule, op, indent) + "\n",
            "%sreturn %s\n" % (indent, tmp),
        ]
    lines[idx: idx + 1] = new
    return "".join(lines)


def apply_audit_guards(source, cls, rule):
    """Return ``source`` with the audit writes spliced into CRUD methods.

    ``cls`` is the audited entity class; ``rule`` the entry produced by
    ``audit_rules.extract_audit_rules``. Additive and idempotent: the marker
    on each audit line makes a second pass a no-op.
    """
    if not rule or not source:
        return source
    e = _snake_name(cls)
    source = _import_audit_class(source, rule["audit_cls"], cls)
    for op, templates in (
        ("create", _CREATE_NAMES),
        ("update", _UPDATE_NAMES),
        ("delete", _DELETE_NAMES),
    ):
        for tpl in templates:
            source = _splice(source, tpl % e, op, rule)
    return source
