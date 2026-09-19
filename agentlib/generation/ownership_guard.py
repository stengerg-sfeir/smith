"""Apply an ownership rule to a rendered service and CLI (palier 4, correctif E3).

Prompt 38: "A user can only read, modify or delete their own documents."

``pipeline/ownership_rules.py`` reads that sentence and names the acting class,
the protected resource and the FK recording the owner. This module turns the rule
into code:

* ``list_<resource>`` gains the acting user and returns only that user's rows;
* ``update_<resource>`` / ``delete_<resource>`` gain the acting user, load the row
  first and raise the design's permission error when it belongs to somebody else.
  The check is *prepended*, so whatever the method already did still happens — and
  happens only after the caller has been authorised;
* when the prompt also says the actor must authenticate, the acting user goes
  through the service's own ``authenticate_user`` before anything is touched;
* the CLI commands for the resource gain a required ``--user-id``, forwarded to
  the service, so the caller is identified instead of trusted.

Two facts are read from the rendered sources rather than assumed: the repository
attribute (``self.document_repo``, found in ``__init__``) and a row getter.
Prompt 38's design keeps its document loader on the *user* repository, so every
repository is searched; when none can load a row, the resource's own repository
gains a deterministic ``get_<resource>(id)`` whose table is read from that
repository's own ``FROM`` clause. A marker makes every step idempotent.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

MARKER = "# ownership (spec)"
ACTOR_PARAM = "user_id"
FALLBACK_PERMISSION = "PermissionError"
GENERIC_GETTERS = ("get_by_id", "find_by_id", "fetch_by_id")
SCOPED_COMMANDS = ("list", "update", "delete")


def _snake(name: str) -> str:
    """``Document`` -> ``document``; ``OrderLine`` -> ``order_line``."""
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _method_span(lines: List[str], name: str) -> Optional[Tuple[int, int]]:
    """First..last line index of a ``def name(`` inside a rendered class."""
    start = None
    for index, line in enumerate(lines):
        if re.match(r"\s*def\s+%s\s*\(" % re.escape(name), line):
            start = index
            break
    if start is None:
        return None
    base = len(_indent_of(lines[start]))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        if len(_indent_of(line)) <= base and re.match(r"\s*(def|class)\s", line):
            end = index
            break
    return start, end


def _paren_span(signature: str) -> Optional[Tuple[int, int]]:
    """Indexes of the ``(`` opening a parameter list and its matching ``)``.

    Matched by DEPTH from the first ``(``, so a return annotation such as
    ``-> (int, str)`` is never mistaken for the parameter list — and so the
    caller can keep whatever follows the closing parenthesis.
    """
    open_paren = signature.find("(")
    if open_paren == -1:
        return None
    depth = 0
    for index in range(open_paren, len(signature)):
        char = signature[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return open_paren, index
    return None


def _params_of(signature: str) -> List[str]:
    span = _paren_span(signature)
    if span is None:
        return []
    open_paren, close_paren = span
    names: List[str] = []
    for part in signature[open_paren + 1 : close_paren].split(","):
        part = part.strip()
        if not part or part.startswith("*"):
            continue
        name = part.split(":")[0].split("=")[0].strip()
        if name and name != "self":
            names.append(name)
    return names


def _add_param(signature: str, param: str) -> str:
    """Add a required ``param``, before any defaulted parameter.

    Whatever follows the parameter list — the ``-> ...`` return annotation — is
    preserved: the guard must not cost a method the annotation the
    specification's own contract is checked against.
    """
    span = _paren_span(signature)
    if span is None:
        return signature
    open_paren, close_paren = span
    parts = [
        part.strip()
        for part in signature[open_paren + 1 : close_paren].split(",")
    ]
    names = [part.split(":")[0].split("=")[0].strip() for part in parts if part]
    if param in names:
        return signature
    if any("=" in part for part in parts if part) and parts and parts[0] == "self":
        parts.insert(1, "%s: int" % param)
    else:
        parts.append("%s: int" % param)
    return "%s(%s)%s" % (
        signature[:open_paren],
        ", ".join(part for part in parts if part),
        signature[close_paren + 1 :],
    )


def _permission_exception(exception_names: Optional[List[str]]) -> str:
    """The design's permission error, or ``PermissionError``.

    Only a name saying "permission" (or "forbidden") qualifies: prompt 38's design
    declares ``PermissionError`` next to ``AuthenticationError`` and
    ``NotFoundError``, and one of those would announce the wrong failure.
    """
    for name in sorted(exception_names or []):
        lowered = name.lower()
        if "permission" in lowered or "forbidden" in lowered:
            return name
    return FALLBACK_PERMISSION


def _repo_attributes(service_source: str) -> Dict[str, str]:
    """Map ``document`` -> ``document_repo``, read from the rendered ``__init__``."""
    return {
        match.group(1): "%s_repo" % match.group(1)
        for match in re.finditer(r"self\.(\w+?)_repo\s*=", service_source)
    }


def _table_of(repo_source: str) -> Optional[str]:
    """The table a repository queries, read from its own ``FROM`` clause."""
    match = re.search(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", repo_source)
    return match.group(1) if match else None


def _has_getter(repo_source: str, resource_snake: str) -> Optional[str]:
    """A method of ``repo_source`` that loads one row of the resource."""
    available = set(re.findall(r"\bdef\s+(\w+)\s*\(", repo_source))
    wanted = (
        "get_%s_by_id" % resource_snake,
        "get_%s" % resource_snake,
        "find_%s_by_id" % resource_snake,
    ) + GENERIC_GETTERS
    for name in wanted:
        if name in available:
            return name
    return None


def ensure_owner_getter(
    repo_source: str, resource_snake: str
) -> Tuple[str, Optional[str]]:
    """Make sure a repository can load one row, and name the loader.

    An existing loader is reused; otherwise ``get_<resource>(<resource>_id)`` is
    appended, selecting every column of the repository's own table.
    """
    existing = _has_getter(repo_source, resource_snake)
    if existing is not None:
        return repo_source, existing
    table = _table_of(repo_source)
    if table is None:
        return repo_source, None
    method = "get_%s" % resource_snake
    key = "%s_id" % resource_snake
    body = (
        "\n\n    def %s(self, %s: int):  %s\n"
        "        with self.db.connect() as conn:\n"
        "            row = conn.execute(\n"
        "                \"SELECT * FROM %s WHERE id = ?\", (%s,)\n"
        "            ).fetchone()\n"
        "            return dict(row) if row else None\n"
    ) % (method, key, MARKER, table, key)
    return repo_source.rstrip("\n") + body, method


def _repo_stem(path: str) -> str:
    """``document_repository.py`` -> ``document``."""
    name = path.rsplit("/", 1)[-1]
    if name.endswith(".py"):
        name = name[: -len(".py")]
    if name.endswith("_repository"):
        name = name[: -len("_repository")]
    return name


def _getter_for(
    repos: Dict[str, str], service_source: str, resource_snake: str
) -> Tuple[Optional[str], Optional[str]]:
    """``(repository attribute, loader)`` the service can actually call.

    The resource's OWN repository is tried FIRST: a loader of the same name
    living on another repository is a different object. Prompt 38 keeps
    ``get_document_by_id`` on ``UserRepository`` while the service reads rows
    through ``self.document_repo``, so a bare name would emit
    ``self.document_repo.get_document_by_id`` -> ``AttributeError``. Every
    candidate is therefore paired with the attribute the service really holds
    for it (read from ``__init__``); a repository the service does not hold is
    skipped. ``(None, name)`` names a method of the service itself.
    """
    attributes = _repo_attributes(service_source)
    own = _repository_for(repos, resource_snake)
    ordered = ([own] if own else []) + [
        path for path in sorted(repos) if path != own
    ]
    for path in ordered:
        found = _has_getter(repos[path], resource_snake)
        if found is None:
            continue
        attribute = attributes.get(_repo_stem(path))
        if attribute is not None:
            return attribute, found
    for name in sorted(set(re.findall(r"\bdef\s+(\w+)\s*\(", service_source))):
        if name.startswith("get_") and resource_snake in name:
            return None, name
    return None, None


def _key_param(params: List[str], resource_snake: str) -> Optional[str]:
    """The parameter holding the row key: ``id``, else ``<resource>_id``."""
    for candidate in ("id", "%s_id" % resource_snake):
        if candidate in params:
            return candidate
    return None


def _check_prefix(
    getter: str,
    repo_attr: Optional[str],
    key_param: str,
    failure: str,
    auth_call: Optional[str],
) -> List[str]:
    """The authorisation put in front of a write.

    A rejected call must change nothing, so the row is loaded and compared before
    the method's own body runs. A missing row is left to the body: reporting "not
    found" is the body's business, not the guard's. ``repo_attr`` is ``None`` when
    the loader is a method of the service itself.
    """
    indent = "        "
    lines: List[str] = []
    if auth_call:
        lines.append("%s%s" % (indent, auth_call))
    # An empty ``repo_attr`` names a loader carried by the service itself.
    row_call = (
        "self.%s.%s(%s)" % (repo_attr, getter, key_param)
        if repo_attr
        else "self.%s(%s)" % (getter, key_param)
    )
    lines.append("%srow = %s" % (indent, row_call))
    # Compared as TEXT on both sides: the acting user reaches the service with
    # whatever type the command's own option declares (prompt 39's
    # ``--user-id`` is TEXT), while the row's owner column is an integer — an
    # ``int != str`` test would let every non-owner through.
    lines.append(
        "%sif row is not None and str(_owner_of(row)) != str(%s):"
        % (indent, ACTOR_PARAM)
    )
    lines.append(
        "%s    raise %s('you may only access your own records')"
        % (indent, failure)
    )
    return lines


def _scoped_list_body(
    body: List[str], auth_call: Optional[str], indent: str
) -> Optional[List[str]]:
    """Rewrite a list body so only the acting user's rows come back.

    The original call is kept verbatim — its ``return`` becomes a binding, so any
    filter the caller passed still applies — and only the *result* is narrowed.
    A body without ``return <expression>`` is left alone.
    """
    out: List[str] = []
    if auth_call:
        out.append("%s%s" % (indent, auth_call))
    rewritten = False
    for line in body:
        match = re.match(r"^(\s*)return\s+(.+?)\s*$", line)
        if match and not rewritten:
            out.append("%srows = %s" % (indent, match.group(2)))
            rewritten = True
            continue
        out.append(line)
    if not rewritten:
        return None
    out.append(
        "%sreturn [row for row in rows if str(_owner_of(row)) == str(%s)]"
        % (indent, ACTOR_PARAM)
    )
    return out


def apply_ownership_guards(
    service_source: str,
    repo_sources: Dict[str, str],
    rule: Dict[str, Any],
    exception_names: Optional[List[str]] = None,
) -> Tuple[str, Dict[str, str], List[str]]:
    """Return ``(service, repos, notes)`` with the ownership rule applied.

    Nothing changes when ``rule`` is empty, when the service already carries the
    marker, or when the pieces the guard needs (repository attribute, row getter,
    key parameter) cannot be found: a guard spliced onto wrong names would check
    the wrong column.
    """
    if not rule or MARKER in service_source:
        return service_source, repo_sources, []

    resource_snake = _snake(rule["resource"])
    failure = _permission_exception(exception_names)
    auth_call = (
        "self.authenticate_user(%s)" % ACTOR_PARAM
        if rule.get("auth_required")
        else None
    )

    repo_attr = _repo_attributes(service_source).get(resource_snake)
    if repo_attr is None:
        return service_source, repo_sources, []

    repos = dict(repo_sources)
    getter_attr, getter = _getter_for(repos, service_source, resource_snake)
    if getter is None:
        repo_path = _repository_for(repos, resource_snake)
        if repo_path is not None:
            source, added = ensure_owner_getter(repos[repo_path], resource_snake)
            if added is not None:
                repos[repo_path] = source
                getter_attr, getter = repo_attr, added
    if getter is None:
        return service_source, repo_sources, []

    lines = service_source.splitlines()
    notes: List[str] = []

    list_span = _method_span(lines, "list_%s" % resource_snake)
    if list_span is not None:
        start, end = list_span
        signature = _add_param(lines[start].strip().rstrip(":"), ACTOR_PARAM)
        guarded = _scoped_list_body(lines[start + 1 : end], auth_call, "        ")
        if guarded is not None:
            lines[start] = "%s%s:" % (_indent_of(lines[start]), signature)
            lines[start + 1 : end] = guarded
            notes.append("list_%s only returns the actor's rows" % resource_snake)

    for verb in ("update", "delete"):
        method = "%s_%s" % (verb, resource_snake)
        span = _method_span(lines, method)
        if span is None:
            continue
        start, end = span
        signature = _add_param(lines[start].strip().rstrip(":"), ACTOR_PARAM)
        key_param = _key_param(_params_of(signature), resource_snake)
        if key_param is None:
            continue
        lines[start] = "%s%s:" % (_indent_of(lines[start]), signature)
        lines[start + 1 : end] = _check_prefix(
            getter, getter_attr, key_param, failure, auth_call
        ) + lines[start + 1 : end]
        notes.append("%s_%s refuses non-owners" % (verb, resource_snake))

    if not notes:
        return service_source, repo_sources, []
    guarded = _with_owner_helper("\n".join(lines) + "\n", rule["owner_field"])
    return guarded, repos, notes


def _repository_for(
    repo_sources: Dict[str, str], resource_snake: str
) -> Optional[str]:
    """The repository file whose name carries the resource."""
    for path in sorted(repo_sources):
        stem = path.rsplit("/", 1)[-1].removesuffix(".py")
        if stem in ("%s_repository" % resource_snake, "%s_repo" % resource_snake):
            return path
    for path in sorted(repo_sources):
        if resource_snake in path.rsplit("/", 1)[-1]:
            return path
    return None


def _with_owner_helper(source: str, owner_field: str) -> str:
    """Add the ``_owner_of`` helper (and the marker) to a guarded service.

    Rows come back as ``dict`` from a raw query as often as a model instance.
    """
    if "_owner_of(" not in source:
        return source
    helper = (
        "\n\ndef _owner_of(row):  %s\n"
        "    if isinstance(row, dict):\n"
        "        return row.get(\"%s\")\n"
        "    return getattr(row, \"%s\", None)\n"
    ) % (MARKER, owner_field, owner_field)
    return source.rstrip("\n") + helper


def apply_ownership_cli(
    cli_source: str, rule: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """Add the acting user to the resource's CLI commands.

    ``--user-id`` becomes a required option of ``list``/``update``/``delete`` for
    the protected resource and is forwarded as ``user_id=``. An existing
    ``--user-id`` (prompt 38 offers one on ``document update``) is kept: only its
    meaning changes — it now identifies the caller instead of selecting a value to
    store. Commands are found by their ``@<group>.command('<verb>')`` decorator, so
    nothing depends on how the function itself was named.
    """
    if not rule or MARKER in cli_source:
        return cli_source, []

    resource_snake = _snake(rule["resource"])
    lines = cli_source.splitlines()
    notes: List[str] = []

    for verb in SCOPED_COMMANDS:
        header = _command_header(lines, resource_snake, verb)
        if header is None:
            continue
        option_index, function_index = header
        if ACTOR_PARAM not in _params_of(lines[function_index].strip()):
            lines.insert(
                option_index + 1,
                "@click.option('--user-id', type=int, required=True)",
            )
            function_index += 1
            lines[function_index] = _extend_signature(
                lines[function_index], ACTOR_PARAM
            )
        call_index = _call_index(lines, function_index, resource_snake, verb)
        if call_index is None:
            notes.append("%s/%s: no service call found" % (resource_snake, verb))
            continue
        lines[call_index] = _forward_actor(lines[call_index], ACTOR_PARAM)
        notes.append("%s/%s identifies its caller" % (resource_snake, verb))

    if not notes:
        return cli_source, []
    return "\n".join(lines) + "\n" + MARKER + "\n", notes


def _command_header(
    lines: List[str], resource_snake: str, verb: str
) -> Optional[Tuple[int, int]]:
    """Line indexes of ``@<group>.command('<verb>')`` and its ``def``."""
    pattern = re.compile(
        r"^@(\w+)\.command\(\s*['\"]%s['\"]\s*\)\s*$" % re.escape(verb)
    )
    for index, line in enumerate(lines):
        match = pattern.match(line.strip())
        if not match or match.group(1) != resource_snake:
            continue
        for offset in range(1, 12):
            candidate = index + offset
            if candidate >= len(lines):
                break
            if re.match(r"\s*def\s+\w+\s*\(", lines[candidate]):
                return index, candidate
    return None


def _extend_signature(signature: str, param: str) -> str:
    """Add a parameter to a plain ``def f(a, b):`` line."""
    span = _paren_span(signature)
    if span is None:
        return signature
    open_paren, close_paren = span
    parts = [
        part.strip()
        for part in signature[open_paren + 1 : close_paren].split(",")
        if part.strip()
    ]
    if param in parts:
        return signature
    parts.append(param)
    return "%s(%s)%s" % (
        signature[:open_paren],
        ", ".join(parts),
        signature[close_paren + 1 :],
    )


def _call_index(
    lines: List[str], function_index: int, resource_snake: str, verb: str
) -> Optional[int]:
    """The service call belonging to a command body.

    Anchored on the method name the CLI already uses (``list_document``), which
    keeps a call in a neighbouring function from being rewritten.
    """
    pattern = re.compile(r"\b%s_%s\s*\(" % (verb, resource_snake))
    for index in range(function_index, min(function_index + 40, len(lines))):
        if pattern.search(lines[index]) and "svc." in lines[index]:
            return index
    return None


def _forward_actor(line: str, param: str) -> str:
    """Forward the acting user to the service call on ``line``."""
    call = re.search(r"\b\w+\.\w+\s*\(", line)
    if call is None or re.search(r"\b%s\s*=" % param, line):
        return line
    open_paren = line.find("(", call.start())
    close_paren = line.rfind(")")
    if open_paren == -1 or close_paren == -1:
        return line
    inner = line[open_paren + 1 : close_paren].strip()
    forwarded = (
        "%s, %s=%s" % (inner, param, param)
        if inner else "%s=%s" % (param, param)
    )
    return "%s(%s)%s" % (
        line[:open_paren], forwarded, line[close_paren + 1 :],
    )
