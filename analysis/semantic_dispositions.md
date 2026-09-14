# Dispositions for S1–S19 (Family-B semantic problems)

This document closes the loop on `analysis/semantic_problems.md`: for every
catalogue entry it states **how the defect is now prevented, detected, or why
it is left documented**. A defect is only "closed" in one of three ways:

| Disposition | Meaning |
|---|---|
| **recipe** | The body is rendered deterministically from the design/contract, so the LLM can no longer author it wrongly. |
| **detected + refilled** | A static verifier rejects the LLM body and the violation text is fed back to a bounded refill. |
| **documented** | Not generically renderable; the reason is recorded here instead of being papered over. |

## The anti-tautology rule (load-bearing)

Two checks exist and they must never share a source:

* the **contract extractor** (`agentlib/pipeline/method_contract.py`) reads the
  **PROMPT only** — plus the design's method *signatures*, which merely name the
  methods to describe. It never sees a generated body;
* the **body verifier** (`method_contract_violations`,
  `_repo_entity_coherence_violations`, `_semantic_fill_violations`,
  `_undefined_name_violations`) reads the **generated body only**. It never sees
  the prompt.

If a single source produced both, the check would restate the code and could
never fail. The executed oracle (`behavior_tests/spec_invariants.py`) is a third
independent source — assertions transcribed from the prompt's own bullets,
evaluated against concrete data through the public API — and
`behavior_tests/mutate_semantic.py` proves it is load-bearing by requiring every
invariant to fail on a mutated snapshot.

## What was implemented

1. **Repo/entity coherence (deterministic, design-only)** —
   `_repo_entity_coherence_violations` in `agentlib/generation/service_render.py`.
   A method whose NAME names a designed entity E must reach E's own repository
   when it reaches any repository at all. Runs as a fill validator, so a
   mis-wired body is rejected and refilled.
2. **Contract effects + compound reports + period totals (deterministic)** —
   `agentlib/kernel/service/contract_effects.py` renders a `bool`-returning
   workflow's prompt-stated effects (`counter_delta`, `flag_toggle`,
   `flag_set`, `status_set`) for an anchor row reached by one id parameter;
   `agentlib/kernel/service/report_parts.py` renders a COMPOUND report whose
   pieces the specification names (`total`, `per_category`, `budget_status`
   for a month; `monthly_totals`, `top_categories`, `average_monthly` for a
   year), applying the period predicate to EVERY piece rather than to a
   headline number; `agentlib/kernel/repo/aggregates.py` renders the
   repository-side budget status (`_budget_status_body`) by comparing the
   month's SPENDING to the month's limit. `_period_impl` renders a plain
   period-scoped total. `compile_contract_impl` is deliberately narrow: it
   declines (leaving the LLM fill) for guards, `create_child`,
   multi-parameter or non-`bool` shapes.
3. **Prompt-derived method contracts + static body verification** —
   `extract_method_contracts` (LLM, schema-constrained, evidence-closed against
   a verbatim span of the spec) produces `{shape, filters, effects, guards,
   returns_entity}`; `method_contract_violations` then rejects a body that does
   not read a declared filter parameter or that never reaches the entity it must
   return.
4. **Executed oracle + mutation testing** — `behavior_tests/spec_invariants.py`,
   `behavior_tests/semantic_oracle.py`, `behavior_tests/mutate_semantic.py`,
   driven by `run_semantic_oracle.py`.
5. **Bounded refill** — a rejected body's violations travel back to the retry
   (existing infra); the contract verifier is one more rejection source.

## Disposition table

| # | Defect | Disposition | Mechanism / evidence |
|---|---|---|---|
| S1 | `get_monthly_report(month)` ignores `month` | **recipe** | The contract names the report's PIECES (`report_parts`), so `agentlib/kernel/service/report_parts.py` renders the body and applies the period predicate to every piece; `_period_impl` covers the single-total shape. Oracle: "get_monthly_report filters by month" (the report's own total is Jan=1000 vs Mar=2000 AND every breakdown sums to it) plus "get_monthly_report returns the spec's three pieces"; both killed by stubbing `get_monthly_report`. |
| S2 | `get_yearly_summary(year)` wrong shape | **recipe** | Same route with the year's pieces: `monthly_totals`, `top_categories`, `average_monthly`, scoped to the year. Oracle: "get_yearly_summary exposes monthly totals" (2023's 5000 excluded, 1000/2000 present) and "get_yearly_summary returns top categories and the average". |
| S3 | `get_category_spending` mis-keyed dict + mistyped | **recipe** | The aggregate is keyed `{'total', 'count'}` by `_filtered_aggregate_body` in `agentlib/kernel/repo/aggregates.py` — the same convention as `_period_aggregate_body` — instead of echoing the filter that produced it (`{'category_id': 4000}`). The mistyped service signature is closed too: `_align_delegated_returns` gives a pure-delegation method the repository's return type, so the shipped service method is `-> Dict[str, Any]`, not `-> int`. Oracle: "get_category_spending reports a total" and "get_category_spending keys its aggregate as 'total'". |
| S4 | `get_expense_report(id)` reads keys the repo never returns | **detected + refilled** | `_REPO_ACCESSOR_RULE` is injected into every fill's system message (a repo getter returns a MODEL INSTANCE, never a dict). Verified in the shipped body: it now uses `expense.category_id` / `category.name` attribute access. |
| S5 | `detect_recurring` does not detect | **recipe** | `_detect_and_mark_impl` renders a real group-and-mark body (the fill filtered on the very flag it had to set). Oracle: "detect_recurring marks recurring rows". |
| S6 | `detect_category(id)` treats `id` as a year | **detected + refilled** | Root cause found: `_apply_impl_floors` stamped a `total_in_period` impl on a method whose single parameter is an ENTITY ROW ID, so `id` became a year. A period total now requires the parameter to actually name a period, so the method carries no impl; the fill must then satisfy `_repo_entity_coherence_violations` (the name names Category ⇒ it must reach `category_repo`). |
| S7 | Budget semantics wrong | **recipe** | Two deterministic paths. Repository side: `_budget_status_body` (`agentlib/kernel/repo/aggregates.py`) reads the budget row's month, sums the SAME month's spending and compares it to `amount_limit_cents` — the old body compared the limit to the category's own `monthly_budget` FIELD and never read spending at all. Report side: `report_parts` renders per-category `budget_status` from the month's spend against the month's limit. Oracle: "repository budget status compares the limit to spending" (a March row with a 100-cent limit against 2000 spent must report an exceedance), "budget status compares the month, not lifetime spending" (a month with no spending must NOT be exceeded) and "budget status reflects actual spending"; the first two are killed by stubbing `check_budget_status` / `get_monthly_report`. |
| S8 | `return_book` never increments `available_copies` | **recipe** | Contract → `counter_delta` on Book.available_copies, and the same effect body stamps the row: the shipped `return_book` sets `return_date`, sets `status`, then increments the book's copies. Oracle: "borrow then return restores available_copies" asserts all THREE effects, including `return_date` — a body that only increments and flips the status still leaves the date empty. |
| S9 | `return_book` refuses an overdue loan | **recipe** | Deterministic effect body has no lateness guard. Oracle: "return_book accepts an overdue loan". |
| S10 | `get_overdue_loans` returns books | **detected + refilled** | `_repo_entity_coherence_violations` (the name names Loan ⇒ it must reach `loan_repo`). Oracle: "get_overdue_loans returns overdue LOANS" asserts the returned row is a `Loan`. |
| S11 | `renew_membership` does not toggle `is_active` | **recipe** | Contract → `flag_toggle`; `_contradicts_flag_effect` also drops the self-contradicting `reject_inactive` guard. Oracle: "renew_membership toggles is_active". |
| S12 | `list_author` returns books | **detected + refilled** | Same coherence gate (name names Author ⇒ `author_repo`). |
| S13 | `get_member_history` discards the history | **detected + refilled** | The `returns_entity` check first rejected the legitimate delegation ("never calls `loan_repo`") and stubbed the method; it now also accepts a body that delegates to a DESIGNED repository method whose declared return yields the entity. Verified in the shipped bodies: `history` / `get_member_history` → `member_repo.get_member_loan_history(member_id)` (declared `List[Loan]`), and the run reports `salvaged 6/6` with no method left stubbed. Oracle: "member history surfaces the member's loans". |
| S14 | `borrow_member(id)` always raises | **recipe (surface)** | An earlier revision of this row claimed "the `member_borrow` shape is gone" — that was **false at the time**: `member borrow --id N` was still GENERATED (the CLI design unioned an over-generated surface onto the prompt's) and it always raised `ValidationError: Book not specified for borrowing`, a dead command a user following the specification could reach. It is gone now for the right reason: the surface is derived from the PROMPT's own command list (`agentlib/pipeline/cli_spec.py`), and the prompt asks for `library borrow` / `library return` only. `borrow_book` is therefore the only borrow workflow, and it is oracle-covered end-to-end ("borrow then return restores available_copies"). |
| S15 | `borrow_book` over-restricts | **oracle-enforced** | Oracle round-trip: borrow must decrement, return must restore. |
| S16 | `Member.is_active` default not captured | **recipe** | `agentlib/pipeline/model_defaults.py` transcribes defaults from the PROMPT alone and stamps them onto designed fields. Root cause of the miss: the design LLM stamps a default the renderer must STRICTLY reject, and the pass used to defer to it — it now defers only to a RENDERABLE default. Verified: `available_copies: int = 1`, `is_active: bool = True`. |
| S17 | `BookRepository.search_book` omits author | **recipe** | The lone-term search recipe LIKEs the entity's own text columns AND the text columns of every entity it references through a `<ref>_id` column, joined in. Verified in the shipped body: `LEFT JOIN authors ON books.author_id = authors.id … OR authors.name LIKE ?`. Oracle: "search_books finds a book by its author's name" (a token that appears in no book column); killed by the dedicated `search_ignores_join` mutant. |
| S18 | `bool`-returning methods carry no invariant enforcement | **partially closed — documented remainder** | `counter_delta` / `flag_toggle` / `flag_set` / `status_set` effects are now deterministic, and the fill forbids guards the specification does not state (`_NO_UNSTATED_GUARD_RULE`). **Remainder:** a workflow that must CREATE a child row needs the child's required fields stamped (library's `Loan(due_date, status)`), which is a domain decision neither independent source can supply, so `borrow_book` stays LLM-filled — but the part that IS checkable is checked by execution: the oracle asserts the `borrow → return` round-trip (decrement, then restore). The over-restriction did not recur, and the shipped guard is surgical — `loan_repo.get_loan_by_book_id_and_member_id(book_id, member_id)` compares the PAIR its message names, so it no longer blocks borrowing a different book. The general lever is `_NO_UNSTATED_GUARD_RULE`; there is deliberately **no** "borrowing a second, different book" oracle probe, because such a probe would only be meaningful once the child-creating workflow is itself deterministic — asserting it against a fill would turn an LLM-variance risk into a flaky gate. |
| S19 | Dead / duplicated methods | **fixed (surface)** | The prune ("keep only the commands the specification lists") used to be impossible: the deterministic surface it pruned against was itself incomplete — it lacked spec-required commands (`overdue`, `history`), so pruning by it removed working behaviour, and commit `30521e5` reverted the attempt. The lever was wrong, not the idea: the surface is no longer DERIVED from the design's methods, it is READ from the prompt's own command list (`agentlib/pipeline/cli_spec.py`), so it is complete by construction. `agentlib/pipeline/cli_propagate.py` now takes `preserve_surface=True` and skips its merge/drop loop entirely, and no LLM CLI design runs at all. Shipped counts: library_system 24 → 9 commands (the prompt's 9), expenses 22 → 14 (the prompt's 14); `run_cli_conformity.py` asserts the equality. |

## Residual, explicitly non-generic

* **S18's child-creating workflows** are the one remaining semantic gap: a
  workflow that must CREATE a child row needs that child's required fields
  stamped (library's `Loan(due_date, status)`), which is a *domain decision*
  neither independent source can supply — the design does not declare the value
  and the prompt does not state it — so a deterministic recipe would have to
  invent it. The part that IS checkable is checked by execution (the oracle's
  borrow → return round-trip) and the fill is constrained by
  `_NO_UNSTATED_GUARD_RULE`.
* **S19** is a surface-policy question, not a rendering one; see the table.

## The prompt-derived CLI surface (this revision)

Four defects reported against a FRESH `library_system` / `expenses` regeneration
are closed by one change of source of truth, plus two bounded recipes.

**(a) The CLI surface is read from the prompt, not designed.** —
`agentlib/pipeline/cli_spec.py`. For a specification that ENUMERATES its
command line (`library book add --title --isbn …`), the CLI is not a design
problem: the specification already states it. `build_prompt_cli_surface` parses
that list POSITIONALLY (everything before the first `--option` is the group
path, the last token is the command name), takes option names verbatim
(`[--opt]` optional, `--opt` required), resolves each command's target against
the methods the SPEC declares (`service_contract`), and never invents, renames
or flattens anything. `manifest.py` then skips the LLM CLI design entirely and
`cli_propagate._propagate_cli_commands(..., preserve_surface=True)` skips its
merge/drop loop. A loud `[conformity] MISSING command:` is printed for any
spec command the shipped surface fails to carry, so a regression cannot pass
silently. Closed: `library book add --copies` vs `--available-copies`,
`library member add` vs `member add`, `library overdue` vs `overdue`,
`expense category …` vs `category …`, `--amount` vs `--amount-cents`,
`--category` vs `--category-id`, `--method` vs `--payment-method`,
`expense report monthly` vs `expense monthly`, `expense recurring detect` vs
`expense recurring`, and the 15 + 8 over-generated commands (S19).

**(b) The method signature follows the surface.** —
`agentlib/pipeline/cli_spec.py::_relax_signature_to_surface`. A parameter the
command supplies through an OPTIONAL option, or through no option at all, must
be OPTIONAL on the method — otherwise `_cli_wiring_errors` drops the command as
unsatisfiable (`library member add` was lost to an uncovered `is_active`). Only
a parameter bound to a REQUIRED option keeps its declared type.
`align_surface_to_design` then re-binds every option to the DESIGNED parameter
that actually carries it and mirrors the parameter's primitive onto the click
option, so the value the user types reaches the service.

**(c) An optional date is stamped, not `None`.** — Defect 1, the crash.
`add_expense(..., expense_date: Optional[str] = None, ...)` now opens with
`if expense_date is None: expense_date = datetime.date.today().isoformat()`
(`_generic_service_delegation` in `agentlib/generation/service_render.py`). The
general rule: a non-nullable `date`/`datetime` field exposed as an OPTIONAL
option gets a deterministic fallback (`date.today()` / `datetime.now()`), the
same way a `str` field gets its spec default and `payment_method` gets `'cash'`.
Before: `sqlite3.IntegrityError: NOT NULL constraint failed: expenses.expense_date`,
exit 1, on the prompt's own `expense add --amount --description --category`.

**(d) A filter on the owner's own FK column is conditional and consumes its
other params.** — `agentlib/kernel/repo/bodies.py` §8.12b. The owner-ref recipe
emitted a hard `SELECT r.* FROM books r JOIN authors o ON r.author_id = o.id
WHERE o.id = ?` bound to `author_id`, and ignored every other parameter. When
the caller omits the optional `--author`, click passes `None`, `o.id = NULL`
matches nothing and `library book list` answered `[]` — on the prompt's own
"list all books, optionally filtered by author" path; `--available-only` was
silently dropped. The recipe now recognises that a param which IS the owner's
FK column needs no JOIN, emits a conditional `WHERE` builder, and resolves the
remaining params against the owner's columns through `_own_filter_specs`
(`available_only` → the unique field starting with `available_` →
`available_copies > 0`; a plain field name → equality). It declines rather than
guess when a param cannot be explained.

Closed: `expense add --amount --description --category` without
`--expense-date` exits 0 with today's date; `library book list` lists every
book; `library book list --author N` filters by author; `--available-only`
guards `available_copies > 0`.

## Re-verifying

```
python3 -m compileall -q agentlib behavior_tests
python3 run_semantic_oracle.py            # invariants + mutation testing
python3 run_facade_execution.py --prompt library_system --prompt expenses
python3 run_cli_conformity.py             # prompt surface == shipped CLI
```

`run_cli_conformity.py` is the new deterministic gate for (a)+(b): for every
command a specification enumerates it asserts the group path exists and every
named option is declared, and for every command the CLI exposes it asserts the
specification asked for it. It is LLM-free and needs no fixture data.

Expected: `library_system` 15/15 invariants with every mutant killed and the
façade 9/9; `expenses` 16/16 invariants with every mutant killed and the façade
14/14 (the prompt's own 14 commands); `inventory` 12/12; `cli_tool` 5/5.
Observed on the current revision — all measured on the freshly regenerated
projects, together with the command-line conformity gate:

```
library_system: 15/15 invariant(s) hold
library_system: mutation pass (baseline 15/15)
expenses: 16/16 invariant(s) hold
expenses: mutation pass (baseline 16/16)
ALL SEMANTIC CHECKS PASS

[cli_tool] status=pass       mapped=5  unmapped=0 pass=5  fail=0
[inventory] status=pass      mapped=12 unmapped=0 pass=12 fail=0
[expenses] status=pass       mapped=14 unmapped=0 pass=14 fail=0
[library_system] status=pass mapped=9  unmapped=0 pass=9  fail=0

[expenses]       status=pass prompt_commands=14 violations=0
[inventory]      status=pass prompt_commands=11 violations=0
[library_system] status=pass prompt_commands=9  violations=0
```

Every command each specification enumerates was additionally executed end to
end against a fresh database (`library_system` 16/16 paths, `expenses` 22/22,
`inventory` 16/16, exit 0 throughout), and the commands the specifications do
NOT request are absent (`expense update`, `expense get`,
`expense report --id`, `library member borrow --id`, `loan add` all answer
`No such command` / `No such option`).

**Dual-flag discovery (library_system façade 9/9).** Re-running the library
façade on a freshly generated project exposed a second, independent defect on
the TESTER side: click writes a tri-state boolean as ONE literal
(``'--is-active/--no-is-active'``), and ``facade_discovery`` recorded that
compound as the option's only name. The mapper then rejected a perfectly valid
``--is-active`` as a "stray flag/arg not declared on member add" and left
intention I4 unmapped — the façade sat at 8/9 with no code defect behind it.
``_read_option_arg`` now splits the compound on ``/`` and
``_has_dual_flag_form`` marks the resulting option as a value-less boolean, so
the discovered option is ``names: ['--is-active', '--no-is-active']`` with
``flag: true``. I4 maps and the façade is 9/9. This is the same class of defect
as the tri-state flag the RENDERER emits for ``is_active`` (S16): the option is
a flag, and every consumer must read it as one.

`inventory` used to sit at 11/12: `product update` sent every option into the
`data` dict, including the ones the caller omitted (click yields None), and the
repository wrote those Nones, so `--name` alone set `sku = NULL` and died on
`NOT NULL constraint failed: products.sku`. The generated CLI now filters the
None entries out of the partial-update payload (`cli_render._build_service_call`),
which is the same convention the deterministic service update path already used.
## Second pass on a fresh regeneration (this revision)

Three further defects surfaced by regenerating `library_system` and `expenses`
and exercising every command the specifications enumerate.

**(e) The shipped signature now uses the specification's own parameter names.**
— `agentlib/pipeline/service_contract.py::apply_service_contract_params`,
called from `manifest.py` before the CLI surface binds its options. The
specification declares its service signatures verbatim —
`list_expenses(category_id, start_date, end_date, payment_method)` — and the
design LLM paraphrased a RANGE ROLE, shipping
`list_expenses(category_id, from_date, to_date, payment_method)`.
`check_service_contract` reported the mismatch and *nothing repaired it*, so a
caller who followed the specification got a `TypeError` while the CLI
(`--from-date`) worked. The floor renames a designed parameter to the
spec-declared name ONLY when the rename is a permutation (as many extra design
params as there are missing spec params) and both names denote the same range
role (`start_`/`from_`/`after_`/`since_` = lower bound,
`end_`/`to_`/`until_`/`before_` = upper bound) — the same role vocabulary
`_range_role` already uses to pair filters. Running it *before*
`align_surface_to_design` is what lets the CLI's `--from-date` bind to the
spec's own `start_date` instead of to the paraphrase.

**(f) A group-by equal to the entity's own unique key is never a report.** —
`agentlib/generation/service_render.py::_apply_impl_floors`. The
grouped-count floor stamped `count_by_group` on `list_budget` because its
`List[Dict]` return plus two declared filter params (`category_id`, `month`)
matched the "grouped report" shape — and that pair is exactly Budget's
`UNIQUE(category_id, month)`, so every group held one row and
``budget list`` answered ``[{'category_id': 1, 'month': '2024-01',
'count': 1}]`` instead of the budget rows the specification's own
``budget list`` asks for. Counting by an entity's unique key can never group
anything and replaces the entity's columns with a synthetic `count`, so the
stamp is now skipped when `group_by` equals the entity's `unique_together`
key; the method is left unstamped and rendered by the generic CRUD
delegation, which is the correct body.

**(g) A boolean list-filter is never a bound value.** —
`agentlib/kernel/repo/threshold_compare.py` (`_flag_threshold_spec`),
`_filter_flag_refs` (`agentlib/kernel/service/common.py`),
`_apply_filter_floors` (`service_render.py`) and `_render_repository_file`
(`repo_render.py`). `list_products(category_id, low_only)` was recorded as an
ordinary bound filter (`low_only` -> `stock_qty <= ?`), which is doubly wrong:
the click flag defaults to `False`, and the rendered guard is `is not None`,
so that `False` was BOUND — `AND stock_qty <= 0` — and the UNFILTERED
`product list` listed nothing at all. A bool param is never a bound value, so
it is rewritten to the comparison it actually means: when the design's own
shape says the threshold lives on the ROW THE FK POINTS AT (the entity
carries exactly one FK and one numeric column the filter is recorded against;
the referenced entity carries exactly one OPTIONAL numeric column), the filter
becomes `below_ref` — a JOIN with `t.<value> < r.<threshold>` guarded on the
flag's truthiness. Otherwise it degrades to a constant predicate on the
param's own column (`= 1` for a bool column, `> 0` otherwise), which is what
the former `eq_true`/`gt_zero` ops already meant. `_BOOL_FILTER_TYPES` /
`_is_bool_param_type` decide which parameters are flags, accepting the
`bool`/`Boolean`/`Optional[bool]`/`bool | None` spellings and a trailing
default so the rewrite cannot be defeated by the spelling the design chose.

The compared column has TWO sources, because a parameter name need not mention
it: the name (`find_low_stock_products` names `stock`), or the column the
design itself RECORDED the filter against (`low_only` -> `stock_qty`).
Inventory's `low_only` carries no column word, so the first source found
nothing and the flag degraded to `AND stock_qty > 0` — "in stock", not "low
stock". `_flag_threshold_spec` now falls back to the declared column when it is
a numeric non-FK column of the entity, so the shipped `list()` reads
``if low_only: query += ' AND product.stock_qty <
category.reorder_threshold'`` — verified end to end: `product list` returns
every product unfiltered, `--low-only` returns only the one below its
category's threshold, and after a `restock` above it the same flag returns `[]`.

**(h) A canonical CRUD list name is never a grouped report.** —
`agentlib/generation/service_render.py::_apply_impl_floors`, using
`_is_generic_crud_name`. The grouped-count floor also stamped `count_by_group`
on `list_expenses(category_id, start_date, end_date, payment_method)`: its
`List[Dict]` return plus its declared filter params matched the "grouped
report" shape, so `expense list` answered
``[{'category_id': 1, 'payment_method': 'cash', 'count': 1}, …]`` instead of
the expenses the specification's own `expense list` asks for. A method named
`list_<entity>` / `list_<entities>` for a DESIGNED entity is exactly the CRUD
list the generic delegation tier owns — its `List[Dict]` annotation is only the
element shape the design chose — so the stamp is skipped for those names and
the method renders `return self.<entity>_repo.list(...)`.
## Interpretations accepted, not defects

* **`Member.membership_date` is nullable.** The specification marks only
  `Loan.return_date` "(nullable)" and gives explicit defaults to
  `available_copies (default 1)` and `is_active (default True)`;
  `membership_date` carries neither marker, so a strict reading of "only
  `return_date` is nullable" would make it `NOT NULL`. The design LLM chose an
  `Optional` field instead, so `library member add --name --email` stores
  `NULL` and `library member list` prints `membership_date=None`. This is
  neither a crash nor a surface deviation — every path the specification
  enumerates exits 0 — and the specification is genuinely ambiguous here: it
  does not mark `biography` or `birth_year` nullable either, yet those are
  plainly optional data, so "unmarked" cannot mean "required" without
  contradicting the spec's own intent. Left as the design's reading and
  recorded here rather than papered over by inventing a default the
  specification never states. Note the dated-fallback rule (c) applies to a
  `date`/`datetime` field exposed as an OPTIONAL CLI OPTION (the
  `--expense-date` shape); `membership_date` is not exposed on the CLI at all,
  so the rule that would stamp it does not fire.
## Renderer defects found by whole-surface evaluation (added after the CLI-conformity gate)

The dispositions above were found by reading generated projects. The three
below were found only by *executing every path the specification enumerates*
on a fresh regeneration, with the prompt-surface checker and the per-command
smoke tests as the source of truth. Each is a defect of the **generator**,
fixed in the generator, never by editing a generated file.

**(i) A TYPED design `default` must be flattened before anything reads it.** —
`agentlib/pipeline/manifest.py::_normalise_design_defaults`. The design model
writes a declared default either as a scalar (`"default": "cash"`) or as a
typed wrapper (`"default": {"value": False, "type": "bool"}`). Every consumer
downstream reads `default` as a scalar: the model renderer writes `= <default>`
on the dataclass, and `_generic_service_delegation` builds both
`<field>=(<field> if <field> is not None else <default>)` and the
`_nullable_or_defaulted` set (which treats "has a default" as "an omitted value
is safe to pass through"). An un-normalised wrapper therefore made a real
default invisible on BOTH sides at once:

* `models.py` rendered `is_recurring: bool` with **no** `= False`;
* `add_expense` passed the caller's `None` straight through, because the field
  looked "defaulted" and was excluded from the boolean fallback;

so the path the specification marks optional —
`expense add --amount 1.00 --description x --category 1`, with no
`--expense-date` — died on `sqlite3.IntegrityError: NOT NULL constraint failed:
expenses.expense_date` (it was first reproduced on the over-generated
`--amount-cents/--category-id` surface, and would have died on `is_recurring`
next). Normalised once, in place, where the entities are collected, so every
reader sees the scalar.

**(j) A stale `list_filtered` stamp must not shadow the shape recipes.** —
`agentlib/kernel/repo/bodies.py::_repo_method_body`, tier 1. The dispatcher's
first tier handles a designed `impl {"kind": "list_filtered"}` by delegating to
`self.list(...)`. A guard already recognised that `self.list()` yields ROWS and
so must not answer a scalar/status annotation — but it expressed that as
`return None`, which **exits the whole dispatcher**, skipping every later tier
including the dict-aggregate recipes. `expenses`' repository
`get_monthly_report(month) -> Dict[str, Any]` carried exactly that stamp, so it
stayed a stub, the LLM filled it with a raw row LIST under a `Dict` annotation,
and `expense report monthly` answered `monthly_report: None` (the service read
`.get('total')` off a list). Its twin `get_yearly_summary(year) -> Dict[str, Any]`
carried **no** stamp, reached the aggregate recipe, and was correct — the
asymmetry that exposed the bug. Fixed by falling *through* instead of bailing,
so a stamp that cannot describe the body no longer prevents a later recipe from
describing it.

**(k) A cents-typed CLI option must be entered as a DECIMAL.** —
`agentlib/generation/cli_render.py::_render_cli_file`. The money convention is
two-sided: integer cents in storage, decimal amounts for display *and* for
input. `_build_service_call` already routed every option bound to a `*_cents`
parameter through `money.from_decimal`, but the option itself was emitted
`type=int`, so `expense add --amount 12.50` died inside click
(`invalid literal for int() with base 10: '12.50'`) before the conversion could
run — the specification's `--amount` option could only be given a cent count.
Now a `*_cents` parameter renders `type=float` and is converted at the call
boundary; every other int option (an id, a cents field with no conversion such
as `--budget`) stays an int, and `from_decimal` still returns an `int`
UNCHANGED, so a cent-count input is never rescaled.

## The CLI surface is taken from the PROMPT, and this is now enforced

`agentlib/pipeline/cli_spec.py::build_prompt_cli_surface` parses the
specification's own enumerated command list and the surface is shipped
verbatim; `_reconcile_cli_design(..., preserve_surface=True)` may back-propagate
a missing service method but can never remove a command, and a removal is
reported as `[conformity] MISSING command: <path>` rather than shipped.
`run_cli_conformity.py` + `behavior_tests/conformity.py` are the executable
check: for every command the prompt lists they assert the group chain, the
sub-command and every option exist, and that **no command the prompt never
asked for is exposed**. Measured on a fresh regeneration:

| project | prompt commands | generated | violations |
|---|---|---|---|
| `library_system` | 9 | 9 | 0 |
| `expenses` | 14 | 14 | 0 |
| `inventory` | 11 | 11 | 0 |

This is what removed the over-generated surface (library's `loan add`,
`loan cancel`, `member borrow`, `book update/delete`, `author *`; expenses'
`expense report --id`, `expense update/delete/get/detect`, `budget check`,
`category detect/check`) — including `member borrow --id N`, a dead command
that always raised `ValidationError: Book not specified for borrowing` (S14).
