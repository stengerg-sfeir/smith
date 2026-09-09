"""Deterministic click CLI renderer + application entry-point renderer.

Extracted from agent.py. A designed command becomes a flat top-level click
command wired to the designed service method; the entry-point renderer
produces a real, compilable main.py. No behaviour change.
"""
import re
from pathlib import Path

from ..naming import _camel, _snake


def _render_cli_file(design, svc_class, entities_by_class, service_methods,
                     verbose=False, db_path="app.db"):
    """Deterministic click CLI: one flat top-level command per command.

    A designed command `group=["item"], name="add"` becomes
    a flat `@click.command()` named `<group>_<name>` registered on the root
    `cli` group, wired to the designed service method with option->param
    mapping. No LLM involvement.
    """
    commands = design.get("commands") or []
    svc_snake = _snake(svc_class)
    seen_flat = set()

    lines = [
        "import click",
        "from database import Database",
        "from %s import %s" % (svc_snake, svc_class),
        "",
        'DB_PATH = "%s"' % db_path,
        "",
        "@click.group()",
        "def cli():",
        '    """Application root."""',
        "",
    ]

    for c in commands:
        if not isinstance(c, dict):
            continue
        group = c.get("group") or []
        name = c.get("name")
        if not name:
            continue
        # click registers commands under their function-name; hyphenate and give
        # the function an identifier-safe name (underscores) while click
        # exposes the hyphenated alias via the explicit @cli.command(name=...).
        # A doubled verb (["expense", "add"] + "add") collapses to the parent
        # path so the flat command is "expense-add", never "add-add"; any
        # residual collision gets a numeric suffix instead of being silently
        # overwritten by a later @cli.command registration.
        while group and group[-1] == name:
            group = group[:-1]
        leaf = group[-1] if group else ""
        flat_hyphen = "-".join([leaf, name]) if leaf else name
        if flat_hyphen in seen_flat and len(group) >= 2:
            flat_hyphen = "-".join(group + [name])
        base = flat_hyphen
        k = 2
        while flat_hyphen in seen_flat:
            flat_hyphen = "%s-%d" % (base, k)
            k += 1
        seen_flat.add(flat_hyphen)
        flat_ident = flat_hyphen.replace("-", "_")
        opts = c.get("options") or []
        target = c.get("target") or name or ""

        lines.append("@cli.command(%r)" % flat_hyphen)
        for o in opts:
            oname = o.get("name")
            if not oname:
                continue
            otype = o.get("type") or "str"
            req = "required=True" if o.get("required") else ""
            if otype == "int":
                lines.append("@click.option(%r, type=int%s)"
                             % (oname, (", " + req) if req else ""))
            elif otype == "flag":
                lines.append("@click.option(%r, is_flag=True, default=False)" % oname)
            else:
                lines.append("@click.option(%r%s)"
                             % (oname, (", " + req) if req else ""))
        pvars = ", ".join(_optvar(o) for o in opts if o.get("name"))
        lines.append("def %s(%s):" % (flat_ident, pvars))
        lines.append('    """%s"""' % "/".join(group + [name]))
        call = _build_service_call(target, opts, service_methods)
        # The service __init__ takes a Database object, not a path string.
        lines.append("    svc = %s(Database(DB_PATH))" % svc_class)
        lines.append("    " + call)
        lines.append("")

    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    cli()")
    return "\n".join(lines).rstrip() + "\n"


def _optvar(o):
    return re.sub(r"[- ]", "_", (o.get("name") or "").lstrip("-"))


def _match_param(key, params):
    """Exact match first, then bounded suffix matching (--category ->
    category_id, --price -> price_cents). The key is dash-normalized so a
    CLI option whose declared field name carries a hyphen ('from-date' ->
    'from_date') matches the snake_case service param — a '-'-vs-'_' drift
    between the LLM's CLI design and the service signature would otherwise
    leave the option unmapped and the command dropped."""
    if isinstance(key, str):
        # Mirror _optvar: strip leading dashes ('--from-date' -> 'from-date')
        # then normalize dashes AND spaces to underscores ('from date' /
        # 'from-date' -> 'from_date'), so a CLI option whose declared field
        # carries a flag prefix, hyphen, or space matches the snake_case
        # service param. Any '-'-vs-'_' / space drift between the LLM's CLI
        # design and the service signature would otherwise leave the option
        # unmapped and the command dropped.
        key = re.sub(r"[- ]", "_", key.lstrip("-"))
    if key in params:
        return key
    m = next(
        (
            p
            for p in params
            if p.startswith(key + "_") or p.endswith("_" + key)
        ),
        None,
    )
    if m:
        return m
    # FK option (--category enriched to field "category_id") may name the FK
    # column while the designed service param is the bare entity token
    # ("category"). Match the stem so a command like `budget list --category`
    # wires onto list_budget(category, ...) instead of being dropped by the
    # sanitizer for an uncovered category_id param.
    if key.endswith("_id"):
        stem = key[: -len("_id")]
        if stem in params:
            return stem
        return next(
            (
                p
                for p in params
                if p.startswith(stem + "_") or p.endswith("_" + stem)
            ),
            None,
        )
    return None


def _resolve_option_param(o, params):
    """Resolve a CLI option to a target param, trying the declared field
    first then falling back to the option-name-derived key.

    The LLM's ``field`` hint can point at a param name the target does not
    have (e.g. ``start_date`` for a service param named ``from_date``).
    Click binds values by option NAME, so if the declared field does not
    resolve onto the target, fall back to the option variable — a stray or
    misnamed ``field`` must never drop the option from the call or falsely
    reject the command.
    """
    key = o.get("field") or _optvar(o)
    m = _match_param(key, params) if params is not None else key
    if m is not None:
        return m
    if o.get("field"):
        alt = _optvar(o)
        m = _match_param(alt, params) if params is not None else alt
        if m is not None:
            return m
    return None


def _build_service_call(target, opts, service_methods):
    """Wire click options to a service method call, passing ONLY options
    that map to real parameters of the target's designed signature."""
    sig = {}
    for m in service_methods or []:
        if isinstance(m, dict) and m.get("name"):
            sig[m["name"]] = [
                p.get("name")
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
    params = sig.get(target)

    def key_of(o):
        return o.get("field") or _optvar(o)

    if params and "data" in params:
        # update-style (id, data) target: map direct params, pack every
        # other option into the data dict instead of dropping them
        parts, packed, used = [], [], set()
        for p in params:
            if p == "data":
                continue
            for o in opts:
                if (o.get("name")
                        and _resolve_option_param(o, params) == p):
                    parts.append("%s=%s" % (p, _optvar(o)))
                    used.add(o.get("field") or _optvar(o))
                    break
        for o in opts:
            if not o.get("name"):
                continue
            k = key_of(o)
            if k in used or k in params:
                continue
            used.add(k)
            packed.append("'%s': %s" % (k, _optvar(o)))
        if packed:
            parts.append("data={%s}" % ", ".join(packed))
        return "result = svc.%s(%s)" % (target, ", ".join(parts))

    kwargs, used = [], set()
    for o in opts:
        if not o.get("name"):
            continue
        key = key_of(o)
        if key in used:
            continue
        match = _resolve_option_param(o, params) if params is not None else key
        if match is None:
            continue  # option does not map to the target signature
        used.add(key)
        kwargs.append("%s=%s" % (match, _optvar(o)))
    return "result = svc.%s(%s)" % (target, ", ".join(kwargs))


def _render_main_file(files, db_file="app.db"):
    """Deterministic application entry point.

    The manifest declares a main.py entry point, but the manifest-first
    pipeline renders only exceptions/models/cli/repositories/services/
    database deterministically — a declared main.py used to fall through to
    an empty file. This renderer produces a real, compilable entry point:

      - prefers the click CLI when the layout declared one;
      - else instantiates Database + the designed service and prints a
        ready message;
      - else just initializes the database, or prints a plain message.

    Never returns an empty string, so the shipped project always has a
    runnable entry point.
    """
    if "cli.py" in files:
        return (
            '"""Application entry point."""\n'
            "from __future__ import annotations\n"
            "\n"
            "from cli import cli\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    cli()\n"
        )
    svc_files = [f for f in files if f.endswith("_service.py")]
    if svc_files:
        svc_stem = Path(svc_files[0]).stem
        svc_class = _camel(svc_stem[: -len("_service")]) + "Service"
        return (
            '"""Application entry point."""\n'
            "from __future__ import annotations\n"
            "\n"
            "from database import Database\n"
            "from %s import %s\n"
            "\n"
            'DB_PATH = "%s"\n'
            "\n"
            "def main() -> None:\n"
            '    """Initialize the application and run a smoke check."""\n'
            "    db = Database(DB_PATH)\n"
            "    svc = %s(db)\n"
            '    print("Application ready — database initialized at %s")\n'
            "\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        ) % (svc_stem, svc_class, db_file, svc_class, db_file)
    if "database.py" in files:
        return (
            '"""Application entry point."""\n'
            "from __future__ import annotations\n"
            "\n"
            "from database import Database\n"
            "\n"
            'DB_PATH = "%s"\n'
            "\n"
            "def main() -> None:\n"
            '    """Initialize the application."""\n'
            "    Database(DB_PATH)\n"
            '    print("Application ready — database initialized at %s")\n'
            "\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        ) % (db_file, db_file)
    return (
        '"""Application entry point."""\n'
        "from __future__ import annotations\n"
        "\n"
        "def main() -> None:\n"
        '    """Run the application."""\n'
        '    print("Application ready.")\n'
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
