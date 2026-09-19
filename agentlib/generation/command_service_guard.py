"""Wire a command to the service the design provided FOR THAT COMMAND (20).

Prompt 20 asks for "a report showing total sales amount and number of sales
per product". The manifest declared a dedicated ``sale_report_service`` whose
``SaleService.get_sale_report()`` aggregates every sale per product — and the
CLI required ``--id`` and instantiated the other, general service instead:

    # cli.py, sale report
    svc = SaleService(Database(DB_PATH))
    result = svc.get_sale_report(id=id)

    # sale_report_service.py — the module named after the command
    class SaleService:
        def get_sale_report(self) -> Dict[str, Any]:   # every product
            for row in self.sale_repo.list():
                ...

So the report could not be produced as specified. The law: when a module named
after the command (``sale report`` -> ``sale_report_service.py``) exists and
declares the called method, the command is wired to it — the class imported
under an alias, the instantiation and the call rebuilt from that method's own
parameters, and every option it does not accept removed with its callback
parameter. Nothing else about the callback changes.
"""

import ast
import re

from agentlib.generation.cli_wiring import _apply_edits, _option_dest


def _params(node):
    args = node.args
    return list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)


def _command_fragment(callback):
    """``sale_report`` for ``@sale.command('report')`` / ``def sale_report``."""
    for decorator in getattr(callback, "decorator_list", []):
        if not isinstance(decorator, ast.Call):
            continue
        function = decorator.func
        if not isinstance(function, ast.Attribute) or function.attr != "command":
            continue
        group = function.value.id if isinstance(function.value, ast.Name) else None
        if group is None:
            continue
        for argument in decorator.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                return "%s_%s" % (group, argument.value.replace("-", "_"))
    return callback.name


def _class_defining(service_source, method):
    """``(class name, parameter names)`` of the class declaring ``method``."""
    try:
        tree = ast.parse(service_source)
    except (SyntaxError, TypeError):
        return None, None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for sub in node.body:
            if isinstance(sub, ast.FunctionDef) and sub.name == method:
                return node.name, [arg.arg for arg in _params(sub)]
    return None, None


def _instantiation(callback, class_name):
    """The callback's own ``<class_name>(...)`` call, if it has one."""
    for node in ast.walk(callback):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == class_name
        ):
            return node
    return None


def _service_module(files, fragment):
    """The module the design named after the command, if it exists."""
    wanted = "%s_service.py" % fragment
    for path in files:
        if path.replace("\\", "/").rsplit("/", 1)[-1] == wanted:
            return path
    return None


def _alias_for(class_name, fragment):
    return "%s%s" % (
        class_name,
        "".join(part.capitalize() for part in fragment.split("_")),
    )


def _option_lines(callback, parameter):
    """The line indices of ``callback``'s own ``--<parameter>`` options."""
    found = []
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
            found.append(decorator.lineno - 1)
    return found


def _rewire(files, cli_path, service_path, method, callback):
    """Rewire ONE callback to the command-specific service.

    ``callback`` is the command's own callback — the one whose name matched the
    module — never a callback found again by method name, which could belong to
    a different command that happens to call a method of the same name.

    The rewiring is ALL OR NOTHING: it happens only when the callback really
    instantiates the class the module declares. Otherwise the command would keep
    the class it had while losing the keywords the new method does not accept —
    the worst of both.
    """
    cli_source = files[cli_path]
    class_name, new_params = _class_defining(files[service_path], method)
    if not class_name or new_params is None:
        return None
    if _instantiation(callback, class_name) is None:
        return None
    alias = _alias_for(class_name, _command_fragment(callback))
    edits = []
    removed = []
    dropped_keywords = set()
    for node in ast.walk(callback):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id == class_name:
            edits.append((function.lineno, function.col_offset,
                          function.lineno, function.end_col_offset, alias))
            continue
        if not (isinstance(function, ast.Attribute) and function.attr == method):
            continue
        for keyword in node.keywords:
            if keyword.arg and keyword.arg not in new_params:
                dropped_keywords.add(keyword.arg)
                edits.append((keyword.lineno, keyword.col_offset,
                              keyword.lineno, keyword.end_col_offset, ""))
    removed = sorted(dropped_keywords)
    if not edits and not removed:
        return None
    lines = cli_source.split("\n")
    spliced = _apply_edits(list(lines), edits)
    if spliced is None:
        return None
    # A removed keyword can leave `, )` or `(,` behind: the empty span must not
    # survive as a syntax error. The call is what carries them.
    cleaned = []
    for line in spliced:
        cleaned.append(
            re.sub(r"\(\s*,", "(", re.sub(r",\s*\)", ")", line))
        )
    # The callback signature loses the parameters of the removed options.
    for parameter in removed:
        for line_index, line in enumerate(cleaned):
            if line.strip().startswith("def %s(" % callback.name):
                cleaned[line_index] = re.sub(
                    r"(?<=[(,])\s*%s\b(?!\w)" % re.escape(parameter),
                    "", line, count=1,
                )
                break
    for parameter in removed:
        for line_index in _option_lines(callback, parameter):
            cleaned[line_index] = None
    cleaned = [line for line in cleaned if line is not None]
    imports = [
        line for line in cleaned[:60] if line.startswith(("import ", "from "))
    ]
    import_line = "from %s import %s as %s" % (
        service_path[:-3], class_name, alias,
    )
    if import_line not in cleaned:
        if imports:
            cleaned.insert(cleaned.index(imports[-1]) + 1, import_line)
        else:
            cleaned.insert(0, import_line)
    candidate = "\n".join(cleaned)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return None
    files[cli_path] = candidate
    return "%s: %s wired to %s" % (cli_path, method, service_path)


def apply_command_service_guards(files, cli_files):
    """Wire every command to the service module named after it.

    ``files`` is ``{path: source}``. Returns ``(files, notes)``.
    """
    notes = []
    cli_paths = [path for path in (cli_files or []) if path in files]
    if not cli_paths:
        cli_paths = [
            path for path in files
            if path.replace("\\", "/").rsplit("/", 1)[-1] == "cli.py"
        ]
    for cli_path in cli_paths:
        while True:
            source = files.get(cli_path)
            if not source:
                break
            try:
                cli_tree = ast.parse(source)
            except SyntaxError:
                break
            rewired = False
            for callback in [
                node for node in ast.walk(cli_tree)
                if isinstance(node, ast.FunctionDef)
            ]:
                methods = [
                    sub.func.attr for sub in ast.walk(callback)
                    if isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                ]
                if not methods:
                    continue
                service_path = _service_module(files, _command_fragment(callback))
                if service_path is None or service_path == cli_path:
                    continue
                for method in methods:
                    note = _rewire(files, cli_path, service_path, method,
                                   callback)
                    if note:
                        notes.append(note)
                        rewired = True
                        break
                if rewired:
                    break
            if not rewired:
                break
    return files, notes
