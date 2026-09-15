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
| S18 | `bool`-returning methods carry no invariant enforcement | **recipe** | `counter_delta` / `flag_toggle` / `flag_set` / `status_set` effects are deterministic, AND so is the child-creating workflow: `compile_contract_impl` compiles a stated INSERT operation into a `create_child_row` impl (`agentlib/kernel/service/create_child_row.py`), which loads the anchor row, renders the guards from the DESIGN's own exception classes, applies the counter effects and inserts the child with every required column stamped from an exact source (a method parameter, the design's declared default, or "now" for an unqualified date). It is decided BEFORE the guard gate, so a guarded create is deterministic too. Earlier revisions of this row claimed `borrow_book` "stays LLM-filled" and that a child's required fields were "a domain decision neither source can supply" — measured on a fresh regeneration, that was a fill-luck dependency, not a necessity: one run shipped `borrow_book` as a dead `return False` stub, another happened to fill it correctly. The rendered body is now always `load Book → refuse when `(available_copies or 0) <= 0` → decrement → insert the Loan → True`, and the oracle's `borrow → return` round-trip (decrement, then restore) is a property of the renderer, not of the sample. |
| S19 | Dead / duplicated methods | **fixed (surface)** | The prune ("keep only the commands the specification lists") used to be impossible: the deterministic surface it pruned against was itself incomplete — it lacked spec-required commands (`overdue`, `history`), so pruning by it removed working behaviour, and commit `30521e5` reverted the attempt. The lever was wrong, not the idea: the surface is no longer DERIVED from the design's methods, it is READ from the prompt's own command list (`agentlib/pipeline/cli_spec.py`), so it is complete by construction. `agentlib/pipeline/cli_propagate.py` now takes `preserve_surface=True` and skips its merge/drop loop entirely, and no LLM CLI design runs at all. Shipped counts: library_system 24 → 9 commands (the prompt's 9), expenses 22 → 14 (the prompt's 14); `run_cli_conformity.py` asserts the equality. |

## Residual, explicitly non-generic

* **No S18 remainder.** The child-creating workflow was the last one listed
  here; it is now a recipe (see the row above), so the only thing a fill can
  still get wrong on a `bool` workflow is a method the contract renderer
  DECLINES — and every decline is a conservative "a required column has no
  parameter, default or `now` stamp", which leaves the previous behaviour
  untouched rather than shipping a half-stamped row.
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
python3 run_cli_behavior.py               # declared values, flags, workflows
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
## Whole-surface evaluation, second pass: error reporting and the entry point

Two defects of the GENERATED PROJECT (found by running every error path and
every command, not by reading the code), plus the tester-side fix they
required.

**(l) A command must REPORT a domain error, not dump a traceback.** —
`agentlib/generation/cli_render.py::_render_cli_file`, now given the project's
designed exception names by `manifest.py`. The specification's own error
contract IS a set of custom exception classes ("Implement proper error
handling with custom exception classes: CategoryNotFoundError,
ExpenseNotFoundError, BudgetExceededException"), and the generated classes
existed — but nothing caught them, so a user following the specification got a
raw Python traceback ending in `exceptions.CategoryNotFoundError: 999`:

```
$ python3 main.py expense add --amount 5.00 --description x --category 999
Traceback (most recent call last):
  ...
exceptions.CategoryNotFoundError: 999
```

Every command body now wraps its service call:

```python
    try:
        result = svc.add_expense(...)
    except (sqlite3.IntegrityError, CategoryNotFoundError, ExpenseNotFoundError,
            BudgetExceededException) as exc:
        click.echo("Error: %s" % exc, err=True)
        raise SystemExit(1)
```

The `sqlite3.IntegrityError` arm is unconditional, because a repository write
can raise a plain UNIQUE / FOREIGN KEY violation on a user-visible path
(a duplicate isbn, an unknown `--author-id`) and that is just as much a raw
crash. Measured on the freshly regenerated projects, all 19 error paths exit
with a one-line message and NO traceback:

```
Error: 999                                     (CategoryNotFoundError)
Error: UNIQUE constraint failed: categories.name
Error: UNIQUE constraint failed: books.isbn
Error: UNIQUE constraint failed: members.email
Error: FOREIGN KEY constraint failed
Error: Book with id 999 not found
Error: Member with id 999 not found
```

**(m) A CLI project always has a runnable entry point.** —
`agentlib/pipeline/manifest.py`. `main.py` was rendered only for a spec the
LLM layout happened to list, so `library_system` shipped with NO entry point
while `expenses` (the same shape: a click CLI) got one — `python main.py …`,
the way a user runs the deliverable, worked in one project and not the other
for no reason a user could see. The entry point is a property of the tree, not
a design decision: a tree with a `cli.py` and no `main.py`/`app.py` now gets
`_render_main_file` unconditionally. Verified: both projects ship a `main.py`.

**(n) The tester reads the call wherever the generated body puts it.** —
`behavior_tests/facade_discovery.py::_find_service_target` and
`_data_keys_from_body`. Both scanned only a function's TOP-LEVEL statements.
Adding the `try:` wrapper above nested the `result = svc.…` assignment one
level down, so the facade discovered an EMPTY target for every command of every
project: with no target it could not infer the command's FK references, stopped
synthesizing the parent seed, and reported three FALSE failures on correct code
(inventory `product add --category 1` -> the `CategoryNotFoundError` the
inventory specification explicitly demands: "add_product(...): validates the
category exists"). Both readers now walk the whole body, so the discovery is
independent of how the body wraps the call. Inventory returns to 12/12 and the
four-project façade is 5/5 + 12/12 + 14/14 + 9/9 with 0 unmapped.
## Third pass: the borrow workflow, and a parent NAME as a filter value

Two further defects of the GENERATOR surfaced by regenerating `library_system`
and running every path the specification enumerates, including the two the
executed oracle does not cover. Both are fixed in the generator; no generated
file was edited.

**(o) A stated INSERT workflow is rendered, never left to the fill.** —
`agentlib/pipeline/method_contract.py` (`spec_line_effects`,
`_create_child_impl`) and `agentlib/kernel/service/create_child_row.py`, wired
into `service_render._render_service_file` (which now passes `prompt_text` down
so a contract-less method can still be read). The specification states
`borrow_book(member_id, book_id): checks availability, creates loan, decrements
copies`, and the contract extractor's evidence closure rejected that line on all
three retries ("evidence was not verbatim"), so the method carried **no**
contract, fell to the LLM fill, and the fill is a coin toss: one measured run
shipped it as a dead `return False` stub (borrowing neither decremented the book
nor created the loan — the oracle caught it), another happened to fill it
correctly. Two changes close it:

1. `spec_line_effects` reads the method's OWN specification line and
   transcribes it into the extractor's own vocabulary, entity-closed: `creates
   loan` → `create_child` on the designed `Loan`; `decrements copies` → a
   `counter_delta` on the designed field ending in `copies`
   (`available_copies`); `checks availability` → `reject_unavailable` on that
   field. An unresolvable word yields nothing, so a spec-derived contract can
   never name an entity or a column the design lacks.
2. `compile_contract_impl` compiles the INSERT shape into a
   `create_child_row` impl **before** the guard gate (a guard no longer forces
   the fill), and the recipe renders it: load the anchor row by the parameter
   that names its id, run the guards (raising the DESIGN's own exception class,
   resolved by name — `BookNotAvailableError` — so nothing is invented), apply
   the counter deltas, then insert the child with every required column stamped
   from an exact source: a parameter of the method (`book_id`, `member_id`), the
   design's declared default (`status` = `'active'`, transcribed from the spec's
   own `status (active/returned/overdue)` line), or `now` for an unqualified
   date. A required column with none of those three sources DECLINES the
   render, leaving the previous behaviour rather than a half-stamped row.

Shipped body, verbatim:

```python
    def borrow_book(self, member_id: int, book_id: int) -> bool:
        row = self.book_repo.get_by_id(book_id)
        if row is None:
            raise InvalidBookIdError(book_id)
        if (row.available_copies or 0) <= 0:
            raise BookNotAvailableError(book_id)
        self.book_repo.update(book_id, {'available_copies': (row.available_copies or 0) - 1})
        loan = Loan(book_id=book_id, member_id=member_id, loan_date=datetime.datetime.now().isoformat(), due_date=datetime.datetime.now().isoformat(), status='active')
        self.loan_repo.create(loan)
        return True
```

Verified by execution, not by reading: borrowing decrements `available_copies`
2 → 1 and creates the `Loan` (oracle `borrow → return` round-trip), returning
restores it, and borrowing a book with **zero** copies exits 1 with a one-line
`Error:` and leaves both the counter and the loan table untouched — the
specification's own "checks availability". Borrowing a book whose id does not
exist exits 1 with `InvalidBookIdError`, again with no traceback.

**(p) A parent NAME is a filter value, not a parent ID.** —
`agentlib/generation/service_render.py` (`_parent_name_binding`,
`_render_parent_name_lookup`, in the `list_<entity>` branch of
`_generic_service_delegation`). The specification writes
`library book list [--author]` — an author NAME — while the design's repository
filters on `author_id`, and the design ALSO declared a second, optional
`author_id` parameter. The method therefore could not be resolved against the
declared filters (`author` is not a column), and the LLM fill answered
`--author 'F. Scott Fitzgerald'` with
`self.author_repo.get_by_id(None)` → `raise NotFoundError('Author with id None
not found')`: exit 1 on a path the specification marks as an ordinary optional
filter. The façade registered it honestly as 8/9. The generic delegation now
resolves the name deterministically when the design pins every piece of the
join: the parameter's `<name>_id` IS a declared `list()` filter of the entity,
the referenced entity IS designed, and that parent carries exactly one
candidate name column — the one the design calls `name`, else its single `str`
column (the specification's Author model is `id, name, birth_year, biography`:
TWO strs, so "exactly one str column" alone would still decline). The rendered
body scans the parent rows through the design's own `list()`, and an author name
that matches no row yields an empty listing rather than an error — the
specification describes `--author` as a FILTER, not as a lookup that can fail:

```python
        if author:
            _parent = None
            for _row in self.author_repo.list():
                if getattr(_row, 'name', None) == author:
                    _parent = _row
                    break
            if _parent is None:
                return []
            author_id = _parent.id
        return self.book_repo.list(available_only=available_only, author_id=author_id)
```

Measured: `library book list` lists every book, `--author <name>` filters by
that author, `--available-only` filters on `available_copies > 0`, and the
library façade is **9/9** (I2 passes).

## Final verification (this revision, four projects regenerated from scratch)

```
== marqueurs (reject / dropped / still stubbed / reverted / sanitized):
library_system 0   expenses 0   inventory 0   cli_tool 0

== oracle:
library_system: 15/15 invariant(s) hold
library_system: mutation pass (baseline 15/15)
expenses: 16/16 invariant(s) hold
expenses: mutation pass (baseline 16/16)
ALL SEMANTIC CHECKS PASS

== conformité prompt→surface (les DEUX directions):
[expenses]       status=pass prompt_commands=14 violations=0
[inventory]      status=pass prompt_commands=11 violations=0
[library_system] status=pass prompt_commands=9  violations=0

== façade (invocations réelles sur base fraîche):
[cli_tool]       status=pass mapped=5  unmapped=0 pass=5  fail=0
[inventory]      status=pass mapped=12 unmapped=0 pass=12 fail=0
[expenses]       status=pass mapped=14 unmapped=0 pass=14 fail=0
[library_system] status=pass mapped=9  unmapped=0 pass=9  fail=0
```

`run_cli_conformity.py` is load-bearing, not decorative: it is what caught the
last regression (2 violations on `inventory`, caused by a missing command the
generator itself had dropped), and its output is the measured equality between
each prompt's own command list and the shipped CLI — every prompt command
present with the prompt's own group path and option names, and **nothing the
prompt did not ask for**.
## Fourth pass: the specification's own value vocabulary, flag names and defaults

Three further generator defects surfaced by exercising the freshly regenerated
projects against the prompt text itself rather than against the design.

**(q) A value vocabulary the specification declares is part of the CLI
contract.** — `agentlib/pipeline/value_vocab.py` (new), wired into
`agentlib/generation/cli_render.py` and `agentlib/pipeline/manifest.py`.
`expenses`'s spec line reads `payment_method (cash/card/transfer)` — a
DECLARED set of allowed values. The generated CLI accepted any string, so a
caller could store `payment_method='bitcoin'` and every later report grouped on
a value the specification never defined. The vocabulary is read from the prompt
alone and only for a FIELD a designed entity actually carries, so a
parenthesised slash-list in prose cannot constrain an unrelated option; a name
whose occurrences DISAGREE (`status` written differently in two places) is
REFUSED rather than guessed. The renderer then emits
`type=click.Choice(['cash', 'card', 'transfer'])`, so the CLI refuses an
out-of-vocabulary value with exit 2 and a one-line message.

The TESTER had to learn the same contract: `facade_discovery._choice_values`
records the declared values, `facade_mapping._facade_context` lists them
(`OPTION --method (str, one of: cash|card|transfer)`) and `_build_plan` binds an
option to a declared value whenever the LLM proposed one outside the set.
Measured: with the discovery but without the mapper floor, the façade's two
payment-method intentions FAILED with
`Invalid value for '--method': 'credit_card' is not one of 'cash', 'card',
'transfer'` — the CLI was RIGHT and the test input was wrong. Both intentions
now pass and the façade is 14/14. Measured on the generated CLI:
`--method bitcoin` exits 2, `--method card` exits 0.

**(r) A flag the specification names is emitted alone, never with a
synthesized twin.** — `agentlib/generation/cli_render.py`, driven by the option
NAMES the prompt wrote (`manifest.py` passes `spec_option_names`). The spec
writes `expense add … [--recurring]`; the renderer used to emit the boolean as
the click dual form `--recurring/--no-recurring`, which is a command-line NAME
the specification never asked for (a user following the prompt cannot know it,
and a name the prompt never wrote has no place in the shipped surface). The
option is now rendered as the single flag the spec named; a non-spec-named
boolean keeps its dual form. Measured: `--recurring` is accepted and stores
`is_recurring = 1`; `--no-recurring` exits 2 (`No such option`).

**(s) A default the specification declares reaches the DDL, not only the
dataclass.** — `agentlib/generation/model_render.py`, using the defaults
transcribed by `agentlib/pipeline/model_defaults.py`. The declared defaults were
applied to the domain model (`is_recurring: bool = False`) but the CREATE TABLE
rendered a bare `is_recurring BOOLEAN NOT NULL`, so any INSERT path that is not
the generated service (a direct SQL seed, a future migration, a user's own
script) met `NOT NULL constraint failed`. The column now carries the same
default the specification declares. Measured in the regenerated DDL:

```sql
payment_method TEXT NOT NULL DEFAULT 'cash',
is_recurring   BOOLEAN NOT NULL DEFAULT 0,
available_copies INTEGER NOT NULL DEFAULT 1,
is_active      BOOLEAN NOT NULL DEFAULT 1,
status         TEXT NOT NULL DEFAULT 'active',
```

These three are properties of the RENDERER reading the specification, and each
is verified by executing the shipped CLI (`expense add` without
`--expense-date`, `--recurring` / `--no-recurring`, `--method` in and out of
vocabulary) rather than by reading generated code.
## Fifth pass: repository body fidelity, and an approach the oracle REFUTED

This pass targets the *body* of a repository custom method — the fill the LLM
writes inside a locked signature. Three of the defects below were shipped code
that no crash filter could see, because the method was never called on the
paths the other gates exercise. Each is now a rule read off the body's own
syntax, plus a preventive line in the fill's system prompt. One approach was
tried, measured, and rejected; it is recorded here because the rejection is
the most useful evidence in this section.

**(a) A declared parameter the body never reads.** `list_authors_with_books(
include_inactive)` shipped a body that built a query, patched it with the
flag, then assigned a FRESH query over it — the flag ended up with no effect
whatsoever. The order-aware reading lives in
`agentlib/generation/repo_render.py::_dead_store_names` / `_repo_fidelity_violations`
and fires on a local that is REASSIGNED before its earlier value was ever
read. `x += ...` reads `x` and is never flagged, so the legitimate incremental
build (`query = query + " AND ..."`) passes untouched. Verified by a six-case
unit check (three defective bodies rejected, three legitimate shapes accepted).

**(b) A date value the body re-formats.** `ExpenseRepository.export_to_csv(
file_path, start_date: date, end_date: date)` called `start_date.isoformat()`.
Values reach a repository as ISO strings — the same convention the service
fill already states — so the call is an `AttributeError` waiting for a caller.
The rule rejects `.isoformat()`/`.strftime()`/`.date()` called on a *parameter*
(never on a locally built `datetime.datetime.now()`, whose receiver is a call
and not a name).

**(c) A datetime annotation naming the MODULE.** `models.py` imported
`import datetime` and then annotated `due_date: datetime` —
`agentlib/generation/model_render.py::_annotation` now emits
`datetime.datetime` for a `datetime` column (`date` stays bare, because the
module also imports `from datetime import date`). `from __future__ import
annotations` made the defect inert, which is exactly why only a reading of the
annotation could find it.

Each rule is stated to the model BEFORE it writes, in
`_REPO_FILL_SYSTEM_RULES`, so the validator is the backstop rather than the
normal path. Measured on a fresh `expenses` regeneration:
`export_to_csv` now ships `conn.execute(query, (start_date, end_date))` and a
`csv.DictWriter`, with no `.isoformat()` anywhere.

### An approach the oracle refuted: pruning "uncalled" repository customs

The first attempt at "no dead method" was to drop every designed repository
custom whose name appears in no `<x>_repo.<name>(` call site of the shipped
service, re-rendering the repository from the pruned design
(`_prune_dead_repo_customs`). It removed `get_overdue_loans_count`,
`list_authors_with_books` and `export_to_csv` — all genuinely uncalled — and
the semantic oracle immediately FAILED:

```
FAIL [spec] repository budget status compares the limit to spending
     -> AssertionError: no budget-status method found: the specification
        requires BudgetRepository to 'check if a category has exceeded its budget'
expenses: 14/16 invariant(s) hold
```

`check_budget_exceeded` is a repository DUTY the specification states in
prose and no CLI command reaches; the whole purpose of
`repo_spec_constraint` is to keep the design covering it. A method can
therefore be uncalled and still REQUIRED. Any reachability prune needs the
spec's prose as its oracle, which is a semantic judgement, not a
deterministic one — so the prune was abandoned and the helpers removed.
Reachability is not deadness.

The two defects this leaves are real and BOTH concern the same shape: a body
whose SQL does not match its own name.

* `LoanRepository.get_overdue_loans_count()` still runs `SELECT COUNT(*) FROM
  loans` — every loan, not the overdue ones. The prompt enumerates
  `get_overdue_loans()` (which is shipped, faithful, and drives `library
  overdue`) but never `get_overdue_loans_count`, so this is an
  over-generation. It is never called, so it cannot crash the delivered CLI —
  but it is wrong code in the tree, and no deterministic rule catches it.
  Rejecting it by name token ("overdue" must appear in the SQL) would reject
  the CORRECT `get_overdue_loans`, whose faithful SQL compares `due_date`.
  Deciding whether `SELECT COUNT(*) FROM loans` "means" counting overdue loans
  requires reading the name as language. This is the boundary of what this
  generator validates without a domain word list, and it is stated as a
  known limit rather than papered over.

### A logging convention the fill shared with the service path

`agentlib/llm/fill.py` printed `output rejected (attempt N)` on EVERY failed
attempt of its two-attempt compile retry. A transient failure that the retry
then repaired left a marker in the log that reads as a shipped defect. The
service fill path already states the opposite convention, in its own comment:
log a rejection only when the method ultimately failed, "positive-first".
`fill.py` now does the same — a rejection is printed once, after both attempts
have failed — so the marker means exactly what it says.

### The gate that keeps the display convention honest

`run_cli_behavior.py` gained seven assertions on the report path: the monthly
and yearly reports must print `Decimal` totals while `SUM(amount_cents)` in
SQLite still returns integer cents. Both halves are checked (console path and
stored column), so a regression on either side of the "store cents, display
decimals" convention fails the gate. It runs with no LLM, on a fresh database,
and is the cheapest regression net for the renderer.
### Frozen-state verification (fifth pass, both projects regenerated from scratch)

Generator frozen, `generated/library_system` and `generated/expenses` regenerated
from scratch, then every gate re-run. No log marker in either generation:

```
== marqueurs (reject / dropped / still stubbed / reverted / sanitized):
library_system 0   expenses 0

== compile:
python3 -m compileall -q agentlib behavior_tests   -> OK

== conformite prompt -> surface (les DEUX directions):
[expenses]       status=pass prompt_commands=14 violations=0
[inventory]      status=pass prompt_commands=11 violations=0
[library_system] status=pass prompt_commands=9  violations=0
[cli-conformity] failures=0/3

== comportement (CLI reelle, base fraiche, sans LLM):
EXPENSES:         PASS (43 ok, 0 fail)
LIBRARY_SYSTEM:   PASS (39 ok, 0 fail)
SOURCE-FIDELITY:  PASS (83 ok, 0 fail)

== oracle semantique:
library_system: 15/15 invariant(s) hold  + mutation pass
expenses:       16/16 invariant(s) hold  + mutation pass
ALL SEMANTIC CHECKS PASS

== facade (invocations reelles):
[cli_tool]       pass 5   [inventory] pass 12
[expenses]       pass 14  [library_system] pass 9

== preuve brute des quatre defauts (24 commandes, arbre fige):
mismatches = 0 / 24
```

The 24 raw rows are the four defects of the task, observed rather than
asserted. Every path the specification enumerates exits 0 — including
`expense add --amount 12.50 --description lunch --category 1` with **no**
`--expense-date` (defect 1), `expense category add` (defect 3, the missing
`expense` group), `expense report monthly --month` (the `report` sub-group),
`expense recurring detect`, `budget add --amount`, `expense add --method
card --recurring`, `library book add --copies`, `library overdue`,
`library member history`, `library borrow`. Every path the specification never
asked for exits 2 with click's "No such command" / "No such option" —
`--amount-cents`, `--available-copies`, `--term`, `--amount-limit-cents`,
a bare `category add` without its `expense` group, `expense monthly` for
`expense report monthly`, a bare `expense recurring`, `expense update`,
`expense get`, `expense report --id`, `budget check`, `library loan add`,
`library loan cancel`, and the dead `library member borrow --id` (S14).

### `source-fidelity`: a gate that found a defect in a DETERMINISTIC body

`run_cli_behavior.py` grew a third suite that re-runs the generator's own
`_repo_fidelity_violations` over the SHIPPED repository sources (83 assertions
on the two projects). It exists because the fill-time rule only ever sees LLM
FILLS — a deterministically rendered body never passes through the validator,
and the suite immediately found one:

* `BudgetRepository.check_budget_exceeded` opens `limit = None`, refines
  `limit` inside the `for` loop, and reads it AFTER the loop. The first
  version of the dead-store rule walked nested blocks with a SHARED liveness
  set, so it read that refinement as "assigned then overwritten" — a false
  positive on the sentinel idiom, invisible at generation time because the
  method is a recipe, not a fill.

The rule now decides WITHIN one statement list and recurses into each nested
list as its own scope: a value assigned before a branch is legitimately
replaced inside it, while a read INSIDE a branch does not consume the outer
value on every path — which is exactly why `query` patched conditionally
(`if flag: query += ...`) and then overwritten unconditionally is still a dead
store. Seven unit cases pin both directions: three defective shapes rejected
(the overwritten query, `.isoformat()` on a parameter, a parameter never read)
and four legitimate ones accepted (incremental `query = query + ...`, `query +=
...`, `.isoformat()` on a locally built datetime, the sentinel-in-loop above).

Loi D, re-measured on the frozen tree:

| instance | before | frozen |
|---|---|---|
| `AuthorRepository.list_authors_with_books` | query built then OVERWRITTEN; `include_inactive` had no effect | builds one query incrementally (`base_where +=`), the flag changes the WHERE clause |
| `ExpenseRepository.export_to_csv` | `start_date.isoformat()` on a `date` parameter that carries a str | `conn.execute(query, (start_date, end_date))`, no re-formatting |
| `Loan.due_date` annotation | `datetime` (the MODULE, inert only because of `from __future__ import annotations`) | `datetime.datetime` |
| `LoanRepository.get_overdue_loans_count` | `SELECT COUNT(*) FROM loans` — every loan | **resolved in the sixth pass**: the method no longer exists. A count the repository's own specification bullet never names is not a capability anyone asked for — see the sixth pass, rules R2/R3c. |

The last row was the honest boundary of the fifth pass: the two live defects
(the flag with no effect, the crash-on-call) were closed and gated, and the one
that remained was a dead over-generation with no reachable consequence. The
sixth pass closes it too, by removing the method rather than by guessing at its
body: the repository's own specification bullet is the ownership test, and
"CRUD + find active loans, overdue loans, member loan history, book loan
history" owns no count.
## Sixth pass: the duplicate capability, removed at the design

The fifth pass closed the *bodies*. This pass closes the *definitions*: a
repository that ships two methods for the same capability is a second source of
truth for one table, free to diverge, and the user's own audit named it as the
remaining defect (`list` beside `list_expenses`, `list` beside `list_budgets`,
`create` beside `add_member`). Measured on the tree before this pass:

| repository | non-CRUD methods shipped | of which nobody asked for |
|---|---|---|
| `expense_repository` | 8 | `list_expenses`, `get_expense_by_id`, `export_to_csv`, `detect_recurring` |
| `category_repository` | 6 | `list_categories`, `get_category_by_id`, `add_category`, `update_category`, `delete_category` |
| `budget_repository` | 5 | `list_budgets`, `add_budget`, `update_budget`, `delete_budget` |
| `book_repository` | 2 | `list_books` |
| `author_repository` | 3 | `get_author_books_count`, `list_authors_with_books` |
| `member_repository` | 3 | `add_member`, `list_members` |
| `loan_repository` | 5 | `get_overdue_loans_count` |

Four points about why this is a defect and not cosmetics:

* the RENDERED SERVICE never calls any of them — it uses the deterministic CRUD
  method (`self.category_repo.list()`, `self.expense_repo.get_by_id(id)`), so
  every one is unreachable;
* they DIVERGE. `category_repository.update_category` wrote all four columns
  unconditionally (`SET name = ?, description = ?, monthly_budget = ?, icon = ?`)
  where the CRUD `update(id, data)` is PARTIAL, so a caller of the duplicate
  nulled every field it omitted;
* one of them was BROKEN and no gate could see it, because nothing calls it:
  `author_repository.list_authors_with_books` built `SELECT a.id, …` with **no
  `FROM authors a`** and filtered on an `a.is_active` column its own table does
  not have — `OperationalError: no such column: a.id` on any call;
* another was semantically WRONG: `loan_repository.get_overdue_loans_count`
  answered `SELECT COUNT(*) FROM loans` — 2 — where the canonical
  `get_overdue_loans` filtered `due_date < date('now') AND return_date IS NULL`
  and found 0.

### The rules

Five pruners, each keyed on an exact spelling test, never on a domain word list.
They run at design time except R3g, which runs after the service is rendered.

| rule | where | drops | kept by construction |
|---|---|---|---|
| **R1** CRUD shadow | `repo_render._prune_crud_shadow_customs` | a custom that merely re-spells a deterministic CRUD method on its own entity: `add_<e>` → create, `list_<e>(s)`/`all` → list, `get_<e>_by_id` → get_by_id, `update_<e>` → update, `delete_<e>` → delete | any name keeping a NON-entity token (`search_books`, `get_overdue_loans`, `find_books_by_author`, `get_expenses_for_category`) |
| **R2** qualifier extension | same | `name` = sibling + trailing qualifier tokens (`get_overdue_loans_count` beside `get_overdue_loans`) | an unrelated longer name (`get_expenses_for_category` beside `get_expenses`) |
| **R3c** unjustified qualifier | `repo_render._unjustified_qualifier_customs` | a count/total/sum custom whose qualifier the repository's own specification bullet never names (`get_author_books_count`; the bullet is "CRUD + find books by author") | inert when the prompt names no repository for that entity, or when the bullet contains the qualifier |
| **R3e** rejected and subsumed | `repo_render._render_repository_file` | a custom the schema gate REJECTED whose content words are already named by a sibling that shipped (`list_authors_with_books` → {'books'} ⊆ `find_books_by_author` → {'books'}) | any rejected body whose words no sibling carries — the safe stub is kept rather than guessing |
| **R3g** uncalled and unnamed | `manifest._prune_uncalled_repo_customs` | a custom the SHIPPED SERVICE never calls **and** whose content words the repository's own bullet never names (`export_to_csv`, `detect_recurring`) | every spec-mandated duty however unreachable: `get_monthly_report` / `get_yearly_summary` ("monthly/yearly aggregation queries"), `get_expenses_for_category` ("find expenses for a category"), `check_budget_exceeded` ("check if a category has exceeded its budget"), `get_active_loans` ("find active loans"), `get_member_loan_history` ("member loan history") |

Two properties make the set safe rather than merely aggressive:

**The pruning is a fixpoint on the DESIGN, not on the file.** R1/R2/R3c prune
`design["methods"]` in place, and `_service_repo_interface` builds the fill's
legal interface from the SAME object, so a method pruned here can never be
advertised to a service fill — the service cannot call what no longer exists.
R3g prunes after the service source is in hand and removes the methods from the
shipped file with `_drop_functions` (an AST range deletion) rather than
re-rendering, so the accepted sibling fills and any bounded repair the service
fill made are preserved byte for byte.

**A duplicate is judged against the SPECIFICATION, not against a notion of
"used".** The tempting rule — "drop every repository method the service never
calls" — is WRONG, and measurably so: two methods of the shipped library tree
are uncalled yet mandated. `get_expenses_for_category` is the prompt's own
"CategoryRepository — CRUD + find expenses for a category" and
`get_monthly_report`/`get_yearly_summary` are its "monthly/yearly aggregation
queries". A repository duty the service realizes inline is still a duty the
prompt states. R3g therefore requires the bullet to be silent too, and skips
`export_to_csv`/`detect_recurring` (which the prompt assigns to
`ExpenseService`, not to the repository) while keeping the aggregation pair.

An earlier candidate rule, "drop a repository custom whose NAME equals a
designed service method name", was tried and REJECTED on measurement: on the
regenerated library tree `MemberRepository.get_member_history` IS called by the
service (`return self.member_repo.get_member_history(member_id)`, the body
behind `library member history --member-id`), so the name-equality test would
have deleted a live, spec-implied path. A shared name is evidence of nothing;
the call site is evidence, and only R3g reads one.

### Measured after the pass

```
-- library_system.author_repository: 8 methods   (create/get_by_id/get_all/
   list/update/delete + find_books_by_author)
-- library_system.book_repository: 7 methods     (+ search_books)
-- library_system.loan_repository: 10 methods    (+ get_overdue_loans /
   get_active_loans / get_member_loan_history / get_book_loan_history)
-- library_system.member_repository: 7 methods    (+ get_member_history)
-- expenses.budget_repository: 8 methods          (+ get_by_category_and_month,
   check_budget_exceeded)
-- expenses.category_repository: 7 methods        (+ get_expenses_for_category)
-- expenses.expense_repository: 9 methods         (+ get_monthly_report,
   get_yearly_summary, get_category_spending)

NO DUPLICATE AND NO UNASKED REPOSITORY METHOD
```

That last line is `verify_nodupes` (a throwaway harness, not a shipped gate): it
walks every generated repository and asserts, per method, that it is not an R1
shadow, not an R2 extension, and that every content word of a non-CRUD name
appears somewhere in the prompt that asked for the project. 0 failures on all
seven repositories, where the pre-pass tree had 18 offenders.

The predicate tables are pinned by 42 unit cases (`R1` 36 + `R2` 6) covering
both directions — the shapes that must be dropped and the spec-named shapes
that must survive (`search_books`, `find_books_by_author`, `get_overdue_loans`,
`get_active_loans`, `get_member_loan_history`, `get_book_loan_history`,
`get_expenses_for_category`, `check_budget_exceeded`,
`get_by_category_and_month`) — plus 12 cases for the capability reader, the
qualifier prune, the subsumption test and the AST range deletion.

The fifth pass's `SOURCE-FIDELITY` suite drops from 83 checks to 65 on the same
tree purely because its input shrank: it asserts one property per shipped
repository method, and 18 duplicate methods no longer exist. The gate is not
weaker; there is less duplicate surface to assert against.

### Gates re-run on the fresh regeneration

```
python3 run_cli_conformity.py
[expenses]       status=pass prompt_commands=14 violations=0
[inventory]      status=pass prompt_commands=11 violations=0
[library_system] status=pass prompt_commands=9  violations=0

python3 run_cli_behavior.py
EXPENSES: PASS (43 ok, 0 fail)   LIBRARY_SYSTEM: PASS (39 ok, 0 fail)
SOURCE-FIDELITY: PASS (65 ok, 0 fail)   FIDELITY-RULES: PASS (7 ok, 0 fail)

python3 run_semantic_oracle.py
library_system: 15/15 invariant(s) hold / mutation pass (baseline 15/15)
expenses: 16/16 invariant(s) hold / mutation pass (baseline 16/16)

python3 run_facade_execution.py --prompt library_system --prompt expenses \
    --prompt inventory --prompt cli_tool
[cli_tool] 5/5   [inventory] 12/12   [expenses] 14/14   [library_system] 9/9

markers (reject|dropped|still stubbed|reverted|sanitized|dropped infeasible)
on both generation logs: 0 — the `reverted list_authors_with_books` line the
fifth pass produced is gone WITH the method, not silenced.
```

Every one of the 23 commands the two prompts enumerate was additionally executed
against a fresh database, once with the required options only and once with
every option (`verify_surface`, a throwaway harness): 0 non-zero exits, including
the optional-option path that was defect 1 of the brief —
`expense add --amount 12.34 --description lunch --category 1`, with no
`--expense-date`, exits 0 and stores today's ISO date.
### The duplicate-capability gate

`run_repo_conformity.py` + `behavior_tests/repo_conformity.py` are the shipped
regression test for this pass — the layer-below counterpart of
`run_cli_conformity.py`, deterministic and LLM-free. For each generated
repository they assert, per method, that it does not re-spell the deterministic
CRUD surface, that it does not merely extend a sibling with a scalar qualifier,
and that every content word of its name appears in the prompt that asked for the
project at all.

It is not decorative: run against the tree BEFORE `inventory` was regenerated it
reported exactly the duplicates that stale artifact still carried
(`category_repository.add_category` / `list_category` / `update_category` /
`delete_category`, `product_repository.list_products`), and against the
regenerated tree it reports 0. Measured on all three enumerating prompts:

```
python3 run_repo_conformity.py
[expenses]       status=pass repositories=3 violations=0
[inventory]      status=pass repositories=2 violations=0
[library_system] status=pass repositories=4 violations=0
[repo-conformity] failures=0/3
```

## Seventh pass: the pruners re-measured on a fresh four-project tree

`inventory` and `cli_tool` were regenerated with the sixth-pass generator so the
non-regression claim rests on fresh artifacts rather than on files from two days
earlier (the stale `generated/inventory` was exactly what the new gate flagged).

```
== markers (reject / dropped (unknown target) / dropped (no designed service
   method) / still stubbed / reverted / sanitized / dropped infeasible):
library_system 0   expenses 0   inventory 0   cli_tool 0

== CLI surface conformity (both directions):
[expenses]       status=pass prompt_commands=14 violations=0
[inventory]      status=pass prompt_commands=11 violations=0
[library_system] status=pass prompt_commands=9  violations=0

== repository capability conformity:
[expenses]       status=pass repositories=3 violations=0
[inventory]      status=pass repositories=2 violations=0
[library_system] status=pass repositories=4 violations=0

== body fidelity + declared values:
EXPENSES: PASS (43 ok, 0 fail)         LIBRARY_SYSTEM: PASS (39 ok, 0 fail)
SOURCE-FIDELITY: PASS (65 ok, 0 fail)  FIDELITY-RULES: PASS (7 ok, 0 fail)

== oracle:
library_system: 15/15 invariant(s) hold / mutation pass (baseline 15/15)
expenses: 16/16 invariant(s) hold / mutation pass (baseline 16/16)

== facade, four freshly regenerated projects:
[cli_tool] 5/5   [inventory] 12/12   [expenses] 14/14   [library_system] 9/9
```

The four-project regeneration is what proves the pruners are not specific to the
two target prompts: `inventory`'s `category_repository` shipped the same
`add_/list_/update_/delete_category` duplicate family and `product_repository`
shipped `list_products`, and all five are gone on the fresh tree with the
project's façade holding at 12/12.
### The surface-smoke gate

`run_surface_smoke.py` is the executable form of the third objective — *no
command the prompt authorizes may crash*. For every command each enumerating
prompt lists it invokes the shipped CLI three ways (`--help`, with NO option,
and with every option given a placeholder value) inside a SCRATCH COPY of the
project, and asserts that stderr never carries a Python traceback and that the
exit code is 0 (worked), 1 (a reported domain error) or 2 (click refused the
arguments). A stack dump is precisely the defect disposition (l) fixed, where
`CategoryNotFoundError` and `sqlite3.IntegrityError` used to reach the user as
a traceback.

```
python3 run_surface_smoke.py
[expenses]       status=pass commands=14 runs=42 violations=0
[inventory]      status=pass commands=11 runs=33 violations=0
[library_system] status=pass commands=9  runs=27 violations=0
[surface-smoke] failures=0/3
```

102 invocations across the three prompts, 0 tracebacks. The scratch copy keeps
the gate side-effect free: it mutates only its own temporary tree, never
`generated/`, so it can run between the other suites without disturbing the
fixtures they seed.
## Eighth pass: the FINAL measurement, on a fresh regeneration of both targets

The generator was touched after the seventh pass (R1 gained the
`get_all_<e>`/`find_all_<e>` spelling, found by the new unit test), so
`expenses` and `library_system` were regenerated once more from scratch with
the final revision, and every gate re-run against those artifacts.

```
== unit: the pruner predicates, both directions
REPO PRUNERS: PASS (71 case(s))

== markers (reject / dropped (unknown target) / dropped (no designed service
   method) / still stubbed / reverted / sanitized / dropped infeasible):
expenses 0   library_system 0   (and inventory 0, cli_tool 0)

== CLI surface conformity (both directions):
[expenses]       status=pass prompt_commands=14 violations=0
[inventory]      status=pass prompt_commands=11 violations=0
[library_system] status=pass prompt_commands=9  violations=0

== repository capability conformity:
[expenses]       status=pass repositories=3 violations=0
[inventory]      status=pass repositories=2 violations=0
[library_system] status=pass repositories=4 violations=0

== surface smoke (no command may crash):
[expenses]       status=pass commands=14 runs=42 violations=0
[inventory]      status=pass commands=11 runs=33 violations=0
[library_system] status=pass commands=9  runs=27 violations=0

== body fidelity + declared values:
EXPENSES: PASS (43 ok, 0 fail)         LIBRARY_SYSTEM: PASS (39 ok, 0 fail)
SOURCE-FIDELITY: PASS (65 ok, 0 fail)  FIDELITY-RULES: PASS (7 ok, 0 fail)

== oracle:
library_system: 15/15 invariant(s) hold / mutation pass (baseline 15/15)
expenses: 16/16 invariant(s) hold / mutation pass (baseline 16/16)
ALL SEMANTIC CHECKS PASS

== every prompt command executed, required-only AND with every option:
ALL SURFACE COMMANDS OK (required-only and all options)

== facade, four projects (two regenerated in this pass):
[cli_tool] 5/5   [inventory] 12/12   [expenses] 14/14   [library_system] 9/9
```

The two objectives of the brief, restated against that measurement:

* **zero crash on every path the prompt authorizes** — the surface smoke
  exercises every enumerated command three ways (102 invocations) with 0
  tracebacks, and the execution sweep drives all 23 prompt commands with the
  required options only and with every option, exit 0 throughout, including
  the optional-option path that was the brief's first defect
  (`expense add --amount 12.34 --description lunch --category 1`, no
  `--expense-date`, stores today's ISO date);
* **the prompt's own CLI surface and nothing else** — 0 conformity violations
  in both directions on the three enumerating prompts, and 0 duplicate or
  unasked repository methods on all seven repositories.
## Tenth pass: what remained BELOW the CLI, measured then closed

The ninth pass closed the CLI surface. Re-measuring the whole tree afterwards
(same gates, plus two throwaway probes over the shipped sources) answered the
question "what is still non-conformant?" with three findings, all *below* the
command line where no earlier gate looked.

### Finding 1 — `AuthorRepository.list_authors_with_books`: an unrequested method

`find_books_by_author` and `list_authors_with_books` both read as the
capability `{'books'}` (verb + entity stem + stopwords removed), and the
prompt's bullet — "SQLite storage with CRUD + find books by author" — names
the object word `books`, so the existing intersection test in
`_prune_uncalled_repo_customs` kept BOTH, although the service calls neither.

The intersection test was too weak: the bullet names the *object* of the duty,
and an over-generated second spelling also names that object. The rule is
sharpened (R3h): among unreached customs that name the SAME capability, the
one the bullet itself SPELLS survives — its own name tokens appearing
contiguously in the bullet's token sequence (`find books by author` spells
`find_books_by_author`; it does not spell `list_authors_with_books`). A
capability the bullet names exactly once is left alone, so
`get_expenses_for_category`, `check_budget_exceeded`, `get_monthly_report` and
`get_yearly_summary` are untouched — each names a capability no sibling shares.

`behavior_tests/repo_conformity.py` gained the matching check — two shipped
methods with identical non-empty capability tokens are a violation — and it
FAILED on the tree before regeneration
(`author_repository.py ships find_books_by_author and list_authors_with_books
— one capability (books), two implementations`), which is what makes it
load-bearing rather than decorative. `run_repo_pruner_unit.py` grew from 71 to
81 cases, pinning the new predicate in both directions against the REAL prompt
bullets.

### Finding 2 — `database.py` shipped three unused connection helpers

`get_db_connection`, `get_connection` and `init_database` were emitted on every
project and called by NOTHING — no generated repository, service, `main.py`,
harness or specification (verified by a reference count over the whole tree,
and by grepping every prompt and bench file). Three spellings of one
connection: over-generation of exactly the kind the brief forbids for
commands, one layer lower. The template now emits the surface a project
actually uses — `Database` and `create_tables` — and the specification's own
database filename reaches the file as its module docstring, so the parameter
stays meaningful instead of dangling.

Adjacent and latent: the generated `Database.__init__` defaulted to
`:memory:`, while `connect()` opens a FRESH connection per call — so the tables
created in `__init__` were discarded and the default constructor could never
work. The CLI always passed a real path (`Database(DB_PATH)`), so no
prompt-authorized path ever hit it; the default now names the specification's
own file, which is both reachable and coherent with the spec.

### Finding 3 — the service layer re-implements what the repository was asked to provide (kept, documented)

The prompt asks `BudgetRepository` to "check if a category has exceeded its
budget" and `ExpenseRepository` for "monthly/yearly aggregation queries", and
both exist — but `ExpenseService.add_expense` performs the budget comparison
inline and `get_monthly_report` / `get_yearly_summary` recompute their
aggregates from `list()` rather than calling the repository method. Likewise
`LoanRepository.get_member_loan_history` is unreached because
`MemberRepository.get_member_history` serves `library member history`.

This is NOT a conformity violation and is deliberately NOT pruned: every
capability the specification names EXISTS and every prompt-authorized path
works, and dropping `get_member_loan_history` would remove a method the
LoanRepository bullet explicitly asks for. It is recorded as a fidelity limit —
the prompt asks for the capability, not for delegation — and the earlier
remedy would be worse than the disease.

### Measurement on a fresh regeneration of all four projects

All four were regenerated with the final generator (markers clean on every log,
exit 1 for the official forbidden pattern):

| gate | result |
|---|---|
| `compileall` (agentlib, behavior_tests, gates) | OK |
| `run_repo_pruner_unit.py` | PASS (81 cases) |
| `run_cli_conformity.py` | 0 violations — expenses 14, inventory 11, library_system 9 |
| `run_repo_conformity.py` | 0 violations — 3 + 2 + 4 repositories |
| `run_surface_smoke.py` | 102 invocations, 0 tracebacks |
| `run_cli_behavior.py` | PASS (43 / 39 / 64 / 7) |
| `list_authors_with_books` in the tree | 0 occurrences |
| `init_database` + `get_connection` + `get_db_connection` | 0 occurrences in any `database.py` |

`SOURCE-FIDELITY` moves 65 → 64 because one of its checks asserted a property
of the method that no longer exists; the check left WITH the method rather
than being silenced.
