"""Apply a role/authorisation rule to a rendered service and CLI (E4).

Prompt 39: "Administrators can manage products and users. Normal users can
create orders and view their own orders but cannot modify products or other
users."

``pipeline/role_rules.py`` reads that policy and names the acting class, the
column carrying its role, and which entity operations only an administrator
may perform. This module turns the rule into code:

* every admin-only command gains a required ``--actor-id``, forwarded to the
  service, so the caller is identified instead of trusted;
* the service loads the caller's own row and refuses the write unless its role
  is an administrator value, raising the design's own authorisation exception;
* ``update_<actor>`` is the one exception the specification writes down — a
  normal user "cannot modify ... *other* users" — so a refusal there happens
  only when the target row belongs to somebody else.

The acting repository attribute (``self.user_repo``) and its row getter are
read from the rendered source rather than assumed, and the refusal exception is
imported into the service when the design did not import it already. A marker
makes every step idempotent.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from agentlib.generation.ownership_guard import (
    FALLBACK_PERMISSION,
    _add_param,
    _call_index,
    _command_header,
    _extend_signature,
    _forward_actor,
    _indent_of,
    _method_span,
    _params_of,
    _repo_attributes,
)

MARKER = "# roles (spec)"
ACTOR_PARAM = "actor_id"
ADMIN_ONLY_MESSAGE = "administrators only"
OWN_ROW_MESSAGE = "you may only modify your own account"
UNKNOWN_CALLER_MESSAGE = "the caller does not exist"

# The prompt's operation -> the method-name prefixes the renderer uses.
_METHOD_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "add": ("add_%s", "create_%s"),
    "update": ("update_%s", "modify_%s"),
    "delete": ("delete_%s", "remove_%s"),
}


def _snake(name: str) -> str:
    """``Document`` -> ``document``; ``OrderLine`` -> ``order_line``."""
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def _refusal_exception(exception_names: Optional[List[str]]) -> str:
    """The design's authorisation error, or ``PermissionError``.

    Ranked by MEANING rather than alphabetically: a design declaring both
    ``PermissionDeniedError`` and ``UnauthorizedError`` gets the one that names
    a refusal of permission. A name saying "unauthorised" still beats the
    generic fallback — it is the design's own word for this failure.
    """
    for needle in ("permission", "forbidden", "denied", "unauthor", "access"):
        for name in sorted(exception_names or []):
            if needle in name.lower():
                return name
    return FALLBACK_PERMISSION


def _role_of_helper(role_field: str) -> str:
    """The module-level ``_role_of`` helper (a row may be a dict or an object)."""
    return (
        "\n\ndef _role_of(row):  %s\n"
        "    if isinstance(row, dict):\n"
        "        return str(row.get(\"%s\") or \"\")\n"
        "    return str(getattr(row, \"%s\", \"\") or \"\")\n"
    ) % (MARKER, role_field, role_field)


def _ensure_exception_import(source: str, name: str) -> str:
    """Make sure ``name`` is importable in ``source``.

    A rendered service imports the design's exception module, but a name the
    renderer never needed before the guard was spliced in would be missing —
    and a guard that raises an undefined name is worse than no guard at all.
    The import is added after the last TOP-LEVEL import, so it can never land
    inside a function or after the class body.
    """
    if re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name), source):
        return source
    lines = source.split("\n")
    last_import = -1
    for index, line in enumerate(lines):
        if line.startswith((" ", "\t")):
            continue
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            last_import = index
        elif stripped.startswith(("class ", "def ", "@")):
            break
    if last_import == -1:
        return source
    lines.insert(last_import + 1, "from exceptions import %s" % name)
    return "\n".join(lines)


def _actor_getter(
    repo_sources: Optional[Dict[str, str]], actor_snake: str
) -> str:
    """The loader of ONE actor row, read from the actor's own repository.

    Restricted to ``<actor>_repository``: every rendered repository has a
    ``get_by_id``, but a same-named loader on ANOTHER repository would be called
    on the acting attribute and raise ``AttributeError``.
    """
    for path in sorted(repo_sources or {}):
        stem = path.rsplit("/", 1)[-1].removesuffix(".py")
        if stem not in ("%s_repository" % actor_snake, "%s_repo" % actor_snake):
            continue
        available = set(
            re.findall(r"\bdef\s+(\w+)\s*\(", (repo_sources or {})[path])
        )
        for name in ("get_%s_by_id" % actor_snake, "get_by_id", "find_by_id"):
            if name in available:
                return name
    return "get_by_id"


def _own_row_key(params: List[str], entity_snake: str) -> str:
    """The parameter naming the row being updated: ``id``, else ``<e>_id``."""
    for candidate in ("id", "%s_id" % entity_snake):
        if candidate in params:
            return candidate
    return "id"


def _guard_prefix(
    verb: str,
    entity_snake: str,
    actor_snake: str,
    repo_attr: str,
    getter: str,
    admin_values: List[str],
    failure: str,
    params: List[str],
    own_row: bool,
) -> List[str]:
    """The authorisation put in front of a gated write.

    A refused call must change nothing, so the caller is loaded and its role
    checked BEFORE the method's own body runs. The one specification-stated
    exception is ``update`` on the acting class itself: "cannot modify ...
    other users" leaves a user's own account modifiable.
    """
    prefix = ["        actor = self.%s.%s(%s)" % (repo_attr, getter, ACTOR_PARAM)]
    allowed = ", ".join(repr(value) for value in admin_values)
    if verb == "update" and own_row and entity_snake == actor_snake:
        key = _own_row_key(params, entity_snake)
        prefix.append("        if actor is None:")
        prefix.append(
            "            raise %s('%s')" % (failure, UNKNOWN_CALLER_MESSAGE)
        )
        prefix.append(
            "        if _role_of(actor).lower() not in (%s,) and %s != %s:"
            % (allowed, key, ACTOR_PARAM)
        )
        prefix.append("            raise %s('%s')" % (failure, OWN_ROW_MESSAGE))
        return prefix
    prefix.append(
        "        if actor is None or _role_of(actor).lower() not in (%s,):"
        % allowed
    )
    prefix.append("            raise %s('%s')" % (failure, ADMIN_ONLY_MESSAGE))
    return prefix


def apply_role_guards(
    service_source: str,
    rule: Dict[str, Any],
    exception_names: Optional[List[str]] = None,
    repo_sources: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    """Return ``(service, notes)`` with the role rule applied.

    Nothing changes when ``rule`` is empty, when the service already carries the
    marker, when it does not hold the acting repository, or when it carries none
    of the gated operations: a guard spliced onto wrong names would test the
    wrong thing.
    """
    if not rule or MARKER in service_source:
        return service_source, []

    actor = rule.get("actor")
    role_field = rule.get("role_field")
    admin_values: List[str] = [
        str(value) for value in (rule.get("admin_values") or ["admin"])
    ]
    restricted = rule.get("restricted") or {}
    own_row = bool(rule.get("own_row"))
    if not actor or not role_field or not restricted:
        return service_source, []

    actor_snake = _snake(str(actor))
    repo_attr = _repo_attributes(service_source).get(actor_snake)
    if repo_attr is None:
        return service_source, []

    getter = _actor_getter(repo_sources, actor_snake)
    failure = _refusal_exception(exception_names)

    lines = service_source.splitlines()
    notes: List[str] = []

    for entity, verbs in sorted(restricted.items()):
        entity_snake = _snake(str(entity))
        for verb in verbs:
            for template in _METHOD_PREFIXES.get(str(verb), ()):
                method = template % entity_snake
                span = _method_span(lines, method)
                if span is None:
                    continue
                start, end = span
                signature = _add_param(
                    lines[start].strip().rstrip(":"), ACTOR_PARAM
                )
                lines[start] = "%s%s:" % (_indent_of(lines[start]), signature)
                prefix = _guard_prefix(
                    str(verb), entity_snake, actor_snake, repo_attr, getter,
                    admin_values, failure, _params_of(signature), own_row,
                )
                lines[start + 1 : end] = prefix + lines[start + 1 : end]
                notes.append("%s requires an administrator" % method)
                break

    if not notes:
        return service_source, []

    guarded = _ensure_exception_import("\n".join(lines) + "\n", failure)
    guarded = guarded.rstrip("\n") + _role_of_helper(str(role_field))
    return guarded, notes


def apply_role_cli(
    cli_source: str, rule: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """Add the acting caller to the administrator-only commands.

    ``--actor-id`` becomes a required option of the gated commands and is
    forwarded to the service. Commands are found by their
    ``@<group>.command('<verb>')`` decorator with the group equal to the
    entity, so nothing depends on how the function itself was named.
    """
    if not rule or MARKER in cli_source:
        return cli_source, []
    restricted = rule.get("restricted") or {}
    if not restricted:
        return cli_source, []

    lines = cli_source.splitlines()
    notes: List[str] = []

    for entity, verbs in sorted(restricted.items()):
        group = _snake(str(entity))
        for verb in verbs:
            header = _command_header(lines, group, str(verb))
            if header is None:
                continue
            option_index, function_index = header
            if ACTOR_PARAM not in _params_of(lines[function_index].strip()):
                lines.insert(
                    option_index + 1,
                    "@click.option('--actor-id', type=int, required=True)",
                )
                function_index += 1
                lines[function_index] = _extend_signature(
                    lines[function_index], ACTOR_PARAM
                )
            call_index = _call_index(lines, function_index, group, str(verb))
            if call_index is None:
                notes.append("%s/%s: no service call found" % (group, verb))
                continue
            lines[call_index] = _forward_actor(lines[call_index], ACTOR_PARAM)
            notes.append("%s/%s identifies its caller" % (group, verb))

    if not notes:
        return cli_source, []
    return "\n".join(lines) + "\n" + MARKER + "\n", notes
