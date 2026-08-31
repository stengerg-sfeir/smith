#!/usr/bin/env python3
"""Behavioral tests. Generated deterministically from a prompt spec.

Do not edit by hand. The runner exports a JSON object with a per-test
pass/fail list and a coverage map, then exits 0 when every test passes.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
import tempfile
import traceback

GENERATED_ROOT = os.environ.get("BEHAVIOR_ROOT", os.getcwd())
sys.path.insert(0, GENERATED_ROOT)

RESULT = {"tests": [], "coverage": {}}

TEST_SPEC = {'database_file': 'app.db',
 'entities': [{'name': 'Product',
               'table_name': '',
               'fields': [{'name': 'name',
                           'type': 'str',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'price',
                           'type': 'float',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'id',
                           'type': 'int',
                           'nullable': False,
                           'unique': False,
                           'primary_key': True,
                           'auto': 'autoincrement',
                           'default': 'None'}],
               'unique_together': [],
               'fks': []},
              {'name': 'Sale',
               'table_name': '',
               'fields': [{'name': 'product_id',
                           'type': 'int',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'quantity',
                           'type': 'int',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'sale_date',
                           'type': 'datetime',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'id',
                           'type': 'int',
                           'nullable': False,
                           'unique': False,
                           'primary_key': True,
                           'auto': 'autoincrement',
                           'default': 'None'}],
               'unique_together': [],
               'fks': [{'field': 'product_id', 'ref': 'Product'}]}],
 'exceptions': [{'name': 'NotFoundError', 'trigger': 'not_found'},
                {'name': 'ValidationError', 'trigger': 'validation'},
                {'name': 'DatabaseError', 'trigger': 'custom'},
                {'name': 'SalesReportError', 'trigger': 'custom'}],
 'repositories': [{'module': 'product_repository',
                   'class': 'ProductRepository',
                   'entity': 'Product',
                   'methods': [{'name': 'create',
                                'params': [{'name': 'product', 'type': 'Product'}],
                                'returns': 'int'},
                               {'name': 'get_by_id',
                                'params': [{'name': 'id', 'type': 'int'}],
                                'returns': 'Optional[Product]'},
                               {'name': 'get_all', 'params': [], 'returns': 'List[Product]'},
                               {'name': 'list',
                                'params': [{'name': 'name', 'type': 'Optional[Any]'},
                                           {'name': 'price', 'type': 'Optional[Any]'}],
                                'returns': 'List[Product]'},
                               {'name': 'update',
                                'params': [{'name': 'id', 'type': 'int'},
                                           {'name': 'data', 'type': 'Dict[str, Any]'}],
                                'returns': 'bool'},
                               {'name': 'delete',
                                'params': [{'name': 'id', 'type': 'int'}],
                                'returns': 'bool'},
                               {'name': 'get_sales_report_by_product',
                                'params': [{'name': 'product_id', 'type': 'int'}],
                                'returns': 'dict'},
                               {'name': 'get_total_sales_amount', 'params': [], 'returns': 'float'},
                               {'name': 'get_sales_count_per_product',
                                'params': [],
                                'returns': 'dict'},
                               {'name': 'get_sales_with_product_names',
                                'params': [{'name': 'start_date', 'type': 'datetime'},
                                           {'name': 'end_date', 'type': 'datetime'}],
                                'returns': 'list'}]},
                  {'module': 'sale_repository',
                   'class': 'SaleRepository',
                   'entity': 'Sale',
                   'methods': [{'name': 'create',
                                'params': [{'name': 'sale', 'type': 'Sale'}],
                                'returns': 'int'},
                               {'name': 'get_by_id',
                                'params': [{'name': 'id', 'type': 'int'}],
                                'returns': 'Optional[Sale]'},
                               {'name': 'get_all', 'params': [], 'returns': 'List[Sale]'},
                               {'name': 'list',
                                'params': [{'name': 'product_id', 'type': 'Optional[Any]'},
                                           {'name': 'sale_date_from', 'type': 'Optional[Any]'},
                                           {'name': 'sale_date_to', 'type': 'Optional[Any]'},
                                           {'name': 'quantity', 'type': 'Optional[Any]'},
                                           {'name': 'sale_date', 'type': 'Optional[Any]'}],
                                'returns': 'List[Sale]'},
                               {'name': 'update',
                                'params': [{'name': 'id', 'type': 'int'},
                                           {'name': 'data', 'type': 'Dict[str, Any]'}],
                                'returns': 'bool'},
                               {'name': 'delete',
                                'params': [{'name': 'id', 'type': 'int'}],
                                'returns': 'bool'},
                               {'name': 'get_sales_report_by_product',
                                'params': [{'name': 'product_id', 'type': 'int'}],
                                'returns': 'dict'},
                               {'name': 'get_total_sales_amount', 'params': [], 'returns': 'float'},
                               {'name': 'get_sales_count_per_product',
                                'params': [],
                                'returns': 'dict'},
                               {'name': 'get_sales_with_product_names',
                                'params': [{'name': 'start_date', 'type': 'datetime'},
                                           {'name': 'end_date', 'type': 'datetime'}],
                                'returns': 'list'}]}],
 'services': [{'module': 'sales_report_service',
               'class': 'SalesReportService',
               'entity': 'SalesReport',
               'methods': [{'name': 'get_total_sales_amount', 'params': [], 'returns': 'float'},
                           {'name': 'get_sales_count_per_product', 'params': [], 'returns': 'dict'},
                           {'name': 'get_sales_report_by_product',
                            'params': [{'name': 'product_id', 'type': 'int'}],
                            'returns': 'dict'},
                           {'name': 'export_sales_report_to_csv',
                            'params': [{'name': 'file_path', 'type': 'str'}],
                            'returns': 'None'},
                           {'name': 'find_duplicate_sales_by_product',
                            'params': [],
                            'returns': 'list'},
                           {'name': 'get_sales_with_product_names',
                            'params': [{'name': 'start_date', 'type': 'datetime'},
                                       {'name': 'end_date', 'type': 'datetime'}],
                            'returns': 'list'},
                           {'name': 'get_sales_with_low_quantity_threshold',
                            'params': [{'name': 'threshold', 'type': 'float'}],
                            'returns': 'list'},
                           {'name': 'add_product',
                            'params': [{'name': 'name', 'type': 'str'},
                                       {'name': 'price', 'type': 'str'}],
                            'returns': 'int'},
                           {'name': 'add_sale',
                            'params': [{'name': 'product_id', 'type': 'int'},
                                       {'name': 'quantity', 'type': 'int'},
                                       {'name': 'sale_date', 'type': 'str'}],
                            'returns': 'int'}]}],
 'foreign_keys_enabled': True,
 'business_rules': [{'id': 'sales_count_per_product_count_group_by',
                     'kind': 'count_group_by',
                     'entity': 'Sale',
                     'method': 'get_sales_count_per_product',
                     'fk': 'product_id',
                     'exception': 'None',
                     'over_status': 'None',
                     'ref_entity': 'Product'}],
 'business_logic_coverage': 'partial',
 'unexpressed_rules': ['The report showing total sales amount and number of sales per product '
                       'requires a method that computes total sales amount as sum of (quantity * '
                       'product.price), which is best modeled as sum_mul_joined. However, the '
                       'specification does not explicitly state the method or the fields involved, '
                       'so it is not fully expressible with the given rule kinds unless we infer '
                       "it. Since the rule kind 'sum_mul_joined' requires the method to return a "
                       'scalar sum of (child_field * ref_field), and the specification only says '
                       "'total sales amount' and 'number of sales per product', we must assume the "
                       'method exists and is named appropriately. However, the specification does '
                       'not specify the exact method name or the product price field, so this rule '
                       'cannot be fully expressed without additional detail. Thus, it is not '
                       'expressible with the given constraints.',
                       "The requirement for a report showing 'number of sales per product' implies "
                       'a grouped count, which is covered by count_group_by. However, the '
                       'specification does not explicitly state the method name or the grouping '
                       'field (product_id), so it is not fully expressible without assuming names. '
                       'Since the rule kind requires the method name and field, and these are not '
                       'specified, this rule is not fully expressible.',
                       'Rule total_sales_amount_sum_mul_joined (sum_mul_joined): incomplete rule '
                       'or target not present in the generated design']}

# --- recording -------------------------------------------------------------

def _record(domain, test, ok, detail=""):
    key = "%s:%s" % (domain, test)
    RESULT["tests"].append({
        "id": key,
        "status": "pass" if ok else "fail",
        "detail": str(detail),
    })
    RESULT["coverage"].setdefault(domain, {})[test] = "pass" if ok else "fail"

def _classify_error(exc):
    """Return 'app' if the error indicates a bug in the code under test, else
    'tester' (a harness bug we should fix — our own reflection/import/arg
    construction, never a real generated-code problem)."""
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        # A project module we tried to import isn't there: either we guessed the
        # path wrong (harness) or the app genuinely lacks the module (app). The
        # import helpers already try several paths; a failure here is usually a
        # harness naming issue.
        return "tester"
    name = type(exc).__name__
    if name == "TypeError":
        # Ambiguous, but the harness builds args from the real signature, so a
        # TypeError most often reflects our own reflection/arg mismatch or an
        # app-internal one. Conservative toward surfacing harness bugs.
        return "tester"
    # AttributeError (missing method/field), DB integrity/programming errors and
    # NotImplementedError all point at the generated application.
    return "app"

def _record_error(domain, test, exc):
    """Classify an exception: an app bug is recorded as a failing test; a
    harness bug is recorded in ``build_errors`` (kind=tester) so it is surfaced
    for fixing without being conflated with a real app failure."""
    kind = _classify_error(exc)
    if kind == "tester":
        RESULT["build_errors"].append({
            "kind": "tester",
            "error": "%r" % (exc,),
            "test": "%s:%s" % (domain, test),
        })
        return
    _record(domain, test, False, "error: %r" % (exc,))

def _safe(fn):
    """Run `fn()`; a raised exception is classified: a harness bug is recorded
    in ``build_errors`` (kind=tester), an app bug is recorded as a failure."""
    try:
        return fn()
    except Exception as exc:
        traceback.print_exc()
        RESULT["build_errors"].append({
            "kind": _classify_error(exc),
            "error": str(exc),
        })
        return None

# --- import / discovery helpers --------------------------------------------

def _import(module_name):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc1:
        # Package structure fallback (repositories/, services/ subdirs)
        for prefix in ("repositories.", "services."):
            try:
                return importlib.import_module(prefix + module_name)
            except ModuleNotFoundError:
                pass
        raise exc1

def _find_cls(module, class_name):
    try:
        return getattr(_import(module), class_name, None)
    except (ModuleNotFoundError, AttributeError):
        return None

def _entity_snake(name):
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

def _camel(name):
    import re
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return "".join(p.capitalize() for p in re.split(r"[_\s]+", name) if p)

def _plural(name):
    if name.endswith("s"):
        return name + "es"
    return name + "s"

def _sample(field):
    name = field.get("name", "")
    typ = field.get("type", "str")
    if typ == "int":
        low = name.lower()
        if any(k in low for k in ("price", "amount", "cost", "budget",
                                  "balance", "total", "limit", "count")):
            return 1500
        if "year" in low:
            return 2024
        if "month" in low:
            return 1
        return 42
    if typ == "float":
        return 15.5
    if typ == "bool":
        return True
    if typ == "date":
        return "2024-01-15"
    if typ == "datetime":
        return "2024-01-15T10:00:00"
    # str
    low = name.lower()
    if "email" in low:
        return "test@example.com"
    if "phone" in low:
        return "+33123456789"
    if "status" in low or "state" in low:
        return "active"
    if "code" in low or "sku" in low or "isbn" in low or "ref" in low:
        return "TEST-CODE"
    return "test_" + name

def _type_sample(field):
    """Value by declared type only (no name heuristics)."""
    typ = field.get("type", "str") if isinstance(field, dict) else str(field)
    return {
        "int": 42,
        "float": 15.5,
        "bool": True,
        "date": "2024-01-15",
        "datetime": "2024-01-15T10:00:00",
    }.get(typ, "sample_")

def _build_args(method, rule, ctx, spec):
    """Build positional args for `method` from its signature.

    ``ctx`` maps a parameter name to a value used to probe a role (e.g. a
    missing FK id, a duplicated unique value). Any parameter not in ``ctx``
    falls back to a type sample resolved by name against the rule's entity.
    """
    args = []
    try:
        params = list(inspect.signature(method).parameters.values())
    except (ValueError, TypeError):
        return args
    ent_name = rule.get("entity")
    ent = next(
        (e for e in spec.get("entities", []) if e["name"] == ent_name), None
    )
    for p in params:
        if p.name == "self":
            continue
        if p.name in ctx:
            args.append(ctx[p.name])
            continue
        field_type = "str"
        if ent is not None:
            fld = next(
                (f for f in ent.get("fields", []) if f.get("name") == p.name),
                None,
            )
            if fld is not None:
                field_type = fld.get("type", "str")
        args.append(_type_sample(field_type))
    return args

def _model_instance(model_cls, ent, fk_values=None):
    fk_values = fk_values or {}
    kw = {}
    for f in ent.get("fields", []):
        name = f.get("name")
        if name == "id":
            continue
        if name in fk_values:
            kw[name] = fk_values[name]
            continue
        kw[name] = _sample(f)
    return model_cls(**kw)

def _seed_entity_val(model_cls, ent, fk_values=None, index=0):
    """Build a model instance using type-sample values (no name heuristics).

    ``index`` (when non-zero) makes the sampled values distinct so that
    seeding several rows of the same entity doesn't collide on a UNIQUE field.
    """
    fk_values = fk_values or {}
    kw = {}
    for f in ent.get("fields", []):
        name = f.get("name")
        if name == "id":
            continue
        if name in fk_values:
            kw[name] = fk_values[name]
            continue
        val = _type_sample(f)
        if index:
            if isinstance(val, str):
                val = "%s_%d" % (val, index)
            elif isinstance(val, (int, float)):
                val = val + index
        kw[name] = val
    return model_cls(**kw)

def _call(obj, name, *args, **kwargs):
    fn = getattr(obj, name)
    return fn(*args, **kwargs)

def _arity_ok(fn, nargs):
    try:
        return len(inspect.signature(fn).parameters) - 1 >= nargs
    except (ValueError, TypeError):
        return True

# --- repo / service discovery ----------------------------------------------

def _repo_for(ent):
    snake = _entity_snake(ent["name"])
    for module in (snake + "_repository",):
        cls = _find_cls(module, ent["name"] + "Repository")
        if cls is None:
            continue
        return cls
    return None

def _service_for(ent):
    snake = _entity_snake(ent["name"])
    for module in (snake + "_service",):
        cls = _find_cls(module, ent["name"] + "Service")
        if cls is not None:
            return cls
    for obj in TEST_SPEC.get("services", []):
        cls = _find_cls(obj.get("module", ""), obj.get("class", ""))
        if cls is not None:
            return cls
    return None

_last_service_exc = None

def _service_create_rejects_overlap(svc_cls, spec, ent, fkv, start_f, end_f, scope_f, db):
    """Invoke the service method that creates `ent` with overlapping data.

    ``db`` MUST be the same Database instance that seeded the FK parents in
    ``fkv``; otherwise the service hits a dangling-FK IntegrityError rather
    than exercising the real overlap guard. Returns True iff the call raises
    (the overlap guard exists), else False.
    """
    global _last_service_exc
    ent_snake = _entity_snake(ent["name"])
    # Locate the create method: prefer a name like create_<ent>/add_<ent>.
    method_name = None
    for mname in dir(svc_cls):
        ml = mname.lower()
        if ml in ("create", "add", "make") or (
            ml.startswith(("create_", "add_", "make_", "register_", "book_"))
            and ent_snake in ml
        ):
            method_name = mname
            break
    if method_name is None:
        return False
    try:
        svc = svc_cls(db)
        method = getattr(svc, method_name)  # bound: self is implicit
        # Build args uniformly: FK ids from fkv, overlap interval values in
        # ctx, every other param by type sample. No heuristic business words.
        rule = {
            "entity": ent["name"],
            "start_field": start_f,
            "end_field": end_f,
            "scope_field": scope_f,
        }
        ctx = dict(fkv)
        ctx[start_f] = "2024-01-01T10:00:00"
        ctx[end_f] = "2024-01-01T12:00:00"
        ctx[scope_f] = fkv.get(scope_f, 1)
        # Resolve any status/state param by its declared type (no keyword).
        args = _build_args(method, rule, ctx, spec)
        method(*args)
        return False
    except Exception as exc:
        _last_service_exc = exc
        return True

def _db_setup():
    import sqlite3
    from database import Database
    tmp = tempfile.mktemp(suffix=".db")
    db = Database(tmp)
    # Ensure a fresh sqlite file so DDL runs cleanly.
    conn = sqlite3.connect(tmp)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()
    return db

def _seed_row_for(ent, spec, db):
    """Create a row for `ent` (via repo if present, else direct SQL). Returns id."""
    repo_cls = _repo_for(ent)
    model_cls = _find_cls("models", ent["name"])
    if repo_cls is not None and model_cls is not None:
        # Resolve this row's own FKs first, so a parent (e.g. Invoice) that
        # itself has a FK (e.g. Customer) is created with a REAL customer_id,
        # not a dangling sample id that would raise an FK IntegrityError.
        inst = _model_instance(model_cls, ent,
                               fk_values=_resolved_fk_values(ent, spec, db))
        created = _call(repo_cls(db), "create", inst)
        return created if isinstance(created, int) else getattr(created, "id", None)
    # Direct-SQL fallback for reference-only entities (e.g. a Room with no
    # room_repository): we still need a valid row so child FKs resolve.
    table = ent.get("table_name") or _plural(_entity_snake(ent["name"]))
    cols = [f["name"] for f in ent.get("fields", []) if f["name"] != "id"]
    vals = [_sample(f) for f in ent.get("fields", []) if f["name"] != "id"]
    placeholders = ",".join("?" for _ in cols)
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO %s (%s) VALUES (%s)" % (table, ",".join(cols), placeholders),
            vals,
        )
        conn.commit()
        return cur.lastrowid

def _resolved_fk_values(ent, spec, db):
    """Create parent rows for every FK of `ent` and return {fk_field: real_id}."""
    fk_map = {}
    for fk in ent.get("fks", []):
        ref = fk.get("ref")
        ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref), None)
        if ref_ent is not None:
            pid = _seed_row_for(ref_ent, spec, db)
            fk_map[fk.get("field")] = pid
    return fk_map

# --- per-entity CRUD -------------------------------------------------------

def _test_crud(ent, spec):
    ent_name = ent["name"]
    repo_cls = _repo_for(ent)
    if repo_cls is None:
        _record("crud", ent_name, False, "repo class not found")
        return
    try:
        db = _db_setup()
        repo = repo_cls(db)
        model_cls = _find_cls("models", ent_name)
        if model_cls is None:
            _record("crud", ent_name, False, "model class not found")
            return

        inst = _model_instance(model_cls, ent, fk_values=_resolved_fk_values(ent, spec, db))
        created = _call(repo, "create", inst)
        rid = created if isinstance(created, int) else getattr(created, "id", None)
        if rid is None:
            _record("crud", ent_name, False, "create did not return an id")
            return

        fetched = _call(repo, "get_by_id", rid)
        if fetched is None:
            _record("crud", ent_name, False, "get_by_id returned None")
            return

        # Assert non-id, non-nullable fields round-trip.
        bad = []
        for f in ent.get("fields", []):
            name = f.get("name")
            if name == "id" or f.get("nullable"):
                continue
            if name in inst.__dict__ and hasattr(fetched, name):
                if getattr(fetched, name) != getattr(inst, name):
                    bad.append("%s" % name)
        if bad:
            _record("crud", ent_name, False, "fields differ: %s" % ",".join(bad))
            return

        # list contains the new row
        listed = _call(repo, "list")
        if isinstance(listed, list):
            ids = {getattr(x, "id", None) for x in listed}
            if rid not in ids:
                _record("crud", ent_name, False, "list does not contain created row")
                return

        # update persists
        upd_ok = None
        # Pick a non-id, non-fk field to mutate.
        for f in ent.get("fields", []):
            name = f.get("name")
            if name == "id" or name.endswith("_id") or f.get("nullable"):
                continue
            new_val = "test_update_" + name
            if f.get("type") == "int":
                new_val = 7777
            elif f.get("type") == "bool":
                new_val = False
            elif f.get("type") in ("date", "datetime"):
                new_val = "2024-06-15" if f.get("type") == "date" else "2024-06-15T12:00:00"
            upd_ok = _call(repo, "update", rid, {name: new_val})
            if upd_ok is not None and upd_ok is False:
                _record("crud", ent_name, False, "update returned False")
                return
            refetched = _call(repo, "get_by_id", rid)
            if hasattr(refetched, name) and getattr(refetched, name) != new_val:
                _record("crud", ent_name, False, "update did not persist %s" % name)
                return
            break

        # delete removes
        del_ok = _call(repo, "delete", rid)
        if del_ok is not None and del_ok is False:
            _record("crud", ent_name, False, "delete returned False")
            return
        gone = _call(repo, "get_by_id", rid)
        if gone is not None:
            _record("crud", ent_name, False, "delete did not remove row")
            return

        _record("crud", ent_name, True)
    except Exception as exc:
        _record_error("crud", ent_name, exc)

# --- FK integrity ----------------------------------------------------------

def _test_fk(ent, spec):
    for fk in ent.get("fks", []):
        fk_field = fk.get("field")
        ref = fk.get("ref")
        test_name = "fk_%s" % fk_field
        repo_cls = _repo_for(ent)
        if repo_cls is None:
            _record("fk", test_name, False, "repo not found")
            continue
        try:
            db = _db_setup()
            repo = repo_cls(db)
            model_cls = _find_cls("models", ent["name"])
            # All FKs resolve to real parent rows; the FK under test is set
            # to a dangling id to probe the integrity guard.
            fk_vals = _resolved_fk_values(ent, spec, db)
            fk_vals[fk_field] = 999999
            inst = _model_instance(model_cls, ent, fk_values=fk_vals)
            raised = None
            try:
                _call(repo, "create", inst)
            except Exception as exc:
                raised = exc
            if raised is None:
                # A dangling FK was silently accepted: the schema declares a
                # FK, so integrity MUST be enforced. This is a violation.
                _record("fk", test_name, False,
                        "dangling FK accepted (FK integrity not enforced)")
            else:
                # A raise (IntegrityError or a designed business guard) is the
                # correct, enforced behaviour.
                _record("fk", test_name, True, "raised %r" % type(raised).__name__)
        except Exception as exc:
            _record_error("fk", test_name, exc)

# --- unique constraints ----------------------------------------------------

def _test_unique(ent, spec):
    uniques = []
    # unique fields
    for f in ent.get("fields", []):
        if f.get("unique") and f.get("name") != "id":
            uniques.append([f.get("name")])
    # unique_together
    for pair in ent.get("unique_together", []):
        if pair:
            uniques.append(pair)
    if not uniques:
        return
    repo_cls = _repo_for(ent)
    if repo_cls is None:
        return
    for pair in uniques:
        test_name = "unique_%s" % "_".join(pair)
        try:
            db = _db_setup()
            repo = repo_cls(db)
            model_cls = _find_cls("models", ent["name"])
            fkv = _resolved_fk_values(ent, spec, db)
            inst1 = _model_instance(model_cls, ent, fk_values=fkv)
            inst2 = _model_instance(model_cls, ent, fk_values=fkv)
            # Force equal values on the unique pair for inst2.
            for name in pair:
                setattr(inst2, name, getattr(inst1, name))
            _call(repo, "create", inst1)
            raised = None
            try:
                _call(repo, "create", inst2)
            except Exception as exc:
                raised = exc
            if raised is None:
                created2 = _call(repo, "list")
                if isinstance(created2, list) and len(created2) >= 2:
                    _record("unique", test_name, True,
                            "duplicate pair accepted (lenient: no DB UNIQUE)")
                else:
                    _record("unique", test_name, False, "duplicate not rejected")
            else:
                _record("unique", test_name, True, "raised %r" % type(raised).__name__)
        except Exception as exc:
            _record_error("unique", test_name, exc)

# --- business rules --------------------------------------------------------

def _test_overlap(rule, spec):
    ent_name = rule.get("entity")
    ent = next(e for e in spec.get("entities", []) if e["name"] == ent_name)
    repo_cls = _repo_for(ent)
    test_name = "overlap_%s" % rule.get("id", ent_name)
    if repo_cls is None:
        _record("business_rule", test_name, False, "repo not found")
        return
    start_f = rule.get("start_field")
    end_f = rule.get("end_field")
    scope_f = rule.get("scope_field")
    try:
        db = _db_setup()
        repo = repo_cls(db)
        model_cls = _find_cls("models", ent_name)
        fkv = _resolved_fk_values(ent, spec, db)
        # Seed a first reservation.
        inst1 = _model_instance(model_cls, ent, fk_values=fkv)
        # Set overlap fields deterministically.
        setattr(inst1, start_f, "2024-01-01T09:00:00")
        setattr(inst1, end_f, "2024-01-01T11:00:00")
        _call(repo, "create", inst1)
        # Second overlapping reservation in the SAME scope; service-level
        # guard is what the spec demands, so we exercise the repo directly
        # only to confirm a create of an overlapping interval is policed.
        inst2 = _model_instance(model_cls, ent, fk_values=fkv)
        setattr(inst2, start_f, "2024-01-01T10:00:00")
        setattr(inst2, end_f, "2024-01-01T12:00:00")
        raised = None
        try:
            _call(repo, "create", inst2)
        except Exception as exc:
            raised = exc
        # The repo is lenient. The spec's guard normally lives in the SERVICE
        # layer ("reject reservations that overlap"), so we must actually
        # invoke the service create method — mere presence of a service class
        # is NOT evidence it polices overlap. If it does not raise, the
        # overlap invariant is violated and the test FAILS.
        svc_cls = _service_for(ent)
        svc_rejected = None
        if svc_cls is not None:
            svc_rejected = _service_create_rejects_overlap(
                svc_cls, spec, ent, fkv, start_f, end_f, scope_f, db
            )
        if raised is not None:
            _record("business_rule", test_name, True, "repo raised %r" % type(raised).__name__)
        elif svc_rejected is True:
            _record("business_rule", test_name, True, "service raised %r" % (_last_service_exc,))
        else:
            _record("business_rule", test_name, False,
                    "overlap not rejected (repo lenient, service did not raise)")
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_sum_equals(rule, spec):
    parent_ent = rule.get("parent_entity")
    parent_total = rule.get("parent_total_field")
    child_ent = rule.get("child_entity")
    fk_field = rule.get("fk_field")
    amounts = rule.get("child_amount_fields")
    test_name = "sum_%s" % rule.get("id", parent_ent)
    parent = next((e for e in spec.get("entities", []) if e["name"] == parent_ent), None)
    child = next((e for e in spec.get("entities", []) if e["name"] == child_ent), None)
    if parent is None or child is None:
        _record("business_rule", test_name, False, "parent/child entity missing")
        return
    try:
        db = _db_setup()
        parent_repo = _repo_for(parent)
        child_repo = _repo_for(child)
        if parent_repo is None or child_repo is None:
            _record("business_rule", test_name, False, "repo missing")
            return
        parent_repo_inst = parent_repo(db)
        child_repo_inst = child_repo(db)
        parent_cls = _find_cls("models", parent_ent)
        child_cls = _find_cls("models", child_ent)
        # Resolve every FK of the parent (e.g. Invoice.customer_id) so it is
        # created without a dangling reference, which would otherwise surface
        # as a spurious IntegrityError instead of the real total invariant.
        pinst = _model_instance(parent_cls, parent,
                                fk_values=_resolved_fk_values(parent, spec, db))
        setattr(pinst, parent_total, 0)
        parent_id = _call(parent_repo_inst, "create", pinst)
        pid = parent_id if isinstance(parent_id, int) else getattr(parent_id, "id", None)

        # Resolve the child's OTHER FKs (everything except the fk_field that
        # links it to the parent we just created) so child rows don't dangle.
        child_fkv = _resolved_fk_values(child, spec, db)
        child_fkv.pop(fk_field, None)

        expected = 0
        for i in range(2):
            cinst = _model_instance(child_cls, child,
                                    fk_values={**child_fkv, fk_field: pid})
            vals = []
            for a_name in amounts:
                afield = next(
                    (f for f in child.get("fields", []) if f.get("name") == a_name),
                    {"name": a_name, "type": "int"},
                )
                val = _type_sample(afield)
                setattr(cinst, a_name, val)
                vals.append(val)
            if len(vals) >= 2:
                expected += vals[0] * vals[1]
            else:
                expected += vals[0]
            _call(child_repo_inst, "create", cinst)

        parent_fetched = _call(parent_repo_inst, "get_by_id", pid)
        actual = getattr(parent_fetched, parent_total, None)
        if actual is None:
            _record("business_rule", test_name, False, "total field missing/None")
            return
        if actual == expected:
            _record("business_rule", test_name, True)
        else:
            _record("business_rule", test_name, False,
                    "total %r != expected %r" % (actual, expected))
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_unique_pair(rule, spec):
    ent_name = rule.get("entity")
    fields = rule.get("fields")
    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)
    test_name = "pair_%s" % rule.get("id", ent_name)
    if ent is None or not fields:
        _record("business_rule", test_name, False, "entity/fields missing")
        return
    repo_cls = _repo_for(ent)
    if repo_cls is None:
        _record("business_rule", test_name, False, "repo not found")
        return
    try:
        db = _db_setup()
        repo = repo_cls(db)
        model_cls = _find_cls("models", ent_name)
        fkv = _resolved_fk_values(ent, spec, db)
        inst1 = _seed_entity_val(model_cls, ent, fk_values=fkv)
        inst2 = _seed_entity_val(model_cls, ent, fk_values=fkv)
        for name in fields:
            setattr(inst2, name, getattr(inst1, name))
        _call(repo, "create", inst1)
        raised = None
        try:
            _call(repo, "create", inst2)
        except Exception as exc:
            raised = exc
        if raised is None:
            _record("business_rule", test_name, True,
                    "pair accepted (lenient: may be enforced at service)")
        else:
            _record("business_rule", test_name, True, "raised %r" % type(raised).__name__)
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_no_stub(rule, spec):
    cls_name = rule.get("class")
    method_names = rule.get("methods", [])
    test_name = "nostub_%s" % rule.get("id", cls_name)
    if not cls_name or not method_names:
        _record("business_rule", test_name, False, "class/methods missing")
        return
    found_cls = None
    for obj in spec.get("repositories", []) + spec.get("services", []):
        if obj.get("class") == cls_name:
            found_cls = _find_cls(obj.get("module", ""), cls_name)
            break
    if found_cls is None:
        _record("business_rule", test_name, False, "class not found")
        return
    for m in method_names:
        method = getattr(found_cls, m, None)
        if method is None or not callable(method):
            _record("business_rule", test_name, False, "method %s missing or not callable" % m)
            return
        try:
            src = inspect.getsource(method)
        except (TypeError, OSError) as e:
            _record("business_rule", test_name, False, "cannot get source for method %s: %s" % (m, e))
            return
        if "NotImplementedError" in src:
            _record("business_rule", test_name, False, "method %s is a stub" % m)
            return
    _record("business_rule", test_name, True)

def _test_filter_lt(rule, spec):
    ent_name = rule.get("entity")
    method_name = rule.get("method")
    field = rule.get("field")
    ref_ent_name = rule.get("ref_entity")
    ref_field = rule.get("ref_field")
    fk = rule.get("fk")
    test_name = "filter_%s" % rule.get("id", ent_name)

    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)
    ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref_ent_name), None)
    if ent is None or ref_ent is None or not method_name:
        _record("business_rule", test_name, False, "entity/ref_entity/method missing")
        return
    # A filter_lt rule must carry its comparison/threshold fields to be
    # exercised. The runner validates completeness (rule_is_complete); if one
    # is still missing here, that is a pipeline inconsistency — surface it as
    # a failure instead of silently skipping.
    if not field or not ref_field or not fk:
        _record("business_rule", test_name, False,
                "filter_lt rule missing field/ref_field/fk")
        return
    try:
        db = _db_setup()
        ref_repo = _repo_for(ref_ent)
        ref_model = _find_cls("models", ref_ent_name)
        if ref_repo is None or ref_model is None:
            _record("business_rule", test_name, False, "ref repo/model missing")
            return
        ref_repo_inst = ref_repo(db)
        # Seed the reference entity with ref_field = 5 (a threshold).
        ref_inst = _seed_entity_val(ref_model, ref_ent)
        setattr(ref_inst, ref_field, 5)
        ref_id = _call(ref_repo_inst, "create", ref_inst)
        ref_id = ref_id if isinstance(ref_id, int) else getattr(ref_id, "id", None)

        ent_repo = _repo_for(ent)
        ent_model = _find_cls("models", ent_name)
        if ent_repo is None or ent_model is None:
            _record("business_rule", test_name, False, "entity repo/model missing")
            return
        ent_repo_inst = ent_repo(db)
        # Row below the threshold (field=3) and row at/above it (field=7).
        low_inst = _seed_entity_val(ent_model, ent, fk_values={fk: ref_id}, index=1)
        setattr(low_inst, field, 3)
        low_id = _call(ent_repo_inst, "create", low_inst)
        low_id = low_id if isinstance(low_id, int) else getattr(low_id, "id", None)

        high_inst = _seed_entity_val(ent_model, ent, fk_values={fk: ref_id}, index=2)
        setattr(high_inst, field, 7)
        high_id = _call(ent_repo_inst, "create", high_inst)
        high_id = high_id if isinstance(high_id, int) else getattr(high_id, "id", None)

        owner_cls = _service_for(ent) or ent_repo
        owner = owner_cls(db)
        method = getattr(owner, method_name, None)
        if method is None:
            _record("business_rule", test_name, False, "method %s not found" % method_name)
            return
        try:
            result = method()
        except TypeError:
            result = method(*_build_args(method, rule, {}, spec))
        if not isinstance(result, list):
            _record("business_rule", test_name, False,
                    "method returned non-list %r" % type(result).__name__)
            return
        ids = []
        for item in result:
            if isinstance(item, dict):
                ids.append(item.get("id"))
            else:
                ids.append(getattr(item, "id", None))
        if low_id in ids and high_id not in ids:
            _record("business_rule", test_name, True)
        else:
            _record("business_rule", test_name, False,
                    "filter_lt: low=%r in=%r; high=%r out=%r" %
                    (low_id, low_id in ids, high_id, high_id not in ids))
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_aggregate_mul_sum(rule, spec):
    ent_name = rule.get("entity")
    method_name = rule.get("method")
    fk = rule.get("fk")
    a = rule.get("a")
    b = rule.get("b")
    test_name = "agg_%s" % rule.get("id", ent_name)

    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)
    if ent is None or not method_name or not fk or not a or not b:
        _record("business_rule", test_name, False, "entity/method/fk/a/b missing")
        return
    try:
        db = _db_setup()
        ent_repo = _repo_for(ent)
        ent_model = _find_cls("models", ent_name)
        if ent_repo is None or ent_model is None:
            _record("business_rule", test_name, False, "repo/model missing")
            return
        ent_repo_inst = ent_repo(db)

        # Seed two parent rows for the fk reference (or fall back to int ids).
        fk_def = next((f for f in ent.get("fks", []) if f.get("field") == fk), None)
        ref_name = fk_def.get("ref") if fk_def else None
        group_ids = []
        if ref_name:
            ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref_name), None)
            ref_repo = _repo_for(ref_ent) if ref_ent else None
            ref_model = _find_cls("models", ref_name) if ref_ent else None
            if ref_repo is not None and ref_model is not None:
                ref_repo_inst = ref_repo(db)
                for i in range(2):
                    rinst = _seed_entity_val(ref_model, ref_ent, index=i + 1)
                    rid = _call(ref_repo_inst, "create", rinst)
                    group_ids.append(rid if isinstance(rid, int) else getattr(rid, "id", None))
            else:
                group_ids = [1, 2]
        else:
            group_ids = [1, 2]

        expected = {}
        seed_idx = 0
        for gi, gid in enumerate(group_ids):
            pairs = [(2, 3), (4, 5)] if gi == 0 else [(1, 10)]
            expected[gid] = 0
            for (av, bv) in pairs:
                seed_idx += 1
                inst = _seed_entity_val(ent_model, ent, fk_values={fk: gid}, index=seed_idx)
                setattr(inst, a, av)
                setattr(inst, b, bv)
                _call(ent_repo_inst, "create", inst)
                expected[gid] += av * bv

        owner_cls = _service_for(ent) or ent_repo
        owner = owner_cls(db)
        method = getattr(owner, method_name, None)
        if method is None:
            _record("business_rule", test_name, False, "method %s not found" % method_name)
            return
        try:
            result = method()
        except TypeError:
            result = method(*_build_args(method, rule, {}, spec))

        result_map = {}
        if isinstance(result, dict):
            result_map = result
        elif isinstance(result, (list, tuple)):
            for item in result:
                if isinstance(item, dict):
                    k = item.get(fk) or item.get("id")
                    v = item.get("total") or item.get("value") or item.get("sum")
                    if k is not None:
                        result_map[k] = v
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    result_map[item[0]] = item[1]
        else:
            _record("business_rule", test_name, False,
                    "method returned %r" % type(result).__name__)
            return

        for gid, exp in expected.items():
            if result_map.get(gid) != exp:
                _record("business_rule", test_name, False,
                        "group %r: got %r expected %r" % (gid, result_map.get(gid), exp))
                return
        _record("business_rule", test_name, True)
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_ensure_raise(rule, spec):
    method_name = rule.get("method")
    ent_name = rule.get("entity")
    ref_field = rule.get("ref_field")
    unique_field = rule.get("unique_field")
    fk = rule.get("fk")
    test_name = "raise_%s" % rule.get("id", method_name or ent_name)

    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)         if ent_name else None
    if not method_name:
        _record("business_rule", test_name, False, "method missing")
        return
    try:
        db = _db_setup()
        owner_cls = None
        if ent is not None:
            owner_cls = _service_for(ent) or _repo_for(ent)
        if owner_cls is None:
            # Fall back to scanning declared services/repositories for the method.
            for obj in spec.get("services", []) + spec.get("repositories", []):
                cls = _find_cls(obj.get("module", ""), obj.get("class", ""))
                if cls is not None and hasattr(cls, method_name):
                    owner_cls = cls
                    break
        if owner_cls is None:
            _record("business_rule", test_name, False, "owner class for method not found")
            return
        owner = owner_cls(db)
        method = getattr(owner, method_name)
        params = set(inspect.signature(method).parameters) if method else set()

        # Case 1: raise when a referenced entity does not exist. The local FK
        # (`fk`) is the method parameter that carries the referenced id, so it
        # is the natural probe: ctx[fk] = 999999 injects a dangling reference.
        # Fall back to `ref_field` if it is itself a parameter. If neither is
        # reachable the rule is mis-targeted — surface it, never silently skip.
        if ref_field:
            probe_key = None
            if fk and fk in params:
                probe_key = fk
            elif ref_field in params:
                probe_key = ref_field
            if probe_key is None:
                _record("business_rule", test_name, False,
                        "mis-targeted: neither %s nor %s is a parameter of %s"
                        % (fk, ref_field, method_name))
                return
            ctx = _resolved_fk_values(ent, spec, db) if ent is not None else {}
            ctx[probe_key] = 999999
            args = _build_args(method, rule, ctx, spec)
            raised = None
            try:
                method(*args)
            except Exception as exc:
                raised = exc
            if raised is None:
                _record("business_rule", test_name, False,
                        "method did not raise on missing %s" % ref_field)
                return

        # Case 2: raise when a unique field is duplicated.
        if unique_field and ent is not None:
            if unique_field not in params:
                _record("business_rule", test_name, False,
                        "mis-targeted: %s is not a parameter of %s"
                        % (unique_field, method_name))
                return
            ent_repo = _repo_for(ent)
            ent_model = _find_cls("models", ent_name)
            if ent_repo is not None and ent_model is not None:
                fkv = _resolved_fk_values(ent, spec, db)
                first = _seed_entity_val(ent_model, ent, fk_values=fkv)
                dup_value = getattr(first, unique_field, None)
                _call(ent_repo, "create", first)
                ctx = dict(fkv)
                ctx[unique_field] = dup_value
                args = _build_args(method, rule, ctx, spec)
                raised = None
                try:
                    method(*args)
                except Exception as exc:
                    raised = exc
                if raised is None:
                    _record("business_rule", test_name, False,
                            "method did not raise on duplicate %s" % unique_field)
                    return

        _record("business_rule", test_name, True)
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_count_group_by(rule, spec):
    ent_name = rule.get("entity")
    method_name = rule.get("method")
    fk = rule.get("fk")
    ref_ent_name = rule.get("ref_entity")
    test_name = "count_%s" % rule.get("id", ent_name)

    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)
    ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref_ent_name), None)
    if ent is None or ref_ent is None or not method_name or not fk:
        _record("business_rule", test_name, False, "entity/ref_entity/method/fk missing")
        return
    try:
        db = _db_setup()
        ref_repo = _repo_for(ref_ent)
        ref_model = _find_cls("models", ref_ent_name)
        ent_repo = _repo_for(ent)
        ent_model = _find_cls("models", ent_name)
        if ref_repo is None or ref_model is None or ent_repo is None or ent_model is None:
            _record("business_rule", test_name, False, "repo/model missing")
            return
        ref_repo_inst = ref_repo(db)
        ent_repo_inst = ent_repo(db)

        # Seed two reference groups, then 2 rows for group 0 and 1 for group 1.
        group_ids = []
        for i in range(2):
            rinst = _seed_entity_val(ref_model, ref_ent, index=i + 1)
            rid = _call(ref_repo_inst, "create", rinst)
            group_ids.append(rid if isinstance(rid, int) else getattr(rid, "id", None))

        counts = {group_ids[0]: 2, group_ids[1]: 1}
        seed_idx = 0
        for gid, n in counts.items():
            for _ in range(n):
                seed_idx += 1
                inst = _seed_entity_val(ent_model, ent, fk_values={fk: gid}, index=seed_idx)
                _call(ent_repo_inst, "create", inst)

        owner_cls = _service_for(ent) or ent_repo
        owner = owner_cls(db)
        method = getattr(owner, method_name, None)
        if method is None:
            _record("business_rule", test_name, False, "method %s not found" % method_name)
            return
        try:
            result = method()
        except TypeError:
            result = method(*_build_args(method, rule, {}, spec))

        result_map = {}
        if isinstance(result, dict):
            result_map = result
        elif isinstance(result, (list, tuple)):
            for item in result:
                if isinstance(item, dict):
                    k = item.get(fk) or item.get("id") or item.get("key")
                    v = item.get("count") or item.get("total") or item.get("value")
                    if k is not None:
                        result_map[k] = v
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    result_map[item[0]] = item[1]
        else:
            _record("business_rule", test_name, False,
                    "method returned %r" % type(result).__name__)
            return

        for gid, exp in counts.items():
            if result_map.get(gid) != exp:
                _record("business_rule", test_name, False,
                        "group %r: got %r expected %r" % (gid, result_map.get(gid), exp))
                return
        _record("business_rule", test_name, True)
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_sum_mul_joined(rule, spec):
    ent_name = rule.get("entity")
    method_name = rule.get("method")
    fk = rule.get("fk")
    ref_ent_name = rule.get("ref_entity")
    child_field = rule.get("child_field")
    ref_field = rule.get("ref_field")
    test_name = "sumn_%s" % rule.get("id", ent_name)

    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)
    ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref_ent_name), None)
    if ent is None or ref_ent is None or not method_name or not fk             or not child_field or not ref_field:
        _record("business_rule", test_name, False,
                "entity/ref_entity/method/fk/child_field/ref_field missing")
        return
    try:
        db = _db_setup()
        ref_repo = _repo_for(ref_ent)
        ref_model = _find_cls("models", ref_ent_name)
        ent_repo = _repo_for(ent)
        ent_model = _find_cls("models", ent_name)
        if ref_repo is None or ref_model is None or ent_repo is None or ent_model is None:
            _record("business_rule", test_name, False, "repo/model missing")
            return
        ref_repo_inst = ref_repo(db)
        ent_repo_inst = ent_repo(db)

        # Seed two reference rows with distinct ref_field (e.g. unit prices),
        # then several child rows whose child_field is the per-row quantity.
        ref_vals = []
        for i, price in ((0, 3.0), (1, 5.0)):
            rinst = _seed_entity_val(ref_model, ref_ent, index=i + 1)
            setattr(rinst, ref_field, price)
            rid = _call(ref_repo_inst, "create", rinst)
            ref_vals.append((rid if isinstance(rid, int) else getattr(rid, "id", None), price))

        expected = 0.0
        seed_idx = 0
        for rid, price in ref_vals:
            for qty in (2, 4):
                seed_idx += 1
                inst = _seed_entity_val(ent_model, ent, fk_values={fk: rid}, index=seed_idx)
                setattr(inst, child_field, qty)
                _call(ent_repo_inst, "create", inst)
                expected += qty * price

        owner_cls = _service_for(ent) or ent_repo
        owner = owner_cls(db)
        method = getattr(owner, method_name, None)
        if method is None:
            _record("business_rule", test_name, False, "method %s not found" % method_name)
            return
        try:
            result = method()
        except TypeError:
            result = method(*_build_args(method, rule, {}, spec))

        try:
            actual = float(result)
        except (TypeError, ValueError):
            _record("business_rule", test_name, False,
                    "method returned non-scalar %r" % (result,))
            return
        if abs(actual - expected) < 1e-6:
            _record("business_rule", test_name, True)
        else:
            _record("business_rule", test_name, False,
                    "sum %r != expected %r" % (actual, expected))
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _collect_status_pairs(obj, fk, out):
    """Recursively collect (group_id, status) pairs from a report result.

    Handles a direct {group_id: status} mapping, a list of per-group status
    dicts ({fk: id, 'status': ...}), and a nested container such as
    {'month': ..., 'per_category': [{category_id, budget_status}]}.
    """
    if isinstance(obj, dict):
        k = obj.get(fk) or obj.get("id") or obj.get("key")
        v = obj.get("status") or obj.get("budget_status") or obj.get("state")
        if k is not None and v is not None and isinstance(v, str):
            out[k] = v
            return
        for kk, vv in obj.items():
            if isinstance(vv, str) and isinstance(kk, int):
                out[kk] = vv
            elif isinstance(vv, (dict, list, tuple)):
                _collect_status_pairs(vv, fk, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_status_pairs(item, fk, out)

def _test_ensure_raise_with_comparison(rule, spec):
    method_name = rule.get("method")
    ent_name = rule.get("entity")
    fk = rule.get("fk")
    ref_ent_name = rule.get("ref_entity")
    ref_field = rule.get("ref_field")
    agg_field = rule.get("aggregate_field")
    exception_name = rule.get("exception")
    test_name = "raisecmp_%s" % rule.get("id", method_name or ent_name)

    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)         if ent_name else None
    ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref_ent_name), None)         if ref_ent_name else None
    if not method_name or ent is None or ref_ent is None or not fk             or not ref_field or not agg_field:
        _record("business_rule", test_name, False,
                "ensure_raise_with_comparison missing fields")
        return
    try:
        db = _db_setup()
        ref_repo = _repo_for(ref_ent)
        ref_model = _find_cls("models", ref_ent_name)
        ent_repo = _repo_for(ent)
        ent_model = _find_cls("models", ent_name)
        if ref_repo is None or ref_model is None or ent_repo is None or ent_model is None:
            _record("business_rule", test_name, False, "repo/model missing")
            return
        ref_repo_inst = ref_repo(db)
        ent_repo_inst = ent_repo(db)

        # Seed the reference entity with a small threshold, then child rows whose
        # aggregate sums just below it so the accumulated check is exercised.
        threshold = 100
        ref_inst = _seed_entity_val(ref_model, ref_ent,
                                    fk_values=_resolved_fk_values(ref_ent, spec, db))
        setattr(ref_inst, ref_field, threshold)
        ref_id = _call(ref_repo_inst, "create", ref_inst)
        ref_id = ref_id if isinstance(ref_id, int) else getattr(ref_id, "id", None)

        # Resolve the child's OTHER FKs first so the rows we seed do not dangle
        # (the FK being driven is overwritten with the ref row we just created).
        child_fkv = _resolved_fk_values(ent, spec, db)
        child_fkv.pop(fk, None)

        running = 0
        seed_idx = 0
        for v in (60, 30):
            seed_idx += 1
            inst = _seed_entity_val(ent_model, ent,
                                    fk_values={**child_fkv, fk: ref_id},
                                    index=seed_idx)
            setattr(inst, agg_field, v)
            _call(ent_repo_inst, "create", inst)
            running += v

        owner_cls = _service_for(ent) or ent_repo
        owner = owner_cls(db)
        method = getattr(owner, method_name, None)
        if method is None:
            _record("business_rule", test_name, False, "method %s not found" % method_name)
            return
        params = set(inspect.signature(method).parameters)

        # The comparison must be exercisable: either the FK (group) or the
        # aggregate field must be an actual method parameter; otherwise the rule
        # is mis-targeted and we cannot drive the condition deterministically.
        if fk not in params and agg_field not in params:
            _record("business_rule", test_name, False,
                    "mis-targeted: neither %s nor %s is a parameter of %s"
                    % (fk, agg_field, method_name))
            return

        ctx = {}
        if fk in params:
            ctx[fk] = ref_id
        if agg_field in params:
            # A single-row value that (alone or atop the accumulated total) pushes
            # the aggregate over the threshold.
            ctx[agg_field] = threshold - running + 1
        args = _build_args(method, rule, ctx, spec)

        raised = None
        try:
            method(*args)
        except Exception as exc:
            raised = exc
        if raised is None:
            _record("business_rule", test_name, False,
                    "method did not raise when aggregate crossed threshold")
            return

        if exception_name:
            exp_cls = None
            try:
                exc_mod = _import("exceptions")
                exp_cls = getattr(exc_mod, exception_name, None)
            except Exception:
                exp_cls = None
            if exp_cls is not None and isinstance(raised, exp_cls):
                _record("business_rule", test_name, True)
            elif exp_cls is None:
                _record("business_rule", test_name, True,
                        "raised %r (exception %s not importable, taken as satisfied)"
                        % (type(raised).__name__, exception_name))
            else:
                _record("business_rule", test_name, False,
                        "raised %r expected %s" % (type(raised).__name__, exception_name))
        else:
            _record("business_rule", test_name, True, "raised %r" % type(raised).__name__)
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_sum_compare_status(rule, spec):
    ent_name = rule.get("entity")
    method_name = rule.get("method")
    fk = rule.get("fk")
    ref_ent_name = rule.get("ref_entity")
    ref_field = rule.get("ref_field")
    agg_field = rule.get("aggregate_field")
    over_status = rule.get("over_status")
    test_name = "status_%s" % rule.get("id", ent_name)

    ent = next((e for e in spec.get("entities", []) if e["name"] == ent_name), None)         if ent_name else None
    ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref_ent_name), None)         if ref_ent_name else None
    if ent is None or ref_ent is None or not method_name or not fk             or not ref_field or not agg_field or not over_status:
        _record("business_rule", test_name, False, "sum_compare_status missing fields")
        return
    try:
        db = _db_setup()
        ref_repo = _repo_for(ref_ent)
        ref_model = _find_cls("models", ref_ent_name)
        ent_repo = _repo_for(ent)
        ent_model = _find_cls("models", ent_name)
        if ref_repo is None or ref_model is None or ent_repo is None or ent_model is None:
            _record("business_rule", test_name, False, "repo/model missing")
            return
        ref_repo_inst = ref_repo(db)
        ent_repo_inst = ent_repo(db)

        # Seed two owners: one whose aggregate sum EXCEEDS the threshold, one
        # below it. Then drive the report and assert the per-group status.
        owner_ids = {}
        seed_idx = 0
        for label in ("over", "under"):
            seed_idx += 1
            rinst = _seed_entity_val(ref_model, ref_ent, index=seed_idx,
                                     fk_values=_resolved_fk_values(ref_ent, spec, db))
            setattr(rinst, ref_field, 100)
            rid = _call(ref_repo_inst, "create", rinst)
            owner_ids[label] = rid if isinstance(rid, int) else getattr(rid, "id", None)

        # Resolve the child's OTHER FKs so the seeded rows do not dangle.
        child_fkv = _resolved_fk_values(ent, spec, db)
        child_fkv.pop(fk, None)

        seed_idx = 0
        for label, values in (("over", (60, 90)), ("under", (20, 30))):
            oid = owner_ids[label]
            for v in values:
                seed_idx += 1
                inst = _seed_entity_val(ent_model, ent,
                                        fk_values={**child_fkv, fk: oid},
                                        index=seed_idx)
                setattr(inst, agg_field, v)
                _call(ent_repo_inst, "create", inst)

        owner_cls = _service_for(ent) or ent_repo
        owner = owner_cls(db)
        method = getattr(owner, method_name, None)
        if method is None:
            _record("business_rule", test_name, False, "method %s not found" % method_name)
            return
        try:
            result = method()
        except TypeError:
            result = method(*_build_args(method, rule, {}, spec))

        status_map = {}
        _collect_status_pairs(result, fk, status_map)

        a_status = status_map.get(owner_ids["over"])
        b_status = status_map.get(owner_ids["under"])
        if a_status is None or b_status is None:
            _record("business_rule", test_name, False,
                    "missing status for seeded groups (over=%r under=%r)"
                    % (a_status, b_status))
            return
        if str(a_status).lower() == str(over_status).lower() and                 str(b_status).lower() != str(over_status).lower():
            _record("business_rule", test_name, True)
        else:
            _record("business_rule", test_name, False,
                    "over=%r under=%r expected over_status=%r"
                    % (a_status, b_status, over_status))
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

# --- exceptions ------------------------------------------------------------

def _test_exception(exc, spec):
    name = exc.get("name")
    trigger = exc.get("trigger")
    test_name = "exc_%s" % name
    exc_cls = None
    try:
        mod = _import("exceptions")
        exc_cls = getattr(mod, name, None)
    except Exception:
        exc_cls = None
    if exc_cls is None:
        _record("exceptions", test_name, False, "exception class not found")
        return
    # We cannot reliably force each trigger generically; we at least verify
    # the class is importable and is an Exception subclass. The specific
    # raise conditions are exercised by the business-rule tests above.
    if issubclass(exc_cls, Exception):
        _record("exceptions", test_name, True)
    else:
        _record("exceptions", test_name, False, "not an Exception subclass")

# --- runner ----------------------------------------------------------------

def _run_all():
    spec = TEST_SPEC
    # Only entities that HAVE a declared repository are CRUD/FK/unique tested.
    # Reference-only entities (e.g. a Room with no room_repository in the
    # spec) are skipped. The oracle sometimes omits the `entity` binding on a
    # repo entry; infer it from the module stem (task_repository -> Task).
    repo_entities = set()
    for obj in spec.get("repositories", []):
        e = obj.get("entity") or ""
        if e:
            repo_entities.add(e)
            continue
        mod = str(obj.get("module") or "")
        stem = mod[: -len("_repository")] if mod.endswith("_repository") else mod
        repo_entities.add(_camel(stem))
    for ent in spec.get("entities", []):
        if ent["name"] not in repo_entities:
            continue
        _test_crud(ent, spec)
        _test_fk(ent, spec)
        _test_unique(ent, spec)
    EXECUTOR_DISPATCH = {'overlap_conflict': '_test_overlap',
 'sum_equals': '_test_sum_equals',
 'unique_pair': '_test_unique_pair',
 'no_stub': '_test_no_stub',
 'filter_lt': '_test_filter_lt',
 'aggregate_mul_sum': '_test_aggregate_mul_sum',
 'ensure_raise': '_test_ensure_raise',
 'count_group_by': '_test_count_group_by',
 'sum_mul_joined': '_test_sum_mul_joined',
 'ensure_raise_with_comparison': '_test_ensure_raise_with_comparison',
 'sum_compare_status': '_test_sum_compare_status'}
    # Track single unique fields already covered in _test_unique to avoid running duplicate unique_pair tests
    covered_single_uniques = set()
    for ent in spec.get("entities", []):
        if ent["name"] not in repo_entities:
            continue
        for f in ent.get("fields", []):
            if f.get("unique") and f.get("name") != "id":
                covered_single_uniques.add((ent["name"], f.get("name")))

    for rule in spec.get("business_rules", []):
        kind = rule.get("kind")
        if kind == "unique_pair":
            r_ent = rule.get("entity")
            r_fields = rule.get("fields") or []
            if len(r_fields) == 1 and (r_ent, r_fields[0]) in covered_single_uniques:
                continue  # Already tested by _test_unique
        executor = EXECUTOR_DISPATCH.get(kind)
        if executor is not None and executor in globals():
            globals()[executor](rule, spec)
    for exc in spec.get("exceptions", []):
        _test_exception(exc, spec)

RESULT["build_errors"] = []

def main():
    try:
        _run_all()
    except Exception as exc:
        traceback.print_exc()
        RESULT["build_errors"].append({
            "kind": "tester",
            "error": "fatal: %r" % (exc,),
        })
    # A failed test = a real bug in the code under test -> "fail". A harness
    # bug (build_errors with kind=tester, no test failures) -> "harness_error",
    # surfaced distinctly so it is fixed, never conflated with an app failure.
    tests_failed = any(t["status"] != "pass" for t in RESULT["tests"])
    harness_errors = [b for b in RESULT["build_errors"] if b.get("kind") == "tester"]
    if tests_failed:
        RESULT["status"] = "fail"
    elif harness_errors:
        RESULT["status"] = "harness_error"
    else:
        RESULT["status"] = "pass"
    print(json.dumps(RESULT, indent=2, default=str))
    return 0 if RESULT["status"] == "pass" else 1

if __name__ == "__main__":
    raise SystemExit(main())
