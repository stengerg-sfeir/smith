"""Design schemas, deterministic validators, and inter-file feasibility.

Extracted from agent.py. The LLM emits schema-constrained JSON design
decisions; these functions define the JSON schemas, validate/normalize the
parsed design, and drop design-time infeasible repository customs before any
skeleton locks them as stubs.
"""
import re
from pathlib import Path

from .config import LLM_RETRY_TEMPERATURE
from .llm.client import _json_complete
from .naming import _camel, _snake


_MANIFEST_KINDS = (
    "exceptions", "models", "repository", "repository_interface",
    "service", "cli", "main", "other",
)

_MANIFEST_SYSTEM = (
    "You are an expert Python architect. Plan the FILE LAYOUT of a Python "
    "project from its specification. Output JSON with a \"files\" array "
    "(flat filenames like \"models.py\", no __init__.py, max 6-8 files) and "
    "a \"database_file\" string: the SQLite database filename the spec "
    "names (e.g. \"finance.db\"), or \"app.db\" when it names none. Each "
    "file entry: {\"file\", \"role\", \"kind\", \"entity\", "
    "\"imports_from\"} where kind is one of %s. \"entity\" is the "
    "snake_case domain entity the module owns — REQUIRED for repository, "
    "repository_interface, and service kinds. Preserve explicitly requested "
    "interface/implementation filenames; do not collapse them into one file. "
    "\"imports_from\" lists sibling file "
    "stems this file imports from."
) % ", ".join(_MANIFEST_KINDS)

_ROUTE_SYSTEM = (
    "You classify software specifications. Decide whether the specification "
    "describes a MULTI-MODULE project (several cooperating modules such as "
    "models, repositories, services, a CLI — a structured application) or a "
    "SINGLE-file script/tool. Output {\"mode\": \"multi\"} or "
    "{\"mode\": \"single\"}."
)

_NAME_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
_NAME_CLASS = re.compile(r"^[A-Z][A-Za-z0-9_]*$")

_IMPL_KINDS = (
    "total_in_period", "total_filtered", "export_csv", "duplicate_groups",
    "list_filtered", "sum_by_group", "count_by_group", "below_foreign_threshold",
)


def _manifest_schema():
    """Layout design schema. Files carry DECLARED metadata (kind, entity) so
    downstream phases never sniff the prompt text; `database_file` carries
    the spec's own SQLite filename so no component hardcodes one."""
    return {
        "type": "object",
        "properties": {
            "database_file": {"type": "string"},
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "role": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": list(_MANIFEST_KINDS),
                        },
                        "entity": {"type": "string"},
                        "imports_from": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["file", "role", "kind"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["files"],
        "additionalProperties": False,
    }


def _infer_manifest_kind(stem):
    """Deterministic fallback when the layout design omits `kind`."""
    if "exception" in stem:
        return "exceptions"
    if "model" in stem:
        return "models"
    if "repository" in stem and ("interface" in stem or "abstract" in stem):
        return "repository_interface"
    if stem.endswith("_repository") or stem in ("repository", "repositories"):
        return "repository"
    if stem.endswith("_service") or stem in ("service", "services"):
        return "service"
    if stem == "cli":
        return "cli"
    if stem in ("main", "app"):
        return "main"
    return "other"


def _generate_manifest(prompt_text, verbose=False):
    """Schema-constrained layout design (grammar-enforced JSON, no fences)."""
    user = "SPECIFICATION:\n%s\n\nEmit the file-layout JSON now." % prompt_text
    messages = [
        {"role": "system", "content": _MANIFEST_SYSTEM},
        {"role": "user", "content": user},
    ]
    for attempt in (0, 1):
        out_temp = 0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE
        data = _json_complete(
            messages, schema=_manifest_schema(), verbose=verbose,
            temperature=out_temp,
        )
        if isinstance(data, dict) and data.get("files"):
            return data
    return None


def _validate_manifest(data):
    """Normalize the layout design: flat filenames, declared kinds/entities,
    resolvable imports. Returns (files, db_file)."""
    db_file = str(data.get("database_file") or "").strip()
    if not re.match(r"^[\w.-]+\.db$", db_file):
        db_file = "app.db"
    cleaned = []
    for spec in data["files"]:
        original = spec.get("file") or ""
        flat = Path(original).name
        if flat == "__init__.py" or not flat.endswith(".py"):
            continue
        spec["file"] = flat
        # Declared kind wins, but an absent/"other"/invalid declaration falls
        # back to the deterministic filename inference so a mislabeled
        # models.py can never silently drop out of the design phase.
        if spec.get("kind") not in _MANIFEST_KINDS or spec["kind"] == "other":
            spec["kind"] = _infer_manifest_kind(Path(flat).stem)
        ent = spec.get("entity")
        spec["entity"] = ent.strip() if isinstance(ent, str) else ""
        spec["imports_from"] = [
            Path(d).name if "/" in d else d
            for d in spec.get("imports_from", [])
        ]
        cleaned.append(spec)
    file_stems = {Path(s["file"]).stem for s in cleaned}
    for spec in cleaned:
        spec["imports_from"] = [
            i for i in spec.get("imports_from", []) if i in file_stems
        ]
    # database.py is always generated deterministically from the model AST
    cleaned = [s for s in cleaned if Path(s["file"]).stem != "database"]
    return cleaned, db_file


def _route_schema():
    return {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["single", "multi"]}},
        "required": ["mode"],
        "additionalProperties": False,
    }


def _route_mode(prompt_text, verbose=False):
    messages = [
        {"role": "system", "content": _ROUTE_SYSTEM},
        {
            "role": "user",
            "content": "SPECIFICATION:\n%s\n\nClassify now." % prompt_text,
        },
    ]
    for attempt in (0, 1):
        out_temp = 0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE
        data = _json_complete(
            messages, schema=_route_schema(), verbose=verbose,
            temperature=out_temp,
        )
        if isinstance(data, dict) and data.get("mode") in ("single", "multi"):
            return data["mode"]
    return "single"


def _entities_schema():
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "table_name": {"type": "string"},
                        "fields": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "str", "int", "float", "bool",
                                            "date", "datetime",
                                        ],
                                    },
                                    "unique": {"type": "boolean"},
                                    "nullable": {"type": "boolean"},
                                    "default": {},
                                    "auto": {"type": "string", "enum": ["now"]},
                                    "on_delete": {
                                        "type": "string", "enum": ["cascade"]},
                                },
                                "required": ["name", "type"],
                                "additionalProperties": False,
                            },
                        },
                        "unique_together": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "list_filters": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "param": {"type": "string"},
                                    "column": {"type": "string"},
                                    "op": {
                                        "type": "string",
                                        "enum": ["eq", "gte", "lte"],
                                    },
                                },
                                "required": ["param", "column", "op"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["name", "fields"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["entities"],
        "additionalProperties": False,
    }


def _methods_schema():
    """Method design schema with an optional declarative `impl` object."""
    return {
        "type": "object",
        "properties": {
            "methods": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "params": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"},
                                },
                                "required": ["name", "type"],
                                "additionalProperties": False,
                            },
                        },
                        "returns": {"type": "string"},
                        "crud": {"type": "boolean"},
                        "calls": {"type": "array", "items": {"type": "string"}},
                        "impl": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": list(_IMPL_KINDS)},
                                "entity": {"type": "string"},
                                "value_field": {"type": "string"},
                                "date_field": {"type": "string"},
                                "period_param": {"type": "string"},
                                "granularity": {
                                    "type": "string",
                                    "enum": ["month", "year"],
                                },
                                "result_key": {"type": "string"},
                                "file_param": {"type": "string"},
                                "group_by": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "min_count": {"type": "integer"},
                            },
                            "required": ["kind"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["name", "params", "returns"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["methods"],
        "additionalProperties": False,
    }


def _exceptions_schema():
    return {
        "type": "object",
        "properties": {
            "exceptions": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["exceptions"],
        "additionalProperties": False,
    }


# --- deterministic validators (schema may be bypassed by some backends) ----

def _v_exceptions(d):
    ex = d.get("exceptions") if isinstance(d, dict) else None
    if not isinstance(ex, list):
        return ["exceptions must be an array"]
    errs = []
    for e in ex:
        if not isinstance(e, str) or not _NAME_CLASS.match(e):
            errs.append("bad exception class %r" % (e,))
    return errs


def _v_entities(d):
    ents = d.get("entities") if isinstance(d, dict) else None
    if not isinstance(ents, list) or not ents:
        return ["entities must be a non-empty array"]
    errs = []
    for ent in ents:
        if not isinstance(ent, dict):
            errs.append("entity not an object")
            continue
        name = ent.get("name")
        if not isinstance(name, str) or not _NAME_CLASS.match(name):
            errs.append("bad entity name %r" % (name,))
        tn = ent.get("table_name")
        ent["table_name"] = tn.strip() if isinstance(tn, str) else ""
        fields = ent.get("fields")
        if not isinstance(fields, list) or not fields:
            errs.append("%s: no fields" % (name,))
            continue
        for f in fields:
            if not isinstance(f, dict):
                errs.append("%s: field not an object" % (name,))
                continue
            fname, ftype = f.get("name"), f.get("type")
            if not isinstance(fname, str) or not _NAME_SNAKE.match(fname):
                errs.append("%s: bad field name %r" % (name, fname))
            if ftype not in ("str", "int", "float", "bool", "date", "datetime"):
                errs.append("%s: bad type %r for field %r" % (name, ftype, fname))
            if f.get("auto") != "now":
                f.pop("auto", None)
            if f.get("on_delete") != "cascade":
                f.pop("on_delete", None)
        lf = ent.get("list_filters")
        if lf is not None:
            if not isinstance(lf, list):
                errs.append("%s: list_filters must be an array" % (name,))
            else:
                seen_params = set()
                for spec in lf:
                    if not isinstance(spec, dict):
                        errs.append("%s: list_filter not an object" % (name,))
                        continue
                    p, c = spec.get("param"), spec.get("column")
                    op = spec.get("op")
                    if not isinstance(p, str) or not _NAME_SNAKE.match(p):
                        errs.append("%s: bad list_filter param %r" % (name, p))
                    if not isinstance(c, str) or not _NAME_SNAKE.match(c):
                        errs.append("%s: bad list_filter column %r" % (name, c))
                    elif c not in {f.get("name") for f in fields}:
                        errs.append(
                            "%s: list_filter column %r is not a field" % (name, c)
                        )
                    if op not in ("eq", "gte", "lte"):
                        errs.append("%s: bad list_filter op %r" % (name, op))
                    if isinstance(p, str) and p in seen_params:
                        errs.append("%s: duplicate list_filter param %r" % (name, p))
                    seen_params.add(p if isinstance(p, str) else "")
    return errs


# Per-kind required bindings for a declarative service `impl`.
_IMPL_REQUIRED = {
    "total_in_period": (
        "entity", "value_field", "date_field", "period_param",
        "granularity", "result_key",
    ),
    "total_filtered": ("entity", "value_field", "result_key"),
    "export_csv": ("entity", "file_param"),
    "duplicate_groups": ("entity", "group_by"),
    "list_filtered": (),
    "sum_by_group": ("entity", "value_field", "group_by"),
    "count_by_group": ("entity", "group_by"),
    "below_foreign_threshold": (
        "entity", "value_field", "ref_entity", "ref_field", "fk_field",
    ),
}


def _v_impl(m, label):
    impl = m.get("impl")
    if impl is None:
        return []
    if not isinstance(impl, dict):
        return ["%s.%s: impl must be an object" % (label, m.get("name"))]
    errs = []
    kind = impl.get("kind")
    if kind not in _IMPL_KINDS:
        errs.append("%s.%s: unknown impl kind %r" % (label, m.get("name"), kind))
        return errs
    for key in _IMPL_REQUIRED[kind]:
        v = impl.get(key)
        if v is None or v == "" or v == []:
            errs.append("%s.%s: impl.%s missing for kind %s"
                        % (label, m.get("name"), key, kind))
    ent = impl.get("entity")
    if (
        isinstance(ent, str) and ent
        and not (_NAME_SNAKE.match(ent) or _NAME_CLASS.match(ent))
    ):
        errs.append("%s.%s: impl.entity must be an identifier"
                    % (label, m.get("name")))
    ref = impl.get("ref_entity")
    if (
        isinstance(ref, str) and ref
        and not (_NAME_SNAKE.match(ref) or _NAME_CLASS.match(ref))
    ):
        errs.append("%s.%s: impl.ref_entity must be an identifier"
                    % (label, m.get("name")))
    for key in ("value_field", "date_field", "period_param", "file_param",
                "ref_field", "fk_field"):
        v = impl.get(key)
        if isinstance(v, str) and v and not _NAME_SNAKE.match(v):
            errs.append("%s.%s: impl.%s must be snake_case"
                        % (label, m.get("name"), key))
    rk = impl.get("result_key")
    if isinstance(rk, str) and rk and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rk):
        errs.append("%s.%s: impl.result_key must be an identifier"
                    % (label, m.get("name")))
    gb = impl.get("group_by")
    if isinstance(gb, list):
        for g in gb:
            if not isinstance(g, str) or not _NAME_SNAKE.match(g):
                errs.append("%s.%s: impl.group_by entries must be snake_case"
                            % (label, m.get("name")))
    mc = impl.get("min_count")
    if mc is not None and (not isinstance(mc, int) or isinstance(mc, bool) or mc < 2):
        errs.append("%s.%s: impl.min_count must be an integer >= 2"
                    % (label, m.get("name")))
    if kind == "total_in_period":
        pp = impl.get("period_param")
        ptype = next(
            (
                (p.get("type") or "")
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name") == pp
            ),
            "",
        )
        if "date" in ptype.lower():
            errs.append(
                "%s.%s: impl.period_param %r is date-typed; a period bucket "
                "must be a YYYY-MM str or a year int"
                % (label, m.get("name"), pp)
            )
    return errs


def _normalize_impl(m):
    """Rescue common formatting mistakes in a designed impl object."""
    impl = m.get("impl")
    if not isinstance(impl, dict):
        return

    def clean_ident(v, lower=False):
        v = str(v).split(":")[0].split("(")[0].strip().strip("$").strip()
        return v.lower() if lower else _snake(v)

    g = impl.get("granularity")
    if g == "monthly":
        impl["granularity"] = "month"
    elif g == "yearly":
        impl["granularity"] = "year"

    for key in ("entity", "value_field", "date_field", "period_param",
                "result_key", "file_param", "ref_entity", "ref_field",
                "fk_field"):
        if isinstance(impl.get(key), str) and impl[key]:
            impl[key] = clean_ident(
                impl[key], lower=key in ("entity", "ref_entity")
            )

    gb = impl.get("group_by")
    if isinstance(gb, list):
        impl["group_by"] = [
            clean_ident(g) for g in gb
            if isinstance(g, (str, int)) and str(g).strip()
        ]

    mc = impl.get("min_count")
    if isinstance(mc, str) and mc.strip().isdigit():
        impl["min_count"] = int(mc.strip())


def _strip_invalid_impls(d):
    """Remove impl objects that still fail shape validation after
    normalization (services/repositories designs)."""
    removed = 0
    for m in d.get("methods") or []:
        if not isinstance(m, dict) or m.get("impl") is None:
            continue
        _normalize_impl(m)
        if _v_impl(m, ""):
            del m["impl"]
            removed += 1
    return removed


def _strip_reserved_methods(d):
    """Drop designed methods literally named 'impl' (services/repositories)."""
    kept = []
    removed = 0
    for m in d.get("methods") or []:
        if isinstance(m, dict) and m.get("name") == "impl":
            removed += 1
        else:
            kept.append(m)
    d["methods"] = kept
    return removed


def _strip_invalid_list_filters(d):
    """Drop invalid list_filter declarations in-place (models design)."""
    dropped = 0
    ents = d.get("entities") if isinstance(d, dict) else None
    if not isinstance(ents, list):
        return 0
    for ent in ents:
        if not isinstance(ent, dict):
            continue
        lf = ent.get("list_filters")
        if lf is None:
            continue
        if not isinstance(lf, list):
            ent["list_filters"] = []
            dropped += 1
            continue
        fields = {
            f.get("name")
            for f in ent.get("fields") or []
            if isinstance(f, dict)
        }
        kept, seen = [], set()
        for spec in lf:
            ok = False
            if isinstance(spec, dict):
                p, c, op = spec.get("param"), spec.get("column"), spec.get("op")
                ok = (
                    isinstance(p, str) and bool(_NAME_SNAKE.match(p))
                    and isinstance(c, str) and bool(_NAME_SNAKE.match(c))
                    and c in fields
                    and op in ("eq", "gte", "lte")
                    and p not in seen
                )
                if ok:
                    seen.add(p)
            if ok:
                kept.append(spec)
            else:
                dropped += 1
        ent["list_filters"] = kept
    return dropped


def _v_methods(d, label):
    ms = d.get("methods") if isinstance(d, dict) else None
    if not isinstance(ms, list):
        return ["methods must be an array"]
    errs = []
    for m in ms:
        if not isinstance(m, dict):
            errs.append("%s: method not an object" % label)
            continue
        nm = m.get("name")
        if not isinstance(nm, str) or not _NAME_SNAKE.match(nm):
            errs.append("%s: bad method name %r" % (label, nm))
        params = m.get("params")
        if not isinstance(params, list):
            errs.append("%s.%s: params must be an array" % (label, nm))
            continue
        for p in params:
            if not isinstance(p, dict):
                errs.append("%s.%s: param not an object" % (label, nm))
                continue
            if not isinstance(p.get("name"), str) or not _NAME_SNAKE.match(p.get("name")):
                errs.append("%s.%s: bad param %r" % (label, nm, p.get("name")))
        errs.extend(_v_impl(m, label))
        calls = m.get("calls")
        if calls is not None and (
            not isinstance(calls, list)
            or not all(isinstance(call, str) and call.strip() for call in calls)
        ):
            errs.append("%s.%s: calls must be an array of non-empty strings" % (label, nm))
    return errs


# --- design-time inter-file feasibility -------------------------------------

_FEAS_VERB_TOKENS = {
    "get", "find", "list", "fetch", "all", "search", "count", "total",
    "sum", "avg", "average", "min", "max", "top", "latest", "oldest",
    "newest", "first", "last", "distinct", "grouped", "sorted", "by",
    "with", "for", "in", "and", "or", "of", "the", "low", "high",
    "lowest", "highest", "below", "above", "between", "range", "filtered",
    "matching", "like", "contains", "paginated", "pagination", "paging",
    "page", "pages", "per", "size", "number",
}

_FEAS_AGGREGATE_TOKENS = {
    "history", "summary", "stats", "statistics", "distribution", "report",
    "export", "import", "json", "csv", "value", "values", "amount",
    "amounts", "copies", "quantity", "quantities", "balance", "totals",
    "breakdown",
}

_FEAS_GENERIC_PARAMS = {
    "page", "pages", "page_size", "page_number", "per_page", "limit",
    "size", "offset", "query", "q", "search", "term", "keyword",
    "keywords", "prefix", "pattern", "domain", "json_data", "data",
    "file_path", "path", "content", "low", "high", "threshold",
    "min_value", "max_value", "start_date", "end_date", "from_date",
    "to_date", "start", "end", "value", "new_value",
}

_FEAS_DATE_CLASS_TOKENS = {
    "date", "day", "week", "month", "year", "quarter", "time", "recent",
    "recently", "overdue", "expired", "expiry", "upcoming", "activity",
    "aging",
}

_FEAS_STATE_CLASS_TOKENS = {
    "status", "state", "stage", "active", "inactive", "enabled",
    "disabled", "archived", "published", "draft", "completed", "done",
}


def _feas_entity_fields(ent):
    """{field_name: declared type} for one entity design."""
    return {
        f.get("name"): (f.get("type") or "")
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }


def _feas_token_resolves(tok, own_fields, all_classes):
    """True when `tok` can denote real data somewhere in the design."""
    if tok in own_fields or (tok + "_id") in own_fields:
        return True
    for f in own_fields:
        if f.startswith(tok + "_") or f.endswith("_" + tok):
            return True
    base = tok[:-3] if tok.endswith("_id") else tok
    sing = base[:-1] if base.endswith("s") and len(base) > 3 else base
    return any(c.lower() in (sing, base) for c in all_classes)


def _entity_token(tok, entities_by_class):
    """Return the designed entity class a param-like token references, or None."""
    core = tok
    for suf in ("_id", "_name", "_contains", "_prefix", "_pattern",
                "_substring", "_suffix", "_domain", "_min", "_max",
                "_category", "_type", "_kind", "_label", "_title"):
        if core.endswith(suf):
            core = core[: -len(suf)]
            break
    core = core[:-1] if core.endswith("s") and len(core) > 3 else core
    for cls in (entities_by_class or {}):
        lower = cls.lower()
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", cls).lower()
        if core in {lower, lower + "s", snake, snake + "s"}:
            return cls
    return None


def _is_aggregate_bound(p):
    """True for params that are aggregation boundaries (not honest-empty)."""
    return bool(
        re.match(r"^(min|max|threshold|limit|below|above|floor|ceiling)_", p)
        or p.endswith(("_threshold", "_limit", "_minimum", "_maximum",
                       "_min", "_max", "_floor", "_ceiling"))
    )


def _param_is_child_fk(p, owner_snake, entities_by_class):
    """True when `p` is the owner-FK discriminator of a child entity."""
    if p == owner_snake + "_id":
        return True
    base = p[:-3] if p.endswith("_id") else p
    return base == owner_snake or base == owner_snake + "_id"


def _param_is_other_entity_field(p, owner_model, entities_by_class):
    """True when `p` is a real field of some NON-owner entity."""
    for cls, ent in (entities_by_class or {}).items():
        if cls == owner_model:
            continue
        fnames = {f.get("name") for f in (ent.get("fields") or [])
                  if isinstance(f, dict) and f.get("name")}
        if p in fnames:
            return True
    return False


def _camel_to_snake(s):
    """OrderItem -> order_item; Post -> post; Tag -> tag."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def _repo_method_feasibility_errors(m, ent_snake, entities_by_class):
    """[] when the designed repo custom method is implementable against the
    DESIGNED schema; else human-readable reasons (for the drop log)."""
    name = m.get("name") or ""
    ent_cls = _camel(ent_snake)
    own_ent = entities_by_class.get(ent_cls) or {}
    fields = _feas_entity_fields(own_ent)
    name_tokens = {
        t[:-1] if t.endswith("s") and len(t) > 3 else t
        for t in re.split(r"_+", name)
    }
    ref_fields = dict(fields)
    for cls2, e2 in entities_by_class.items():
        if isinstance(e2, dict) and cls2.lower() in name_tokens:
            ref_fields.update(_feas_entity_fields(e2))
    types = set(fields.values())
    has_date = bool(types & {"date", "datetime"})
    has_state = (
        "bool" in types
        or any(k in n for n in fields for k in ("status", "state"))
    )
    has_text = "str" in types
    all_classes = set(entities_by_class)
    errs = []

    def _need(cond, msg):
        if not cond:
            errs.append("%s: %s" % (name, msg))

    for p in (m.get("params") or []):
        if not isinstance(p, dict):
            continue
        pn = p.get("name") or ""
        if not pn or pn in _FEAS_GENERIC_PARAMS:
            continue
        if pn.startswith("new_"):
            continue
        if re.match(r"^(start|end|from|to|min|max|begin)_?", pn) or pn.endswith(
            ("_start", "_end", "_from", "_to", "_after", "_before")
        ):
            continue
        if pn.endswith(("_ago", "_days", "_months", "_years")):
            _need(
                has_date,
                "duration param %r needs a date/datetime column but %s has "
                "none" % (pn, ent_cls),
            )
            continue
        if not _feas_token_resolves(pn, fields, all_classes):
            errs.append(
                "%s: param %r matches no designed field/entity (%s has: %s)"
                % (name, pn, ent_cls, ", ".join(sorted(fields)) or "(none)")
            )

    for tok in re.split(r"_+", name):
        if not tok or tok in _FEAS_VERB_TOKENS or tok in _FEAS_AGGREGATE_TOKENS:
            continue
        if tok in _FEAS_DATE_CLASS_TOKENS:
            _need(
                has_date
                or _feas_token_resolves(tok, fields, all_classes)
                or _feas_token_resolves(tok, ref_fields, all_classes),
                "'%s' requires a date/datetime column but %s has none"
                % (tok, ent_cls),
            )
            continue
        if tok in _FEAS_STATE_CLASS_TOKENS:
            _need(
                has_state,
                "'%s' requires a bool/status column but %s has none"
                % (tok, ent_cls),
            )
            continue
        if tok in ("query", "search", "term", "keyword", "pattern", "domain",
                   "prefix", "text"):
            _need(has_text, "search token '%s' needs a text column" % tok)
            continue
        if len(tok) >= 4 and tok.isalpha():
            _need(
                (
                    _feas_token_resolves(tok, ref_fields, all_classes)
                    or _feas_token_resolves(tok, fields, all_classes)
                ),
                "name token '%s' matches no designed field/entity"
                % tok,
            )
    return errs


# A designed repository method names a filter-combination CHAIN when it
# joins 2+ 'and' filters (get_books_with_active_loans_and_overdue_loans_
# and_low_copies_...). A single 'and' join (list_expenses_by_category_and_
# date_range) is a genuine query; only the chain is a permutation the
# project never needs.
_REPO_AND_CHAIN_RE = re.compile(r"_and_")


def _repo_and_chain_count(name):
    """Number of 'and' filter joins in a repository method name."""
    return len(_REPO_AND_CHAIN_RE.findall(name or ""))


def _feas_llm_schema():
    """Schema for the LLM repository-feasibility classifier."""
    return {
        "type": "object",
        "properties": {
            "checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string"},
                        "feasible": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": ["method", "feasible", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["checks"],
        "additionalProperties": False,
    }


_FEAS_LLM_SYSTEM = (
    "You are a Python repository feasibility checker. Decide whether each "
    "proposed repository CUSTOM method can be implemented as a SQL query "
    "against the designed data schema. A method is INFEASIBLE only when it "
    "references a column, param, or name-token that does NOT exist in the "
    "schema or its related entities. Method names are a free-form VERB + "
    "entity/filter (add_book, find_by_author, update_loan_status, "
    "get_loans_by_author_and_year) — NEVER treat the leading verb or any "
    "operation word as a field. Recognize operation verbs in ANY language "
    "(add, create, inserer, ajouter, update, modifier, supprimer, ...). Be "
    "permissive: when unsure whether a method is implementable, mark "
    "feasible=true — the downstream SQL validator catches genuinely bad "
    "columns."
)


def _llm_classify_repo_feasibility(methods, ent_snake, entities_by_class,
                                   verbose=False):
    """LLM-semantically classify repo custom methods as implementable or not.

    Replaces the brittle regex token classification (_FEAS_VERB_TOKENS,
    _FEAS_AGGREGATE_TOKENS, ...) that mis-dropped methods whose name led with
    a CRUD verb ('update_author' -> 'update' matched no field), a non-English
    verb, or a vague token ('info'). The LLM reads the schema + method names
    semantically (temp=0, schema-constrained JSON) so it is robust to language
    and to verbs-as-field false positives. Returns {method: reason} for the
    infeasible ones; {} when nothing is infeasible or the call fails (the
    permissive default keeps a designed method rather than false-dropping it).
    """
    ent_cls = _camel(ent_snake)
    ent = entities_by_class.get(ent_cls, {})
    field_lines = ", ".join(
        "%s:%s" % (f.get("name"), f.get("type"))
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    ) or "(none)"
    related = []
    for cls, e in entities_by_class.items():
        if cls == ent_cls:
            continue
        e_fields = ", ".join(
            "%s:%s" % (f.get("name"), f.get("type"))
            for f in (e.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        )
        related.append("- %s: %s" % (cls, e_fields or "(none)"))
    method_lines = "\n".join(
        "- %s(%s) -> %s" % (
            m.get("name"),
            ", ".join(
                "%s:%s" % (p.get("name"), p.get("type"))
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ),
            m.get("returns"),
        )
        for m in methods
        if isinstance(m, dict) and m.get("name")
    )
    user = (
        "SCHEMA ENTITY: %s\nFIELDS: %s\nRELATED ENTITIES:\n%s\n"
        "METHODS TO CHECK:\n%s\n"
        "For EACH method, output feasible=true/false and a short reason. "
        "Emit the decision JSON now."
        % (ent_cls, field_lines, "\n".join(related) or "(none)", method_lines)
    )
    messages = [
        {"role": "system", "content": _FEAS_LLM_SYSTEM},
        {"role": "user", "content": user},
    ]
    data = _json_complete(
        messages, schema=_feas_llm_schema(), verbose=verbose, max_tokens=1024,
    )
    if not isinstance(data, dict):
        return {}
    infeasible = {}
    for chk in data.get("checks") or []:
        if not isinstance(chk, dict):
            continue
        if chk.get("feasible") is False and chk.get("method"):
            infeasible[str(chk.get("method"))] = str(chk.get("reason") or "")
    return infeasible


def _is_join_display_overdesign(m, ent_snake, entities_by_class):
    """True when a designed repo custom is a JOIN-for-display over-design.

    A method like ``list_books_with_author_info`` returns List[Dict]/Dict
    with no params and its name JOINs a related entity for a DISPLAY column
    (``with_<entity>_info`` / ``<entity>_info`` / ``<entity>_name``). The
    owner model has no such column (author_name is an Author field, not a
    Book field), so the LLM fill either constructs Model(...) with an
    unknown kwarg (TypeError) or is reverted by the schema validator. The
    CLI/service surface serves the listing through the deterministic list()
    filter instead, so this method is unnecessary over-design. Drop it
    deterministically at design time so the renderer never reaches the
    ``reverted`` path.

    Conservative: only fires on ZERO-param, dict-returning methods whose name
    contains ``_with_`` (a JOIN marker) AND references a related designed
    entity. A param-bearing filtered listing (get_books_by_author) stays.
    """
    if not isinstance(m, dict) or not m.get("name"):
        return False
    name = m.get("name") or ""
    ret = (m.get("returns") or "").lower()
    if "dict" not in ret:
        return False
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    ]
    if params:
        return False
    if "_with_" not in name:
        return False
    ent_cls = _camel(ent_snake)
    related_snakes = {
        _snake(c) for c in entities_by_class if c != ent_cls
    }
    toks = set(re.split(r"_+", name))

    def _names_related(t):
        if t in related_snakes:
            return True
        return t.endswith("s") and t[:-1] in related_snakes

    return any(_names_related(t) for t in toks)


def _strip_infeasible_repo_methods(designs, entities_by_class, verbose=False):
    """(#1) Drop designed repository customs the LLM semantics judge infeasible
    against the DESIGNED schema (references a non-existent column/param/entity).

    Uses an LLM semantic classifier (temp=0, schema-constrained JSON, small
    prompt) rather than the brittle regex verb/field token tables, so it is
    robust to CRUD-verb name tokens, non-English verbs, and vague-but-plausible
    names. The downstream SQL-schema validator remains the deterministic
    backstop. Mutates designs in place. Returns the number dropped.
    """
    dropped = 0
    for idx, (path, kind, data) in enumerate(designs):
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        methods = data.get("methods")
        if not isinstance(methods, list) or not methods:
            continue
        # Deterministic pre-filter: drop JOIN-for-display over-design customs
        # BEFORE the LLM classifier so it never judges them and the renderer
        # never reaches the "reverted" path (list_books_with_author_info).
        kept_pre = []
        for m in methods:
            if _is_join_display_overdesign(m, ent_snake, entities_by_class):
                dropped += 1
                if verbose:
                    print(
                        "    [design] %s: pruned join-display over-design "
                        "custom %s" % (path, m.get("name"))
                    )
                continue
            kept_pre.append(m)
        methods = kept_pre
        # Persist the pruned set: `methods` is a local rebind of
        # data["methods"], so assigning `methods = kept_pre` alone never
        # updated the design — the renderer/fill would then still see the
        # pruned method and the reverted marker returned. Write the actual
        # design slot.
        data["methods"] = methods
        if not methods:
            continue
        infeasible = _llm_classify_repo_feasibility(
            methods, ent_snake, entities_by_class, verbose=verbose
        )
        if not infeasible:
            continue
        kept = []
        for m in methods:
            if not isinstance(m, dict) or not m.get("name"):
                kept.append(m)
                continue
            reason = infeasible.get(m["name"])
            if reason is None:
                kept.append(m)
                continue
            dropped += 1
            if verbose:
                print(
                    "    [design] %s: dropped infeasible custom %s "
                    "(llm: %s)" % (path, m.get("name"), reason)
                )
            continue
        data["methods"] = kept
        designs[idx] = (path, kind, data)
    return dropped


def _strip_repo_method_chains(designs, verbose=False):
    """(#2) Drop designed repository customs whose name chains 2+ 'and'
    filters — a permutation enumeration a project never needs.

    Bounded to project NEED, not a method-count cap: a single 'and' join
    (list_expenses_by_category_and_date_range) is a genuine filtered query
    and survives; only the 2+ chain is dropped. Without this, the 4B model
    enumerates every field combination on a rich FK graph (library_system's
    book_repository ~55 methods, ~40 of them get_X_with_a_and_b_and_c...),
    which bloats the fill output past the max_tokens cap. Mutates designs in
    place. Returns the number of methods dropped.
    """
    dropped = 0
    for idx, (path, kind, data) in enumerate(designs):
        if kind != "repositories" or not isinstance(data, dict):
            continue
        methods = data.get("methods")
        if not isinstance(methods, list):
            continue
        kept = []
        for m in methods:
            if not isinstance(m, dict) or not m.get("name"):
                kept.append(m)
                continue
            if _repo_and_chain_count(m.get("name")) > 1:
                dropped += 1
                if verbose:
                    print(
                        "    [design] %s: dropped combinatorial chain %s"
                        % (path, m.get("name"))
                    )
                continue
            kept.append(m)
        data["methods"] = kept
        designs[idx] = (path, kind, data)
    return dropped


_DESIGN_SYSTEMS = {
    "exceptions": (
        "You are an expert Python architect. Design the exceptions module of a "
        "Python project from its specification. Output JSON with an "
        '"exceptions" array of custom exception class names (PascalCase) the '
        "spec requires (e.g. NotFoundError, ValidationException). Only list "
        "exceptions the spec explicitly mentions."
    ),
    "models": (
        "You are an expert Python architect. Design a model (data) module from "
        'the specification. Output JSON with an "entities" array. Each entity: '
        '{"name": "PascalCase", "fields": [{"name", "type", "unique", '
        '"nullable"}]}. Types are primitives: str, int, float, bool, date, '
        'datetime. Set "unique": true for columns the spec says must be unique. '
        'Set "nullable": true for optional columns (default None), including '
        'the primary key id. When the spec names table-level uniqueness '
        '(e.g. "UNIQUE(a, b)"), fill the "unique_together" pairs of that '
        'entity. Also declare the "list_filters" of each entity: the query '
        'parameters its repository list() should accept, as {"param", '
        '"column", "op"} entries where op is "eq" (equality) or "gte"/"lte" '
        '(lower/upper bound of a range over a date-like column). Declare only '
        'filters the listing/filtering features in the spec imply; omit '
        '"list_filters" when none apply. Per field, set "auto": "now" when '
        'the spec implies the system stamps that field at creation time '
        '(e.g. a created_at timestamp); omit "auto" otherwise. Per field, '
        'set "default": <value> WHEN THE SPEC DECLARES A DEFAULT for that '
        'field (e.g. "available_copies (default 1)" -> "default": 1, '
        '"is_active (default True)" -> "default": true), using the same '
        'primitive type as the field; omit "default" when the spec names '
        'none. Set '
        '"table_name" on an entity ONLY when its natural plural is '
        'irregular (e.g. Person -> people, Child -> children); omit it for '
        'regular plurals. Do not invent fields the spec does not imply.'
    ),
    "repositories": (
        "You are an expert Python architect. Design the CUSTOM methods of a "
        "data-access (repository) module. Basic CRUD (create/get_by_id/"
        "list/update/delete) is generated automatically, so do NOT list it. "
        'Output JSON with a "methods" array of the project-specific methods '
        "the spec needs (filters, totals, reports). Each method: "
        '{"name", "params": [{"name", "type"}], "returns"}. Use "" for no '
        "params or returns. A \"returns\" type must be a primitive "
        "(int/float/str/bool/date/datetime), a container of them "
        '("Optional[...]", "List[...]", "Dict[...]"), a designed model or '
        "exception class, or \"Any\" — never invent an undefined class. A "
        "domain status/state value (on_track/warning/exceeded, ...) should "
        "be a str (or a bool for a yes/no result), never an invented class. "
        "When a method is a pure filtered listing whose params all map to "
        "this entity's declared list_filters, add "
        '{"impl": {"kind": "list_filtered"}} so its body is generated '
        "deterministically."
    ),
    "services": (
        "You are an expert Python architect. Design a service module that "
        "holds the BUSINESS LOGIC of the project. Output JSON with a "
        '"methods" array. Each method: {"name", "params": [{"name", "type"}], '
        '"returns"}. Use "Optional[T]"/"List[T]"/"Dict" for shapes. A '
        '"returns" type must be a primitive (int/float/str/bool/date/datetime), '
        'a container of them ("Optional[...]", "List[...]", "Dict[...]"), a '
        'designed model/exception class, or "Any" — never invent an undefined '
        'class. A domain status/state value (on_track/warning/exceeded, ...) '
        "should be a str (or a bool for a yes/no result), never an invented "
        'class. Use the '
        "exact field names and exceptions from the spec. One method per use "
        'case the spec describes. Use "" for no params or returns. '
        "When a use case matches one of these mechanical shapes, add an "
        '"impl" object to that method: every method that totals a numeric '
        "field, exports rows to a CSV file, or finds repeated rows MUST "
        "carry impl so its body is generated deterministically: "
        '{"kind": "total_in_period", "entity": "<entity snake_case>", '
        '"value_field": "<numeric field>", "date_field": "<date-like field>", '
        '"period_param": "<param holding a YYYY-MM month or a YYYY year>", '
        '"granularity": "month"|"year", "result_key": "<dict key for the '
        'total>"} (total over one period bucket; pick a short snake_case '
        "result_key naming the total, like total_spent); "
        '{"kind": "total_filtered", "entity": ..., "value_field": ..., '
        '"result_key": ...} (total over rows filtered by the params of this '
        "method that match the declared list_filters of the entity); "
        '{"kind": "export_csv", "entity": ..., "file_param": "<param receiving '
        'the output file path>"} (write filtered rows as CSV); '
        '{"kind": "duplicate_groups", "entity": ..., "group_by": ["<field>", '
        '...], "min_count": 2} (rows sharing the same group_by values, '
        "repeated occurrences); "
        '{"kind": "sum_by_group", "entity": ..., "value_field": ..., '
        '"group_by": ["<field>", ...]} (sum of value_field grouped by the '
        "group_by fields, one dict entry per group); "
        '{"kind": "below_foreign_threshold", "entity": ..., '
        '"value_field": "<numeric field of entity>", "ref_entity": '
        '"<related entity snake_case>", "ref_field": "<threshold field on '
        'the related entity>", "fk_field": "<foreign-key column on entity '
        'pointing at ref_entity>"} (rows whose value_field is strictly '
        "below the related row's ref_field, joined through fk_field). "
        "impl bindings must reference EXACTLY the entity/field/param names "
        "already designed; entity is the snake_case name of a designed "
        "entity. Methods that match none of these shapes get no impl."
    ),
}
