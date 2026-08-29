# Oracle Test Bloat Analysis — `prompt_inventory.txt`

## Summary

The oracle generates **13 tests** for the inventory prompt, but at least **4 are redundant, wrong, or misfired**. The root cause is a combination of:

1. **The oracle emitting `unique_pair` business rules that duplicate the schema-level `unique` test pass**
2. **A misapplied `no_stub` rule targeting a field instead of a method**
3. **A misapplied `filter_lt` rule on the wrong method**

---

## Full Test List

| Domain | Test ID | Status |
|---|---|---|
| `crud` | `Category` | ✅ Correct |
| `unique` | `unique_name` | ✅ Correct |
| `crud` | `Product` | ✅ Correct |
| `fk` | `fk_category_id` | ✅ Correct |
| `unique` | `unique_sku` | ✅ Correct |
| `business_rule` | `pair_unique_sku` | ⚠️ **Duplicate** |
| `business_rule` | `pair_unique_category_name` | ⚠️ **Duplicate** |
| `business_rule` | `filter_stock_below_reorder_threshold` | ⚠️ **Wrong kind** |
| `business_rule` | `agg_stock_value_by_category` | ✅ Correct |
| `business_rule` | `raise_category_exists_check` | ✅ Correct |
| `business_rule` | `nostub_product_low_active_default` | ❌ **Bug: field, not method** |
| `exception` | `CategoryNotFoundError` | ✅ Correct |
| `exception` | `ProductNotFoundError` | ✅ Correct |

---

## Root Cause Breakdown

### Issue 1 — `unique_pair` rules duplicate the `unique` test pass (2 extra tests)

The renderer already generates one structural test per unique field/constraint via `_test_unique()`. This covers both `Category.name` (unique) and `Product.sku` (unique).

The oracle **additionally** emits two `unique_pair` business rules:
```json
{"id": "unique_sku",           "kind": "unique_pair", "entity": "Product",  "fields": ["sku"]}
{"id": "unique_category_name", "kind": "unique_pair", "entity": "Category", "fields": ["name"]}
```

`_test_unique_pair` does **exactly the same thing** as `_test_unique` (creates two instances with same value, expects a raise). These are not just semantically equivalent — they run the identical verification path twice against the same fields.

**Why this happens:** The oracle system prompt describes `unique_pair` as a business rule kind, and the spec says `name (unique)` and `sku (unique)`. The LLM correctly recognizes these as uniqueness constraints but does not know that they will *also* be picked up automatically by the schema-driven unique pass. There is no instruction in `_TEST_SPEC_SYSTEM` or `_KIND_DETECT_SYSTEM` that says "do not emit unique_pair for fields already declared `unique: true` in `entities`".

**Fix surface:** In `oracle.py`'s `_TEST_SPEC_SYSTEM` or `_KIND_DETECT_SYSTEM`, add an instruction like:
> "Do NOT emit a `unique_pair` rule for a field you already declared as `unique: true` in the entity definition — the structural test will cover it automatically."

Or, alternatively, in `renderer.py`'s `_run_all()`, deduplicate by skipping `unique_pair` rules for fields already present in any entity's `unique: true` or `unique_together` list.

---

### Issue 2 — `no_stub` applied to a field instead of a method (1 broken test)

The oracle emits:
```json
{"id": "product_low_active_default", "kind": "no_stub", "class": "Product", "methods": ["low_active"]}
```

`low_active` is a **data field** on the `Product` model, not a method. The `_test_no_stub` executor calls `inspect.getsource()` on it — which will either find the class-level type annotation (not real method body), raise `TypeError`, or silently pass/fail in an undefined way.

**Why this happens:** The oracle misread `low_active (optional bool, default False)` from the prompt as something to test for implementation. There is no meaningful "no_stub" concept for a field. The `no_stub` kind description says *"the given methods on class must be implemented, not a stub"*, but the LLM applied it to a field with a default value.

**Fix surface:** The `no_stub` kind description in `rule_kinds.py` should be more restrictive. Additionally, consider adding a validation step in `spec_schema.py`'s `v_test_spec()` that checks `no_stub` rules reference declared service/repo methods, not entity fields.

---

### Issue 3 — `filter_lt` applied to the wrong method (1 semantically incorrect test)

The oracle emits:
```json
{
  "id": "stock_below_reorder_threshold",
  "kind": "filter_lt",
  "entity": "Product",
  "method": "list_products",
  "ref_entity": "Category",
  "ref_field": "reorder_threshold",
  "fk": "category_id"
}
```

The `filter_lt` kind's executor (`_test_filter_lt`) expects that `method()` can be called **with no arguments** (or introspected positionally) and returns only rows where `entity.field < ref_entity.ref_field`. However, `list_products(category_id=None, low_only=None)` is a **multi-purpose filter method** with two optional flags. Calling it with no arguments returns all products, not a threshold-filtered set. The test will almost certainly fail or produce a misleading result.

The intended behavior to test here is `low_stock_report()` (which returns products where `stock_qty < reorder_threshold`) — that method has no parameters and directly models the `filter_lt` semantics.

**Why this happens:** The oracle is forced to pick from a constrained set of `kind` options. `filter_lt` is the only kind that approximately matches the low-stock concept, but it was bound to `list_products` (the more general method) instead of `low_stock_report`. The oracle probably confused the two because the prompt defines both, and the filter parameter names overlap.

**Fix surface:** The `filter_lt` description in `rule_kinds.py` should clarify that the method must be a **dedicated filter** (takes no or one argument, not a general query method). Alternatively, a dedicated `low_stock_report` test kind with cleaner semantics would be more appropriate.

---

## Also Present in `test_spec.json` — Structural Noise

The `test_spec.json` also contains:
- **`unique_together` mirrors `unique: true` fields** — both `Category` and `Product` have `unique_together: [["name"]]` and `unique_together: [["sku"]]` respectively, which directly duplicates the `unique: true` fields. The `_test_unique` renderer already collects from *both* `unique fields` and `unique_together`, but deduplicates by test name (`unique_<field>`), so these happen to collapse. This is harmless but is noise in the spec.
- **`InventoryService.entity` = `"Inventory"`** — there is no `Inventory` entity. The spec lists `Category` and `Product`. This causes `_service_for(ent)` to fail discovery by entity name, but the service is found by scanning `TEST_SPEC["services"]` as a fallback, so it doesn't break anything — but it is semantically wrong.

---

## Summary of Fixes

| Priority | Location | Fix |
|---|---|---|
| **High** | `oracle.py` (`_TEST_SPEC_SYSTEM` / `_KIND_DETECT_SYSTEM`) | Instruct the LLM not to emit `unique_pair` for fields already declared `unique: true` in the entities section |
| **High** | `renderer.py` `_run_all()` | Deduplicate `unique_pair` rules that overlap with existing entity `unique` fields / `unique_together` at render time |
| **Medium** | `rule_kinds.py` `no_stub` description | Clarify that `methods` must be actual service/repo methods, not model fields |
| **Medium** | `spec_schema.py` `v_test_spec()` | Validate `no_stub` rules reference methods in declared repos/services |
| **Low** | `oracle.py` (`_TEST_SPEC_SYSTEM`) | Clarify `filter_lt` is for dedicated single-purpose filter methods, not general query methods |
