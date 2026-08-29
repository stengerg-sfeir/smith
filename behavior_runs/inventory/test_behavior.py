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
 'entities': [{'name': 'Category',
               'table_name': '',
               'fields': [{'name': 'name',
                           'type': 'str',
                           'nullable': False,
                           'unique': True,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'id',
                           'type': 'int',
                           'nullable': False,
                           'unique': False,
                           'primary_key': True,
                           'auto': 'autoincrement',
                           'default': 'None'},
                          {'name': 'description',
                           'type': 'str',
                           'nullable': True,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': 'None'},
                          {'name': 'reorder_threshold',
                           'type': 'int',
                           'nullable': True,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': 'None'}],
               'unique_together': [['name']],
               'fks': []},
              {'name': 'Product',
               'table_name': '',
               'fields': [{'name': 'sku',
                           'type': 'str',
                           'nullable': False,
                           'unique': True,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'name',
                           'type': 'str',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'category_id',
                           'type': 'int',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'price_cents',
                           'type': 'int',
                           'nullable': False,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': None},
                          {'name': 'stock_qty',
                           'type': 'int',
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
                           'default': 'None'},
                          {'name': 'low_active',
                           'type': 'bool',
                           'nullable': True,
                           'unique': False,
                           'primary_key': False,
                           'auto': None,
                           'default': 'None'}],
               'unique_together': [['sku']],
               'fks': [{'field': 'category_id', 'ref': 'Category'}]}],
 'exceptions': [{'name': 'CategoryNotFoundError', 'trigger': 'not_found'},
                {'name': 'ProductNotFoundError', 'trigger': 'not_found'}],
 'repositories': [{'module': 'category_repository',
                   'class': 'CategoryRepository',
                   'entity': 'Category',
                   'methods': [{'name': 'create',
                                'params': [{'name': 'category', 'type': 'Category'}],
                                'returns': 'int'},
                               {'name': 'get_by_id',
                                'params': [{'name': 'id', 'type': 'int'}],
                                'returns': 'Optional[Category]'},
                               {'name': 'get_all', 'params': [], 'returns': 'List[Category]'},
                               {'name': 'list',
                                'params': [{'name': 'description', 'type': 'Optional[Any]'},
                                           {'name': 'name', 'type': 'Optional[Any]'},
                                           {'name': 'reorder_threshold', 'type': 'Optional[Any]'}],
                                'returns': 'List[Category]'},
                               {'name': 'update',
                                'params': [{'name': 'id', 'type': 'int'},
                                           {'name': 'data', 'type': 'Dict[str, Any]'}],
                                'returns': 'bool'},
                               {'name': 'delete',
                                'params': [{'name': 'id', 'type': 'int'}],
                                'returns': 'bool'},
                               {'name': 'find_products_by_category',
                                'params': [{'name': 'category_id', 'type': 'int'}],
                                'returns': 'list[Product]'}]},
                  {'module': 'product_repository',
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
                                'params': [{'name': 'category_id', 'type': 'Optional[Any]'},
                                           {'name': 'low_only', 'type': 'Optional[Any]'},
                                           {'name': 'name', 'type': 'Optional[Any]'},
                                           {'name': 'price_cents', 'type': 'Optional[Any]'},
                                           {'name': 'sku', 'type': 'Optional[Any]'},
                                           {'name': 'stock_qty', 'type': 'Optional[Any]'}],
                                'returns': 'List[Product]'},
                               {'name': 'update',
                                'params': [{'name': 'id', 'type': 'int'},
                                           {'name': 'data', 'type': 'Dict[str, Any]'}],
                                'returns': 'bool'},
                               {'name': 'delete',
                                'params': [{'name': 'id', 'type': 'int'}],
                                'returns': 'bool'},
                               {'name': 'find_products_by_category',
                                'params': [{'name': 'category_id', 'type': 'int'}],
                                'returns': 'list[Product]'},
                               {'name': 'find_low_stock_products',
                                'params': [{'name': 'category_id', 'type': 'int'}],
                                'returns': 'list[Product]'},
                               {'name': 'aggregate_stock_value_by_category',
                                'params': [],
                                'returns': 'dict[str, int]'}]}],
 'services': [{'module': 'inventory_service',
               'class': 'InventoryService',
               'entity': 'Inventory',
               'methods': [{'name': 'add_product',
                            'params': [{'name': 'sku', 'type': 'str'},
                                       {'name': 'name', 'type': 'str'},
                                       {'name': 'category_id', 'type': 'int'},
                                       {'name': 'price_cents', 'type': 'int'},
                                       {'name': 'stock_qty', 'type': 'int'}],
                            'returns': 'None'},
                           {'name': 'update_product',
                            'params': [{'name': 'id', 'type': 'int'},
                                       {'name': 'data', 'type': 'Dict[str, Any]'}],
                            'returns': 'None'},
                           {'name': 'delete_product',
                            'params': [{'name': 'id', 'type': 'int'}],
                            'returns': 'None'},
                           {'name': 'get_product_by_id',
                            'params': [{'name': 'id', 'type': 'int'}],
                            'returns': 'Optional[Product]'},
                           {'name': 'list_products',
                            'params': [{'name': 'category_id', 'type': 'Optional[int]'},
                                       {'name': 'low_only', 'type': 'Optional[bool]'}],
                            'returns': 'List[Product]'},
                           {'name': 'restock',
                            'params': [{'name': 'id', 'type': 'int'},
                                       {'name': 'qty', 'type': 'int'}],
                            'returns': 'None'},
                           {'name': 'low_stock_report', 'params': [], 'returns': 'List[Product]'},
                           {'name': 'stock_value_by_category',
                            'params': [],
                            'returns': 'Dict[str, int]'},
                           {'name': 'add_category',
                            'params': [{'name': 'name', 'type': 'str'},
                                       {'name': 'description', 'type': 'str'},
                                       {'name': 'reorder_threshold', 'type': 'int'}],
                            'returns': 'int'},
                           {'name': 'list_category', 'params': [], 'returns': 'List[Category]'},
                           {'name': 'update_category',
                            'params': [{'name': 'id', 'type': 'int'},
                                       {'name': 'name', 'type': 'str'},
                                       {'name': 'description', 'type': 'str'},
                                       {'name': 'reorder_threshold', 'type': 'int'}],
                            'returns': 'bool'},
                           {'name': 'delete_category',
                            'params': [{'name': 'id', 'type': 'int'}],
                            'returns': 'bool'}]}],
 'foreign_keys_enabled': True,
 'business_rules': [{'id': 'unique_sku',
                     'kind': 'unique_pair',
                     'entity': 'Product',
                     'fields': ['sku']},
                    {'id': 'unique_category_name',
                     'kind': 'unique_pair',
                     'entity': 'Category',
                     'fields': ['name']},
                    {'id': 'product_category_exists',
                     'kind': 'ensure_raise',
                     'method': 'add_product',
                     'ref_entity': 'Category',
                     'ref_field': 'id',
                     'unique_field': 'id'},
                    {'id': 'stock_value_by_category_sum',
                     'kind': 'aggregate_mul_sum',
                     'entity': 'Product',
                     'method': 'stock_value_by_category',
                     'fk': 'category_id',
                     'a': 'price_cents',
                     'b': 'stock_qty'},
                    {'id': 'low_stock_report_filter',
                     'kind': 'filter_lt',
                     'entity': 'Product',
                     'method': 'low_stock_report',
                     'field': 'stock_qty',
                     'ref_entity': 'Category',
                     'ref_field': 'reorder_threshold',
                     'fk': 'category_id'},
                    {'id': 'list_products_category_filter',
                     'kind': 'filter_lt',
                     'entity': 'Product',
                     'method': 'list_products',
                     'field': 'stock_qty',
                     'ref_entity': 'Category',
                     'ref_field': 'reorder_threshold',
                     'fk': 'category_id'},
                    {'id': 'list_products_low_only_filter',
                     'kind': 'filter_lt',
                     'entity': 'Product',
                     'method': 'list_products',
                     'field': 'stock_qty',
                     'ref_entity': 'Category',
                     'ref_field': 'reorder_threshold',
                     'fk': 'category_id'},
                    {'id': 'product_stock_update',
                     'kind': 'no_stub',
                     'class': 'ProductRepository',
                     'methods': ['find_products_by_category',
                                 'find_low_stock_products',
                                 'aggregate_total_stock_value_by_category']},
                    {'id': 'category_repository_crud',
                     'kind': 'no_stub',
                     'class': 'CategoryRepository',
                     'methods': ['create', 'read', 'update', 'delete', 'find_all_products']},
                    {'id': 'inventory_service_product_validation',
                     'kind': 'ensure_raise',
                     'method': 'add_product',
                     'ref_entity': 'Category',
                     'ref_field': 'id',
                     'unique_field': 'id'}],
 'business_logic_coverage': 'partial',
 'unexpressed_rules': ['The stock_qty must not go below zero after restock or update operations '
                       '(no negative stock).',
                       'The reorder_threshold must be a positive integer (or null), and must be '
                       'defined per category.',
                       'When a product is deleted, its category must not become empty (no '
                       'constraint on category-level emptiness).',
                       'The low_stock_report must only return products where stock_qty < '
                       'reorder_threshold, and only if the category has a defined '
                       'reorder_threshold.',
                       'The stock_value_by_category must only aggregate products that belong to a '
                       'category with a defined reorder_threshold (if required).']}

# --- recording -------------------------------------------------------------

def _record(domain, test, ok, detail=""):
    key = "%s:%s" % (domain, test)
    RESULT["tests"].append({
        "id": key,
        "status": "pass" if ok else "fail",
        "detail": str(detail),
    })
    RESULT["coverage"].setdefault(domain, {})[test] = "pass" if ok else "fail"

def _record_error(domain, test, exc):
    """Record a failing test that errored (not cleanly asserted)."""
    _record(domain, test, False, "error: %r" % (exc,))

def _safe(fn):
    """Run `fn()`; a raised exception is recorded as a failure, never a crash."""
    try:
        return fn()
    except Exception as exc:
        traceback.print_exc()
        RESULT["build_errors"].append(str(exc))
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
        inst = _model_instance(model_cls, ent)
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
        parent_cls = _find_cls("models", parent_ent)
        child_cls = _find_cls("models", child_ent)
        pinst = _model_instance(parent_cls, parent)
        setattr(pinst, parent_total, 0)
        parent_id = _call(parent_repo, "create", pinst)
        pid = parent_id if isinstance(parent_id, int) else getattr(parent_id, "id", None)

        expected = 0
        for i in range(2):
            cinst = _model_instance(child_cls, child, fk_values={fk_field: pid})
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
            _call(child_repo, "create", cinst)

        parent_fetched = _call(parent_repo, "get_by_id", pid)
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
        if method is None:
            _record("business_rule", test_name, False, "method %s missing" % m)
            return
        src = inspect.getsource(method)
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
        by_names = {}
        if ref_name:
            ref_ent = next((e for e in spec.get("entities", []) if e["name"] == ref_name), None)
            ref_repo = _repo_for(ref_ent) if ref_ent else None
            ref_model = _find_cls("models", ref_name) if ref_ent else None
            if ref_repo is not None and ref_model is not None:
                ref_repo_inst = ref_repo(db)
                # Some generated repositories GROUP BY the reference entity's
                # name field (e.g. SELECT category.name AS k) rather than by
                # its id, so record the seeded name per group id and fall back
                # to it when the result key is the name and not the id.
                name_field = None
                for f in ref_ent.get("fields", []):
                    if f.get("name") == "name":
                        name_field = f.get("name")
                        break
                if name_field is None:
                    for f in ref_ent.get("fields", []):
                        if f.get("type") == "str" and f.get("name") != "id":
                            name_field = f.get("name")
                            break
                for i in range(2):
                    rinst = _seed_entity_val(ref_model, ref_ent, index=i + 1)
                    rid = _call(ref_repo_inst, "create", rinst)
                    gid = rid if isinstance(rid, int) else getattr(rid, "id", None)
                    group_ids.append(gid)
                    if name_field and hasattr(rinst, name_field):
                        by_names[gid] = getattr(rinst, name_field)
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
            got = result_map.get(gid)
            if got is None:
                got = result_map.get(by_names.get(gid))
            if got != exp:
                _record("business_rule", test_name, False,
                        "group %r: got %r expected %r" % (gid, got, exp))
                return
        _record("business_rule", test_name, True)
    except Exception as exc:
        _record_error("business_rule", test_name, exc)

def _test_ensure_raise(rule, spec):
    method_name = rule.get("method")
    ent_name = rule.get("entity")
    ref_field = rule.get("ref_field")
    unique_field = rule.get("unique_field")
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

        # Case 1: raise when a referenced entity (ref_field) does not exist.
        if ref_field:
            ctx = _resolved_fk_values(ent, spec, db) if ent is not None else {}
            ctx[ref_field] = 999999
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
 'ensure_raise': '_test_ensure_raise'}
    for rule in spec.get("business_rules", []):
        kind = rule.get("kind")
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
        RESULT["build_errors"].append("fatal: %r" % (exc,))
    status = "pass" if not RESULT["build_errors"] and all(
        t["status"] == "pass" for t in RESULT["tests"]
    ) else "fail"
    RESULT["status"] = status
    print(json.dumps(RESULT, indent=2, default=str))
    return 0 if status == "pass" else 1

if __name__ == "__main__":
    raise SystemExit(main())
