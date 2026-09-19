"""Render the spec-declared NOTIFICATION requirement (E2).

``notify_rules.extract_notify_rules`` reads the trigger (prompt 40: "When an
order is confirmed, the application must send a notification"); this module
supplies the three things the specification asks for and none of which exist:

1. an ABSTRACTION — ``notifications.NotificationService(ABC)`` declaring
   ``notify(recipient, message)``;
2. a simple LOGGING implementation — ``LoggingNotificationService``, which
   records the notification through the standard ``logging`` module instead of
   sending a real message (exactly as the specification says);
3. the CALL — the confirmation's service method notifies before returning, so
   the confirmation actually produces one.

The abstraction is written into its own module (``notifications.py``) and the
order service uses it through a type-hinted PORT attribute, so the service
depends on the abstraction, not on the logging implementation. The port is
imported under an alias (``NotificationPort``) because a design may already
have named its order service ``NotificationService`` (prompt 40 does) — the
alias keeps both names legal in one file.
"""
from __future__ import annotations

import ast
import re

from .field_guard import _snake_name

NOTIFICATIONS_MODULE = "notifications"
_PORT_ALIAS = "NotificationPort"
_ABSTRACTION = "NotificationService"
_LOGGING_IMPL = "LoggingNotificationService"
_MARKER = "# notification (spec)"
_IMPORT_LINE = (
    "from %s import %s as %s, %s"
    % (NOTIFICATIONS_MODULE, _ABSTRACTION, _PORT_ALIAS, _LOGGING_IMPL)
)


def render_notifications_module():
    """The abstraction + the logging implementation, as one module."""
    return '''"""Notification service abstraction.

The specification asks for a notification service ABSTRACTION plus "a simple
implementation that logs the notification instead of sending a real message".
The abstraction is an ABC, so a different delivery mechanism (email, SMS) can
be supplied without touching the service that raises the notification; the
implementation provided here is the logging one the specification describes.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional


class %(abstraction)s(ABC):
    """What a notification sender must do, and nothing else."""

    @abstractmethod
    def notify(self, recipient: str, message: str) -> None:
        """Deliver ``message`` to ``recipient``."""
        raise NotImplementedError


class %(impl)s(%(abstraction)s):
    """The simple implementation: it LOGS the notification.

    Nothing is sent over a network — the specification explicitly asks for the
    notification to be logged instead of transmitted — so a run leaves a
    readable record and never depends on an external service.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger("notifications")

    def notify(self, recipient: str, message: str) -> None:
        self.logger.info("notification to %%s: %%s", recipient, message)
''' % {"abstraction": _ABSTRACTION, "impl": _LOGGING_IMPL}


def _method_def(source, name):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _find_row_var(source, method_name):
    """The local assigned from ``self.<x>_repo.get_by_id(...)``, or None."""
    node = _method_def(source, method_name)
    if node is None:
        return None
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "get_by_id"
                and isinstance(stmt.targets[0], ast.Name)
            ):
                return stmt.targets[0].id
    return None


def _ensure_import(source):
    if _IMPORT_LINE in source:
        return source
    lines = source.splitlines(keepends=True)
    last = 0
    for i, line in enumerate(lines[:80]):
        if line.startswith(("import ", "from ")):
            last = i + 1
    lines.insert(last, _IMPORT_LINE + "\n")
    return "".join(lines)


def _ensure_port(source):
    """Make the service construct the logging implementation by default."""
    if re.search(r"self\.notification_port\s*=", source):
        return source
    node = _method_def(source, "__init__")
    if node is None:
        return source
    lines = source.splitlines(keepends=True)
    # The first statement after the signature (the header may span lines).
    insert_at = node.body[0].lineno - 1
    raw = lines[insert_at]
    indent = raw[: len(raw) - len(raw.lstrip())]
    lines.insert(
        insert_at,
        "%sself.notification_port = %s()\n" % (indent, _LOGGING_IMPL),
    )
    return "".join(lines)


def _splice_notify(source, method_name, rule):
    """Insert the notification just before the method's final return."""
    if _MARKER in source:
        return source
    node = _method_def(source, method_name)
    if node is None or not node.body:
        return source
    last = node.body[-1]
    if not isinstance(last, ast.Return):
        return source
    lines = source.splitlines(keepends=True)
    idx = last.lineno - 1
    raw = lines[idx]
    indent = raw[: len(raw) - len(raw.lstrip())]
    row_var = _find_row_var(source, method_name)
    field = rule.get("recipient_field")
    if row_var and field:
        recipient = "str(%s.%s)" % (row_var, field)
    else:
        recipient = "str(%s)" % rule.get("id_param", "id")
    message = '"%s %%s" %% (%s,)' % (
        "%sed %s" % (rule["verb"], _snake_name(rule["entity"])),
        rule.get("id_param", "id"),
    )
    lines.insert(
        idx,
        "%sself.notification_port.notify(%s, %s)  %s\n"
        % (indent, recipient, message, _MARKER),
    )
    return "".join(lines)


def apply_notify_guards(source, rule):
    """Return ``source`` with the abstraction imported and the call spliced."""
    if not rule or not source:
        return source
    source = _ensure_import(source)
    source = _ensure_port(source)
    return _splice_notify(source, rule["method"], rule)
