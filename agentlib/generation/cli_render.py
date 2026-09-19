"""Deterministic click CLI renderer + application entry-point renderer.

Extracted from agent.py. A designed command becomes a flat top-level click
command wired to the designed service method; the entry-point renderer
produces a real, compilable main.py. No behaviour change.
"""
import re
from pathlib import Path

from ..naming import _camel, _snake
from .model_render import _coerce_field_default


def _method_money_keys(target, service_methods):
    """The result keys a recipe declared as money for this service method.

    A report builds its values by SUMMING a money column, so the key it
    stores them under ("total", "per_category", "monthly_totals",
    "average_monthly_spend") is not a column name and the display helper
    cannot recognise it. The recipe that built the dict declared them
    (``money_keys``), so the CLI prints through the converter with that
    table. A method that declared nothing prints exactly as before.
    """
    for m in service_methods or []:
        if isinstance(m, dict) and m.get("name") == target:
            keys = m.get("money_keys")
            if isinstance(keys, dict):
                return {
                    k: v for k, v in keys.items()
                    if isinstance(k, str) and v in ("scalar", "map")
                }
    return {}


def _render_cli_file(design, svc_class, entities_by_class, service_methods,
                     verbose=False, db_path="app.db", money=False,
                     exception_names=(), money_fields=(), spec_options=(),
                     enums=None):
    """Deterministic click CLI: one flat top-level command per command.

    A designed command `group=["item"], name="add"` becomes
    a flat `@click.command()` named `<group>_<name>` registered on the root
    `cli` group, wired to the designed service method with option->param
    mapping. No LLM involvement.
    """
    money_field_set = {
        n for n in (money_fields or ()) if isinstance(n, str)
    }
    # Option names the SPECIFICATION itself wrote. An option it named is
    # rendered EXACTLY as named: a bool option it wrote as `[--recurring]`
    # must not gain a synthesized `--no-recurring` twin, because that twin is
    # a command-line name the specification never asked for.
    spec_option_set = {
        n for n in (spec_options or ()) if isinstance(n, str)
    }
    # Field -> allowed values, declared by the specification itself
    # (``payment_method (cash/card/transfer)``). A str option bound to such a
    # field is restricted with click.Choice, so a value outside the declared
    # vocabulary is rejected instead of silently stored.
    enum_map = {
        k: list(v) for k, v in (enums or {}).items()
        if isinstance(k, str) and v
    }
    commands = design.get("commands") or []
    svc_snake = _snake(svc_class)
    used_cmds = set()
    used_idents = set()
    # Field names carrying a spec-declared default are OPTIONAL on the CLI:
    # an omitted option yields None and the deterministic add_ body
    # substitutes the declared default (is_active default True,
    # available_copies default 1). Forcing them required would make the
    # caller supply a value the spec already defaults.
    default_fields = set()
    for _ent in (entities_by_class or {}).values():
        for _f in (_ent.get("fields") or []):
            if not isinstance(_f, dict) or not _f.get("name"):
                continue
            # Same STRICT coercion the model renderer uses, so a field only
            # becomes CLI-optional when it ALSO got a real dataclass default.
            # A raw (uncoerced) check here made a bogus LLM default mark the
            # option optional while models.py rejected it and stayed
            # required — the caller then omitted it and the fill crashed on
            # None (expense_date -> fromisoformat(None)).
            if _coerce_field_default(
                _f.get("type", "str"), _f.get("default")
            ) is not None:
                default_fields.add(_f["name"])

    # Every generated CLI reads and writes through the repository layer, so a
    # user-visible UNIQUE / FOREIGN KEY violation (a duplicate isbn, an unknown
    # --author-id) must never reach the user as a raw traceback. It is caught
    # as ``IntegrityViolation``, the DOMAIN error the persistence layer raises
    # when the store refuses a write — the CLI imports NO driver. The project's
    # own DESIGNED exception classes are imported too, so the domain errors the
    # specification asks for (CategoryNotFoundError, BookNotAvailableError, …)
    # are REPORTED, not dumped. Before this, `expense add --category 999` and
    # `library member add` with a duplicate email printed a full Python
    # traceback — the opposite of the "proper error handling with custom
    # exception classes" the specification asks for. Prompts 29 and 30 make the
    # separation explicit ("repositories must contain persistence logic", "the
    # CLI ... must not access SQLite directly"), and a CLI that imports the
    # driver to name its error is reaching straight past its own layers.
    lines = [
        "import click",
        "from database import Database, IntegrityViolation",
    ]
    _exc_names = sorted({
        n for n in (exception_names or [])
        if isinstance(n, str) and n.isidentifier()
    })
    if _exc_names:
        lines.append("from exceptions import %s" % ", ".join(_exc_names))
    if money:
        # The specification's money convention is two-sided: integer cents in
        # storage, decimal amounts for DISPLAY. Import the conversion helpers
        # only for a project that asked for them, so every other CLI's output
        # stays byte-identical.
        lines.append("from money import format_result, from_decimal")
    lines += [
        "from %s import %s" % (svc_snake, svc_class),
        "",
        'DB_PATH = "%s"' % db_path,
        "",
        "@click.group()",
        "def cli():",
        '    """Application root."""',
        "",
    ]

    # Preserve the DESIGNED command TREE: group=["expense","category"],
    # name="add" is the real nested command `expense category add`. The old
    # renderer flattened it to a root-level @cli.command('category-add'),
    # discarding the group structure every spec asks for. Ancestor groups are
    # emitted on first use, root-first, so a decorator always sees its parent.
    param_types = _service_param_types(service_methods)
    group_idents = {}
    used_group_idents = {"cli"}

    def _ensure_groups(path):
        parent_ident = None
        for _i in range(1, len(path) + 1):
            sub = path[:_i]
            if sub not in group_idents:
                gident = _cli_ident(sub)
                _k = 2
                while gident in used_group_idents:
                    gident = "%s_%d" % (_cli_ident(sub), _k)
                    _k += 1
                used_group_idents.add(gident)
                if parent_ident:
                    lines.append("@%s.group(%r)" % (parent_ident, sub[-1]))
                else:
                    lines.append("@cli.group(%r)" % sub[-1])
                lines.append("def %s():" % gident)
                lines.append('    """%s commands."""' % " ".join(sub))
                lines.append("")
                group_idents[sub] = gident
            parent_ident = group_idents[sub]
        return parent_ident

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
        # A doubled verb (["expense","add"] + "add") collapses to its parent.
        while group and group[-1] == name:
            group = group[:-1]
        owner = _ensure_groups(tuple(group))
        cmd_name = name
        k = 2
        while (owner, cmd_name) in used_cmds:
            cmd_name = "%s-%d" % (name, k)
            k += 1
        used_cmds.add((owner, cmd_name))
        base_ident = _cli_ident(tuple(group) + (name,))
        flat_ident = base_ident
        k = 2
        while flat_ident in used_idents:
            flat_ident = "%s_%d" % (base_ident, k)
            k += 1
        used_idents.add(flat_ident)
        opts = c.get("options") or []
        target = c.get("target") or name or ""
        target_types = param_types.get(target) or {}

        if owner:
            lines.append("@%s.command(%r)" % (owner, cmd_name))
        else:
            lines.append("@cli.command(%r)" % cmd_name)
        for o in opts:
            oname = o.get("name")
            if not oname:
                continue
            otype = o.get("type") or "str"
            opt_key = o.get("field") or _optvar(o)
            resolved = (
                _resolve_option_param(o, list(target_types))
                if target_types else None
            )
            declared = (target_types.get(resolved) or "") if resolved else ""
            req = (
                "required=True"
                if o.get("required") and opt_key not in default_fields
                else ""
            )
            if otype == "int":
                # A cents-valued option is entered by the user as a DECIMAL
                # AMOUNT ("12.50") and converted at the call boundary by
                # ``from_decimal`` (see _build_service_call). Typing it ``int``
                # rejected the very form the specification asks for:
                # ``expense add --amount 12.50`` died in click with "invalid
                # literal for int() with base 10: '12.50'" before the
                # conversion could run. Bounded to the ``*_cents`` params the
                # money convention covers, so every other int option (an id, a
                # cent-count field with no conversion) stays an int.
                # The DECLARED money fields, not a suffix guess: the
                # specification marks ``monthly_budget (optional int, stored
                # as cents)``, so its option must read a decimal amount too.
                _money_opt = bool(
                    money and resolved
                    and (
                        resolved in money_field_set
                        or resolved.endswith("_cents")
                    )
                )
                lines.append(
                    "@click.option(%r, type=%s%s)"
                    % (
                        oname,
                        "float" if _money_opt else "int",
                        (", " + req) if req else "",
                    )
                )
            elif otype == "flag" or _is_bool_type(declared):
                # A boolean parameter must be a FLAG, whatever the design
                # declared: `--is-active` was designed as a plain string
                # option, so `member add --is-active false` stored the TEXT
                # 'false' — a row that then matched neither the active nor the
                # inactive listing, and an `is_active` that was not a bool.
                # When the field ALSO carries a declared default (is_active
                # -> True), offer the tri-state `--x/--no-x` form: an omitted
                # flag is None, so the designed default still applies (and a
                # partial update never writes a column the caller omitted).
                opt_fields = (opt_key, resolved)
                if oname in spec_option_set:
                    # The specification wrote this ONE option name. Render it
                    # as written, in its tri-state form: absent is None (so a
                    # designed default still applies and a partial update
                    # never writes a column the caller omitted), present is
                    # True. Never a second name.
                    lines.append(
                        "@click.option(%r, is_flag=True, default=None)" % oname
                    )
                elif any(f and f in default_fields for f in opt_fields):
                    lines.append(
                        "@click.option(%r, default=None)"
                        % ("%s/--no-%s" % (oname, oname.lstrip("-")))
                    )
                else:
                    lines.append(
                        "@click.option(%r, is_flag=True, default=False)" % oname
                    )
            else:
                _key = resolved if isinstance(resolved, str) else opt_key
                _choices = enum_map.get(_key) if _key else None
                if _choices:
                    lines.append(
                        "@click.option(%r, type=click.Choice(%r)%s)"
                        % (oname, list(_choices), (", " + req) if req else "")
                    )
                else:
                    lines.append("@click.option(%r%s)"
                                 % (oname, (", " + req) if req else ""))
        pvars = ", ".join(_optvar(o) for o in opts if o.get("name"))
        lines.append("def %s(%s):" % (flat_ident, pvars))
        lines.append('    """%s"""' % "/".join(group + [name]))
        call = _build_service_call(
            target, opts, service_methods, money=money,
            default_fields=default_fields, money_fields=money_field_set,
        )
        # The service __init__ takes a Database object, not a path string.
        lines.append("    svc = %s(Database(DB_PATH))" % svc_class)
        # Report, never crash: the specification's error contract IS a set of
        # custom exception classes, and a repository write can additionally
        # raise a plain IntegrityError. Both become a one-line stderr message
        # and a non-zero exit instead of a Python traceback.
        _caught = ["IntegrityViolation"] + _exc_names
        _caught_src = (
            _caught[0] if len(_caught) == 1
            else "(%s)" % ", ".join(_caught)
        )
        lines.append("    try:")
        lines.append("        " + call)
        lines.append("    except %s as exc:" % _caught_src)
        lines.append('        click.echo("Error: %s" % exc, err=True)')
        lines.append("        raise SystemExit(1)")
        # A read command must PRINT its result for the CLI to be usable (and
        # for a stdout expectation to be satisfiable). A None-returning
        # mutation stays silent.
        lines.append("    if result is not None:")
        if money:
            # Display through the cents->decimal helper: the value stays an
            # integer cent count in the database, and only its PRINTED form
            # is a decimal amount. Aggregate keys the method's recipe declared
            # as money are passed along, so a report's "total" or
            # "per_category" is converted like a named column.
            _mkeys = _method_money_keys(target, service_methods)
            if _mkeys:
                lines.append(
                    "        click.echo(format_result(result, %r))" % (_mkeys,)
                )
            else:
                lines.append("        click.echo(format_result(result))")
        else:
            lines.append("        click.echo(result)")
        lines.append("")

    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    cli()")
    return "\n".join(lines).rstrip() + "\n"


def _cli_ident(path):
    """Identifier-safe Python function name for a command/group path."""
    return (
        re.sub(r"[^0-9a-zA-Z_]", "_", "_".join(str(p) for p in path))
        or "cmd"
    )


def _optvar(o):
    return re.sub(r"[- ]", "_", (o.get("name") or "").lstrip("-"))


def _service_param_types(service_methods):
    """{method_name: {param_name: declared type}} from the designed service."""
    out = {}
    for m in service_methods or []:
        if isinstance(m, dict) and m.get("name"):
            out[m["name"]] = {
                p.get("name"): (p.get("type") or "")
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            }
    return out


def _is_bool_type(declared):
    """True when a declared parameter type is a boolean (Optional included)."""
    low = (declared or "").strip().lower()
    return low == "bool" or "bool" in low


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


def _optional_cli_option(o, default_fields):
    """True when the rendered click option may be ABSENT (None) at runtime.

    An option is optional either because the design did not mark it required,
    or because its field carries a spec-declared default (the renderer then
    drops ``required=True`` so the default can apply). In BOTH cases the
    callback receives None, so any conversion at the call boundary must be
    None-preserving.
    """
    if not o.get("required"):
        return True
    return (o.get("field") or _optvar(o)) in (default_fields or set())


def _build_service_call(target, opts, service_methods, money=False,
                        default_fields=None, money_fields=()):
    """Wire click options to a service method call, passing ONLY options
    that map to real parameters of the target's designed signature.

    When the project declares the cents/decimal money convention
    (``money``), every option bound to a ``*_cents`` parameter passes
    through ``from_decimal``: that is the boundary reading a user-supplied
    amount as integer cents. The helper returns an ``int`` UNCHANGED, so a
    cents input is never rescaled and a decimal amount is converted.
    """
    _money_names = {n for n in (money_fields or ()) if isinstance(n, str)}

    def _money_arg(param, var, optional=False):
        # A conversion at the boundary FORMATS a supplied value; it never
        # validates an absent one. An optional money option arrives as None
        # (the designed parameter is ``Optional[int] = None``), and calling
        # from_decimal(None) turned `budget update --category-id 1 --month
        # 2024-03` — ``--amount`` is optional in the specification — into a
        # raw ``decimal.InvalidOperation`` traceback, because
        # ``Decimal(str(None))`` is not a number. Keep None as None so every
        # downstream ``is not None`` guard and default applies.
        if money and isinstance(param, str) and (
            param in _money_names or param.endswith("_cents")
        ):
            if optional:
                return "None if %s is None else from_decimal(%s)" % (var, var)
            return "from_decimal(%s)" % var
        return var

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
                    parts.append("%s=%s" % (
                        p,
                        _money_arg(p, _optvar(o),
                                   _optional_cli_option(o, default_fields)),
                    ))
                    used.add(o.get("field") or _optvar(o))
                    break
        for o in opts:
            if not o.get("name"):
                continue
            k = key_of(o)
            if k in used or k in params:
                continue
            used.add(k)
            var = _optvar(o)
            if o.get("type") == "flag":
                # A click flag cannot express "explicitly False": an ABSENT
                # flag hands the callback False, indistinguishable from a
                # deliberate False. Fold it to None so the `is not None`
                # filter below treats it as "not supplied" — otherwise
                # `expense update --id 1 --description x` silently rewrote
                # is_recurring to 0 on a row that was marked recurring.
                packed.append("'%s': (%s if %s else None)" % (k, var, var))
            else:
                packed.append("'%s': %s" % (
                    k,
                    _money_arg(k, var, _optional_cli_option(o, default_fields)),
                ))
        if packed:
            # A PARTIAL update must not write the options the user did not
            # supply: click hands the callback None for an absent option, and
            # the designed ``update(id, data)`` writes every key it receives,
            # so a None overwrites a column — inventory I2 (`product update
            # --name`) sent sku=None and died on ``NOT NULL constraint failed:
            # products.sku``. Filter the None entries out so only the supplied
            # fields are written.
            parts.append(
                "data={k: v for k, v in {%s}.items() if v is not None}"
                % ", ".join(packed)
            )
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
        kwargs.append(
            "%s=%s" % (
                match,
                _money_arg(match, _optvar(o),
                           _optional_cli_option(o, default_fields)),
            )
        )
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
