"""Implement an import command the fill phase left as an empty stub (18, 19).

Prompt 18 asks for "commands to export all contacts to CSV and import contacts
from CSV. Invalid rows during import must be rejected without corrupting
existing data." The fill phase wrote the export in full and reduced the import
to its stub:

    def import_contact(self, filename: str) -> List[str]:
        return []

so ``contact import --filename incoming.csv`` exited 0, said nothing, and
imported nothing — the worst possible answer, because it looks like success.

The body is rendered from the entity the service already owns: the dataclass
gives the field names and their types (which decide the coercion), the file
extension decides CSV or JSON, and the VALIDATION happens before the first
write, so a bad row can never leave the database half-updated. Every rejection
is reported in the returned list, which the CLI prints.

A stub is recognised by its body alone — a bare ``return []``/``{}``/``pass``
or a ``raise NotImplementedError`` — so an import that was actually written is
never touched. The body is only built when the module already imports the
facility it needs (``csv``/``json``); otherwise the law declines rather than
inventing an import.
"""

import ast

_STUB_CONSTANTS = ([], {}, None, "", 0, False)


def _entity_stem(path):
    """``contact_service.py`` -> ``contact``."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if name.endswith(".py"):
        name = name[: -len(".py")]
    for suffix in ("_service", "_repo", "_repository"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _camel(snake):
    return "".join(part.capitalize() for part in snake.split("_"))


def _is_stub(node):
    """True when a method body does nothing but answer with nothing."""
    if len(node.body) != 1:
        return False
    statement = node.body[0]
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Return):
        value = statement.value
        if value is None:
            return True
        if isinstance(value, ast.Constant) and value.value in _STUB_CONSTANTS:
            return True
        if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.Tuple)):
            return not getattr(value, "elts", None) and not getattr(
                value, "keys", None
            )
    if isinstance(statement, ast.Raise):
        exc = statement.exc
        name = None
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name):
            name = exc.id
        return name == "NotImplementedError"
    return False


def _dataclass_fields(source, class_name):
    """``{field: (annotation_text, has_default)}`` for one dataclass.

    The annotation decides the coercion an incoming CSV cell needs, and a
    field with no default and no ``Optional`` is the row's minimum content.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        fields = {}
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign):
                continue
            target = statement.target
            if not isinstance(target, ast.Name):
                continue
            annotation = ast.unparse(statement.annotation)
            fields[target.id] = (annotation, statement.value is not None)
        return fields
    return {}


def _kind(annotation):
    """The coercion a cell of this type needs."""
    lowered = annotation.lower()
    if "bool" in lowered:
        return "bool"
    if "int" in lowered:
        return "int"
    if "float" in lowered or "decimal" in lowered:
        return "float"
    return "str"


def _coerce_lines(kinds, indent):
    """The per-field coercion, as generated source lines."""
    lines = [indent + "if kind == 'int':"]
    lines.append(indent + "    values[name] = int(raw)")
    lines.append(indent + "elif kind == 'float':")
    lines.append(indent + "    values[name] = float(raw)")
    lines.append(indent + "elif kind == 'bool':")
    lines.append(
        indent + "    values[name] = str(raw).strip().lower() in "
        "('1', 'true', 'yes', 'y')"
    )
    lines.append(indent + "else:")
    lines.append(indent + "    values[name] = raw")
    return lines


def _reader_lines(has_csv, has_json, indent):
    """The lines that turn the opened handle into ``rows``.

    JSON and CSV are both supported when both are imported (the file's own
    extension decides, exactly as the sibling export does); a service that
    imports only one of them reads only that one, so the body never names a
    module the file does not import.
    """
    if has_csv and has_json:
        return [
            "%sif str(filename).lower().endswith('.json'):" % indent,
            "%s    rows = json.load(handle)" % indent,
            "%selse:" % indent,
            "%s    rows = list(csv.DictReader(handle))" % indent,
        ]
    if has_json:
        return ["%srows = json.load(handle)" % indent]
    return ["%srows = list(csv.DictReader(handle))" % indent]


def _import_body(class_name, fields, stem, has_csv, has_json, error_name, indent):
    """The method body that reads, validates, then writes the file's rows."""
    required = [
        name for name, (annotation, has_default) in fields.items()
        if not has_default and "Optional" not in annotation and name != "id"
    ]
    kinds = {name: _kind(annotation) for name, (annotation, _) in fields.items()}
    lines = []
    lines.append("%serrors: List[str] = []" % indent)
    lines.append("%srecords: List[%s] = []" % (indent, class_name))
    lines.append("%srequired = %r" % (indent, required))
    lines.append("%skinds = %r" % (indent, kinds))
    lines.append("%stry:" % indent)
    lines.append(
        "%s    with open(filename, newline='', encoding='utf-8') as handle:" % indent
    )
    lines.extend(_reader_lines(has_csv, has_json, indent + "        "))
    lines.append("%sexcept (OSError, ValueError) as exc:" % indent)
    lines.append("%s    raise %s('Failed to read %s data: %%s' %% (exc,))"
                 % (indent, error_name, stem))
    lines.append("%sfor number, row in enumerate(rows, start=2):" % indent)
    lines.append("%s    if not isinstance(row, dict):" % indent)
    lines.append(
        "%s        errors.append('row %%d not imported: expected an object' %% number)"
        % indent
    )
    lines.append("%s        continue" % indent)
    lines.append("%s    missing = [name for name in required if not row.get(name)]"
                 % indent)
    lines.append("%s    if missing:" % indent)
    lines.append(
        "%s        errors.append('row %%d not imported: missing %%s'"
        " %% (number, ', '.join(missing)))" % indent
    )
    lines.append("%s        continue" % indent)
    lines.append("%s    values: Dict[str, Any] = {}" % indent)
    lines.append("%s    try:" % indent)
    lines.append("%s        for name, kind in kinds.items():" % indent)
    lines.append("%s            raw = row.get(name)" % indent)
    lines.append("%s            if raw is None or raw == '':" % indent)
    lines.append("%s                continue" % indent)
    lines.extend(_coerce_lines(kinds, indent + "            "))
    lines.append("%s        records.append(%s(**values))" % (indent, class_name))
    lines.append("%s    except (TypeError, ValueError) as exc:" % indent)
    lines.append(
        "%s        errors.append('row %%d not imported: %%s' %% (number, exc))" % indent
    )
    lines.append("%sfor record in records:" % indent)
    lines.append("%s    try:" % indent)
    lines.append("%s        self.%s_repo.create(record)" % (indent, stem))
    lines.append("%s    except Exception as exc:" % indent)
    # Reported, never swallowed: the caller is TOLD which row did not land.
    lines.append(
        "%s        errors.append('row not imported: %%s' %% (exc,))" % indent
    )
    lines.append("%sreturn errors" % indent)
    return lines


def _rewrite(service_source, model_source, stem):
    """``(source, applied)`` implementing the service's stubbed import."""
    needs_csv = "import csv" in service_source
    needs_json = "import json" in service_source
    if not needs_csv and not needs_json:
        return service_source, []
    class_name = _camel(stem)
    fields = _dataclass_fields(model_source, class_name)
    if not fields:
        return service_source, []
    error_name = "ImportError" if "ImportError" in service_source else "ValueError"
    try:
        tree = ast.parse(service_source)
    except SyntaxError:
        return service_source, []
    lines = service_source.split("\n")
    applied = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("import") or not _is_stub(node):
            continue
        def_line = lines[node.lineno - 1]
        if not def_line.rstrip().endswith(":"):
            continue
        body = _import_body(
            class_name, fields, stem, needs_csv, needs_json, error_name,
            " " * (node.col_offset + 4),
        )
        applied.append((node.lineno, node.end_lineno, body))
    if not applied:
        return service_source, []
    for start, end, body in sorted(applied, reverse=True):
        lines[start:end] = body
    candidate = "\n".join(lines)
    try:
        ast.parse(candidate)
    except SyntaxError:
        return service_source, []
    return candidate, applied


def apply_import_guards(files, service_files, model_files):
    """Implement every stubbed import method of this design.

    ``files`` is ``{path: source}``. The entity's model module is looked up
    among ``model_files`` so the field names and types come from the design
    itself. Returns ``(files, notes)``.
    """
    models = "\n\n".join(
        files[path] for path in (model_files or []) if files.get(path)
    )
    notes = []
    for path in service_files or []:
        source = files.get(path)
        if not source:
            continue
        rewritten, applied = _rewrite(source, models, _entity_stem(path))
        if applied:
            files[path] = rewritten
            notes.append("%s: %d import method(s)" % (path, len(applied)))
    return files, notes
