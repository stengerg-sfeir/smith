"""Make an export write the entity's ROWS, not a summary (prompt 19).

Prompt 19 asks to "export all tasks to JSON and import tasks from JSON", with
"the import operation must validate the input before modifying the database".
The fill phase wrote an export that produces totals instead of tasks:

    {
      "total_tasks": 1,
      "completed_tasks": 0,
      "pending_tasks": 1,
      "overdue_tasks": 0
    }

Nothing in it can round-trip: the import has no tasks to read back, and the
"validate" command has nothing to validate.

The signal is the entity itself: an export whose body names NONE of the
entity's own fields cannot be writing them. The replacement body writes every
field of the design's dataclass, in JSON or CSV according to the extension —
the same convention the sibling import reads.

A body that does name the fields (however it spells its locals) is left
byte-for-byte, and the body is only built when the module already imports the
facility it needs.
"""

import ast

from agentlib.generation.import_guard import _dataclass_fields, _entity_stem


def _mentions(node, names):
    """True when any of ``names`` appears anywhere under ``node``."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in names:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in names:
            return True
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            words = (
                sub.value.replace("{", " ").replace("}", " ")
                .replace("'", " ").replace('"', " ").split()
            )
            if any(word in names for word in words):
                return True
    return False


def _rows_getter(repo_source):
    """The repository call that returns every row, as spelled by the repo."""
    if repo_source and "def get_all" in repo_source:
        return "get_all()"
    return "list()"


def _export_body(fields, stem, repo_getter, has_csv, has_json, indent):
    """The lines that write every field of every row to ``filename``."""
    variable = stem + "s"
    names = ", ".join(repr(name) for name in fields)
    lines = []
    lines.append("%s%s = self.%s_repo.%s" % (indent, variable, stem, repo_getter))
    lines.append("%sfields = [%s]" % (indent, names))
    lines.append("%srows = [" % indent)
    lines.append("%s    {name: getattr(record, name) for name in fields}"
                 % indent)
    lines.append("%s    for record in %s" % (indent, variable))
    lines.append("%s]" % indent)
    if has_csv and has_json:
        lines.append("%sif str(filename).lower().endswith('.json'):" % indent)
        lines.append("%s    with open(filename, 'w', encoding='utf-8') as handle:"
                     % indent)
        lines.append("%s        json.dump(rows, handle, indent=2, default=str)"
                     % indent)
        lines.append("%selse:" % indent)
        lines.append("%s    with open(filename, 'w', newline='', encoding='utf-8') as handle:" % indent)
        lines.append("%s        writer = csv.DictWriter(handle, fieldnames=fields)"
                     % indent)
        lines.append("%s        writer.writeheader()" % indent)
        lines.append("%s        writer.writerows(rows)" % indent)
    elif has_json:
        lines.append("%swith open(filename, 'w', encoding='utf-8') as handle:"
                     % indent)
        lines.append("%s    json.dump(rows, handle, indent=2, default=str)"
                     % indent)
    else:
        lines.append("%swith open(filename, 'w', newline='', encoding='utf-8') as handle:" % indent)
        lines.append("%s    writer = csv.DictWriter(handle, fieldnames=fields)"
                     % indent)
        lines.append("%s    writer.writeheader()" % indent)
        lines.append("%s    writer.writerows(rows)" % indent)
    lines.append("%sreturn True" % indent)
    return lines


def _rewrite(service_source, repo_source, model_source, stem):
    """``(source, applied)`` making the service's export write the rows."""
    has_csv = "import csv" in service_source
    has_json = "import json" in service_source
    if not has_csv and not has_json:
        return service_source, []
    fields = _dataclass_fields(model_source, "".join(
        part.capitalize() for part in stem.split("_")
    ))
    if not fields:
        return service_source, []
    try:
        tree = ast.parse(service_source)
    except SyntaxError:
        return service_source, []
    lines = service_source.split("\n")
    repo_getter = _rows_getter(repo_source)
    applied = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("export"):
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            continue
        if _mentions(node, set(fields)):
            continue
        def_line = lines[node.lineno - 1]
        if not def_line.rstrip().endswith(":"):
            continue
        body = _export_body(
            fields, stem, repo_getter, has_csv, has_json,
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


def apply_export_guards(files, service_files, repo_files, model_files):
    """Rewrite every export that cannot be writing the entity's rows.

    ``files`` is ``{path: source}``. Returns ``(files, notes)``.
    """
    models = "\n\n".join(
        files[path] for path in (model_files or []) if files.get(path)
    )
    repos = {
        _entity_stem(path): files[path]
        for path in (repo_files or [])
        if files.get(path)
    }
    notes = []
    for path in service_files or []:
        source = files.get(path)
        if not source:
            continue
        stem = _entity_stem(path)
        rewritten, applied = _rewrite(
            source, repos.get(stem, ""), models, stem,
        )
        if applied:
            files[path] = rewritten
            notes.append("%s: %d export method(s)" % (path, len(applied)))
    return files, notes
