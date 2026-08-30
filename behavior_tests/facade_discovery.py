"""Discover the real user-facing facade (CLI surface) from generated code.

This is the SECOND stage of the new "facade" tester. While
``design_extract.extract_design`` rebuilds the INTERNAL design (entities,
repos, services) to audit the code, this module discovers the USER-FACING
surface — the executable CLI — so intentions extracted from the prompt (see
``intents.py``) can be driven against it.

It handles the shapes the generator actually produces:

- **click group** (``@click.group() def cli()`` + ``@cli.command('x')``):
  inventory, expenses, library_system, multi_module.
- **click single command** (``@click.command() def main()``):
  hello_world, cli_tool.
- **bare script** (``def main()`` + ``if __name__ == "__main__"``, or an
  ``if __name__ == "__main__"`` block with no click): fallback.

For each facade we capture the entry file, how to invoke it, and the list of
commands with their options/arguments and the service method each wires to.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def _normalize_option_arg(item: ast.expr) -> str | None:
    """Return the string literal of a ``--name`` / ``-f`` / positional name."""
    if isinstance(item, ast.Constant) and isinstance(item.value, str):
        return item.value
    return None


def _flag_type_keyword(dec: ast.Call) -> tuple[str, bool, bool]:
    """Best-effort type/required/flag reading from a ``@click.option(...)``."""
    is_flag = False
    required = False
    vtype = "str"
    for kw in dec.keywords:
        if kw.arg == "type":
            # type=int -> int; type=click.Path(exists=True) -> str; type=str -> str
            t = ast.unparse(kw.value)
            m = re.search(r"\b(int|float|bool|str)\b", t)
            vtype = m.group(1) if m else "str"
        elif kw.arg == "is_flag":
            is_flag = isinstance(kw.value, ast.Constant) and bool(kw.value.value)
        elif kw.arg == "required":
            required = isinstance(kw.value, ast.Constant) and bool(kw.value.value)
    return vtype, required, is_flag


def _read_option_arg(dec: ast.Call) -> tuple[list[str], str | None]:
    """Return (raw names, destination). Raw names include '-f' and '--flag'."""
    names: list[str] = []
    for a in dec.args:
        v = _normalize_option_arg(a)
        if v:
            names.append(v)
    dest = None
    for kw in dec.keywords:
        if kw.arg == "dest" and isinstance(kw.value, ast.Constant):
            dest = str(kw.value.value)
            break
    if dest is None and names:
        # dest defaults to the first long option's name with dashes -> underscores
        long_ = next((n for n in names if n.startswith("--")), names[-1])
        dest = long_.lstrip("-").replace("-", "_")
    return names, dest


def _find_service_target(body: list[ast.stmt]) -> str | None:
    """Find the ``svc.<method>(...)`` call inside a command function body."""
    for stmt in body:
        # Direct: `result = svc.method(...)`
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        else:
            continue
        fn = call.func
        if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) \
                and fn.value.id == "svc":
            return fn.attr
    return None


def _data_keys_from_body(body: list[ast.stmt]) -> dict[str, str]:
    """Map click variable -> data-dict key, from a ``svc.method(data={...})`` call.

    The generator wires ``data={'field': click_var, ...}`` for methods whose
    signature is ``(..., data: Dict)``. This recovers the real field name
    (e.g. click var ``category`` -> data key ``category_id``) so FK/PK inference
    can match against the design.
    """
    keys: dict[str, str] = {}
    for stmt in body:
        call = None
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        if not call:
            continue
        for kw in call.keywords:
            if kw.arg != "data" or not isinstance(kw.value, ast.Dict):
                continue
            for k, v in zip(kw.value.keys, kw.value.values):
                if (isinstance(k, ast.Constant) and isinstance(k.value, str)
                        and isinstance(v, ast.Name)):
                    keys[v.id] = k.value
    return keys


def _parse_click_command(node: ast.FunctionDef) -> dict | None:
    """Parse one function that is a click command/group member."""
    opts = []
    args = []
    data_keys = _data_keys_from_body(node.body)
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        fn = dec.func
        if not (isinstance(fn, ast.Attribute) and fn.attr in ("option", "argument")):
            continue
        if fn.attr == "option":
            names, dest = _read_option_arg(dec)
            vtype, required, is_flag = _flag_type_keyword(dec)
            opt = {
                "names": names,
                "dest": dest,
                "type": vtype,
                "required": required,
                "flag": is_flag,
            }
            if dest in data_keys:
                opt["field"] = data_keys[dest]  # real field name inside the data dict
            opts.append(opt)
        elif fn.attr == "argument":
            names, dest = _read_option_arg(dec)
            vtype, _req, _fl = _flag_type_keyword(dec)
            args.append({
                "names": names,
                "dest": dest,
                "type": vtype,
                "required": True,
            })

    # command name: from @x.command('name') / @click.command('name'), else fn name
    cmd_name = node.name
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        fn = dec.func
        if isinstance(fn, ast.Attribute) and fn.attr == "command" and dec.args:
            v = _normalize_option_arg(dec.args[0])
            if v:
                cmd_name = v
                break
        elif isinstance(fn, ast.Name) and fn.id == "command" and dec.args:
            v = _normalize_option_arg(dec.args[0])
            if v:
                cmd_name = v
                break

    target = _find_service_target(node.body)
    return {
        "name": cmd_name,
        "options": opts,
        "arguments": args,
        "target": target or "",
    }


def _is_click_group(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        fn = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(fn, ast.Attribute) and fn.attr == "group":
            return True
    return False


def _is_click_command(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        fn = dec.func
        if isinstance(fn, ast.Name) and fn.id == "command":
            return True
        if isinstance(fn, ast.Attribute) and fn.attr == "command":
            return True
    return False


def _parse_click_file(path: Path) -> dict | None:
    """Parse a click-based file into facade commands. Returns None if no click."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return None

    commands = []
    has_click = False
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if _is_click_group(node):
            has_click = True
            continue  # the group body holds commands only via decorators on siblings
        if _is_click_command(node):
            has_click = True
            parsed = _parse_click_command(node)
            if parsed:
                commands.append(parsed)
    if not has_click:
        return None
    return {"entry": path.name, "kind": "click", "commands": commands}


def _parse_argparse_script(path: Path) -> dict | None:
    """Parse a plain argparse script into facade commands."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return None
    has_argparse = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in ("add_parser", "add_argument"):
                has_argparse = True
    if not has_argparse:
        return None
    # We only model a single flat command entry for an argparse script.
    return {
        "entry": path.name,
        "kind": "argparse",
        "commands": [{
            "name": "main",
            "options": [],
            "arguments": [],
            "target": "",
        }],
    }


def _parse_bare_script(path: Path) -> dict | None:
    """Parse a bare script (main() + __main__ guard) into a single command."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return None
    has_main = any(
        isinstance(n, ast.FunctionDef) and n.name == "main"
        for n in tree.body
    )
    has_guard = any(
        isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
        and ast.unparse(n.test).replace(" ", "").startswith('__name__=="__main__"')
        for n in tree.body
    )
    if not (has_main and has_guard):
        return None
    return {
        "entry": path.name,
        "kind": "script",
        "commands": [{
            "name": "main",
            "options": [],
            "arguments": [],
            "target": "",
        }],
    }


def discover_facade(project_dir: Path | str) -> dict:
    """Return the discovered user-facing facade for a generated project.

    Returns a dict ``{entry, kind, commands, invoker}``. ``invoker`` is how the
    entry point is called (``cli`` for click groups, else ``main``). An empty
    ``commands`` list means a facade was found but no commands (e.g. a bare
    printing main), or none was found.
    """
    root = Path(project_dir)

    # 1. Click group file (cli.py is the conventional generated name, but a
    #    group can live under any file — search *.py for a click group first).
    for p in sorted(root.glob("*.py")):
        parsed = _parse_click_file(p)
        if parsed and parsed["commands"]:
            is_group = _has_click_group(p)
            return {
                "entry": parsed["entry"],
                "kind": "click_group" if is_group else "click_command",
                "commands": parsed["commands"],
                "invoker": "cli" if is_group else "main",
            }
        if parsed and not parsed["commands"]:
            # A click command with no subcommands -> single command.
            is_group = _has_click_group(p)
            if not is_group:
                return {
                    "entry": parsed["entry"],
                    "kind": "click_command",
                    "commands": [{
                        "name": "main",
                        "options": [],
                        "arguments": [],
                        "target": "",
                    }],
                    "invoker": "main",
                }

    # 2. Fall back to an argparse or bare-script entry point (hello.py,
    #    csv_to_json.py, main.py).
    for p in sorted(root.glob("*.py")):
        if p.name in ("cli.py", "database.py", "models.py", "exceptions.py",
                      "__init__.py"):
            continue
        argparse_ = _parse_argparse_script(p)
        if argparse_:
            return {
                "entry": argparse_["entry"],
                "kind": "argparse",
                "commands": argparse_["commands"],
                "invoker": "main",
            }
        bare = _parse_bare_script(p)
        if bare:
            return {
                "entry": bare["entry"],
                "kind": "script",
                "commands": bare["commands"],
                "invoker": "main",
            }

    return {"entry": "", "kind": "none", "commands": [], "invoker": ""}


def _has_click_group(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return False
    return any(
        isinstance(n, ast.FunctionDef) and _is_click_group(n)
        for n in tree.body
    )
