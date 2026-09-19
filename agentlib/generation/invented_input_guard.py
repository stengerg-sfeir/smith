"""Drop an invented REQUIRED input that the code never reads (prompt 20).

Prompt 20 asks for "a report showing total sales amount and number of sales
per product" — one report over every product. The shipped command demanded an
order id:

    @sale.command('report')
    @click.option('--id', required=True, type=...)
    def sale_report(id):
        result = svc.get_sale_report(id=id)

    def get_sale_report(self, id: int) -> Dict[str, Any]:
        results = {}
        for row in self.sale_repo.list():     # 'id' is never read
            ...

so the report could not be run at all without supplying a value that changes
nothing — an input invented by the fill phase and then made mandatory.

The law needs BOTH halves to fire: the service method never reads the
parameter AND the CLI declares the matching option ``required=True``. An
optional filter is a legitimate extra (the caller may ignore it); a REQUIRED
one that the code discards is a command that cannot be used as specified. The
removal is done in the three places that must agree — the service signature,
the click option, and the callback parameter with its call argument — so the
wired program stays consistent.
"""

import ast

from agentlib.generation.click_prompts import _removal_edit
from agentlib.generation.cli_wiring import _apply_edits, _option_dest


def _params(node):
    """The parameters of a function, in signature order."""
    args = node.args
    return list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)


def _mentioned(node):
    """Every identifier named anywhere under ``node``."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            names.add(sub.attr)
        elif isinstance(sub, ast.keyword) and sub.arg:
            names.add(sub.arg)
    return names


def _unused_params(node):
    """Parameters of a method that its BODY never reads (``self`` aside)."""
    used = set()
    for statement in node.body:
        used |= _mentioned(statement)
    return [
        arg.arg for arg in _params(node)
        if arg.arg != "self" and arg.arg not in used
    ]


def _required_options(cli_tree):
    """The callback parameter of every ``required=True`` click option."""
    found = set()
    for node in ast.walk(cli_tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = (
            function.attr if isinstance(function, ast.Attribute)
            else function.id if isinstance(function, ast.Name) else None
        )
        if name != "option":
            continue
        required = any(
            keyword.arg == "required"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )
        if not required:
            continue
        strings = [
            argument.value for argument in node.args
            if isinstance(argument, ast.Constant)
            and isinstance(argument.value, str)
        ]
        dest = _option_dest(strings)
        if dest:
            found.add(dest)
    return found


def _drop_keyword_edit(node, keyword):
    """The edit deleting one keyword argument from a call.

    ``_removal_edit`` anchors the deletion on a neighbour, so it declines when
    the keyword is the call's ONLY argument — exactly the shape this law
    meets (``svc.get_sale_report(id=id)``). Deleting the keyword's own span
    then leaves the expected ``svc.get_sale_report()``.
    """
    edit = _removal_edit(node, keyword)
    if edit is not None:
        return edit
    ordered = list(node.args) + list(node.keywords)
    if len(ordered) != 1:
        return None
    if keyword.lineno != keyword.end_lineno:
        return None
    return (keyword.lineno, keyword.col_offset, keyword.lineno,
            keyword.end_col_offset, "")


def _drop_argument_edit(node, parameter):
    """The edit that deletes one parameter (with its comma) from a signature."""
    args = _params(node)
    positions = [(arg.lineno, arg.col_offset, arg.end_lineno, arg.end_col_offset)
                 for arg in args]
    names = [arg.arg for arg in args]
    if parameter not in names or len(positions) != len(names):
        return None
    index = names.index(parameter)
    line, col, end_line, end_col = positions[index]
    if line != end_line:
        return None
    if index + 1 < len(positions):
        return (line, col, line, positions[index + 1][1], "")
    if index > 0:
        return (line, positions[index - 1][3], line, end_col, "")
    # The ONLY parameter (``def sale_report(id):``): nothing to anchor the
    # comma on, so the argument's own span is deleted.
    return (line, col, line, end_col, "")


def _callback_owning(cli_tree, method):
    """The CLI function whose body calls ``<something>.<method>(...)``.

    The option to delete belongs to THIS function: several commands declare
    their own ``--id`` (``sale update --id`` next to ``sale report --id``), so
    an option looked up by name alone would be removed from the wrong command
    and the one the law is about would keep demanding its input.
    """
    for node in ast.walk(cli_tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == method
            ):
                return node
    return None


def _option_line_of(callback, parameter):
    """The line index of ``callback``'s own ``--<parameter>`` option."""
    for decorator in getattr(callback, "decorator_list", []):
        if not isinstance(decorator, ast.Call):
            continue
        function = decorator.func
        name = (
            function.attr if isinstance(function, ast.Attribute)
            else function.id if isinstance(function, ast.Name) else None
        )
        if name != "option" or decorator.lineno != decorator.end_lineno:
            continue
        strings = [
            argument.value for argument in decorator.args
            if isinstance(argument, ast.Constant)
            and isinstance(argument.value, str)
        ]
        if _option_dest(strings) == parameter:
            return decorator.lineno - 1
    return None


def _rewrite(service_source, cli_source):
    """``(service, cli, dropped)`` removing the invented mandatory inputs."""
    try:
        service_tree = ast.parse(service_source)
        cli_tree = ast.parse(cli_source)
    except SyntaxError:
        return service_source, cli_source, []
    required = _required_options(cli_tree)
    if not required:
        return service_source, cli_source, []
    dropped = []
    service_edits = []
    for node in ast.walk(service_tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for parameter in _unused_params(node):
            if parameter not in required:
                continue
            edit = _drop_argument_edit(node, parameter)
            if edit is None:
                continue
            service_edits.append(edit)
            dropped.append((node.name, parameter))
    if not dropped:
        return service_source, cli_source, []
    service_lines = service_source.split("\n")
    spliced = _apply_edits(service_lines, service_edits)
    if spliced is None:
        return service_source, cli_source, []
    service_candidate = "\n".join(spliced)
    try:
        ast.parse(service_candidate)
    except SyntaxError:
        return service_source, cli_source, []

    cli_lines = cli_source.split("\n")
    call_edits = []
    signature_edits = []
    line_deletions = set()
    for method, parameter in dropped:
        callback = _callback_owning(cli_tree, method)
        if callback is None:
            continue
        for node in ast.walk(callback):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == method
            ):
                keyword = next(
                    (keyword for keyword in node.keywords
                     if keyword.arg == parameter),
                    None,
                )
                if keyword is None:
                    continue
                edit = _drop_keyword_edit(node, keyword)
                if edit is not None:
                    call_edits.append(edit)
        if parameter in [arg.arg for arg in _params(callback)]:
            edit = _drop_argument_edit(callback, parameter)
            if edit is not None:
                signature_edits.append(edit)
        line = _option_line_of(callback, parameter)
        if line is not None:
            line_deletions.add(line)
    if not call_edits and not signature_edits and not line_deletions:
        return service_source, cli_source, []
    # Splices FIRST: a single-line edit preserves the line COUNT, so the
    # offsets still match the file they were measured on. Deleting the option
    # lines first would shift every later line by one and make the remaining
    # edits land on the wrong lines — a file that no longer parses, which this
    # function must never ship.
    edits = call_edits + signature_edits
    spliced = _apply_edits(cli_lines, edits)
    if spliced is None:
        return service_source, cli_source, []
    trimmed = [
        line for index, line in enumerate(spliced)
        if index not in line_deletions
    ]
    cli_candidate = "\n".join(trimmed)
    try:
        ast.parse(cli_candidate)
    except SyntaxError:
        return service_source, cli_source, []
    return service_candidate, cli_candidate, dropped


def _presentation_files(files, cli_files):
    """Every command-line module actually shipped, design list or not.

    The design's ``cli_files`` can name ``cli.py`` while the commands the
    program RUNS live in ``main.py`` (the entry point ``entry_of`` resolves) —
    editing the file nobody executes changes nothing. Both spellings are
    collected, from the files that really exist.
    """
    found = [path for path in (cli_files or []) if path in files]
    for path in files:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name in ("main.py", "cli.py") and path not in found:
            found.append(path)
    return found


def apply_invented_input_guards(files, service_files, cli_files):
    """Remove every invented mandatory input of this design.

    EVERY command-line module is tried (``cli.py`` and ``main.py``), because a
    design whose commands live in ``main.py`` while ``cli.py`` also exists
    would otherwise be edited in the file nobody runs. A second application is
    a no-op — the parameter is already gone from the service by then.

    ``files`` is ``{path: source}``. Returns ``(files, notes)``.
    """
    notes = []
    for service_path in service_files or []:
        for cli_path in _presentation_files(files, cli_files):
            service_source = files.get(service_path)
            cli_source = files.get(cli_path)
            if not service_source or not cli_source:
                continue
            service_candidate, cli_candidate, dropped = _rewrite(
                service_source, cli_source,
            )
            if not dropped:
                continue
            files[service_path] = service_candidate
            files[cli_path] = cli_candidate
            notes.append(
                "%s (%s): dropped %s" % (
                    service_path,
                    cli_path,
                    ", ".join("%s(%s)" % pair for pair in dropped),
                )
            )
    return files, notes
