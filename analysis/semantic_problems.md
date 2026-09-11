# Semantic problems in the generated code (expenses, library_system)

**Scope.** This document covers the **behavioural (semantic) defects** in the two
explicit-CLI generated projects — bugs where the code compiles, wires up and
runs, but does **not** implement what the prompt asks. The separate class of
*deterministic renderer* bugs (unbound `date` annotation, flat click CLI, leaked
SQLite connections) is out of scope here and is being fixed in the renderers.

**Why these survive.** A filled method body is checked by exactly two
validators, both of which are *crash filters*, not behaviour checks:

- `agentlib/generation/service_render.py::_undefined_name_violations` (≈1970) —
  every name must be bound (no `NameError`).
- `agentlib/generation/service_render.py::_semantic_fill_violations` (≈1647) —
  its docstring states it checks *"using DESIGNED types only"*: constructor
  field names, attribute access on repo-returned entities, no attribute access
  on a `Dict` return, no `date`/`datetime` arithmetic, designed param types.

A body that ignores a parameter, skips a counter update, or forgets to toggle a
flag is **name-correct and type-correct**, so it passes both. The only
deterministic device that stamps real logic is
`_apply_impl_floors` (≈1174), whose docstring limits it to two shapes —
*period total* and *filtered/grouped total* — and which `continue`s on any method
matching `^(add|create|update|delete|remove|set|get|search|find)_` and on any
method whose return type is not `Dict`/`dict`/`int`/`float`.

The consequence, per buggy method:

| method | why no floor applies | body source |
|---|---|---|
| `get_monthly_report` | `get_` prefix → skipped | LLM |
| `get_yearly_summary` | `get_` prefix → skipped | LLM |
| `return_book` | returns `bool` → skipped | LLM |
| `renew_membership` | returns `bool` → skipped | LLM |
| `borrow_book` | returns `bool` → skipped | LLM |

Every method that carries a business invariant is either `get_`-prefixed or
returns `bool`; none is stamped, so all are delegated to Qwen3-4B and only
crash-checked. A 4B model reliably produces plausible, type-correct,
semantically-shallow bodies of exactly these shapes.

---

## EXPENSES

### S1. `ExpenseService.get_monthly_report(month)` ignores `month`
**Prompt:** *"returns total spent, per-category breakdown, budget status
(on_track/warning/exceeded) for a given "YYYY-MM" month"*.
**Actual** (`expense_service.py`):
```python
def get_monthly_report(self, month: str) -> Dict[str, Any]:
    results = {}
    for row in self.expense_repo.list():          # <-- no month filter at all
        key = row.category_id
        results[key] = results.get(key, 0) + row.amount_cents
    return results
```
**Evidence (reproduced):** with a Jan(1000) and a **Mar**(2000) expense,
`get_monthly_report('2024-01')` → `{1: 3000}`. January should be 1000.
**Also wrong:** returns `{category_id: sum}`, i.e. no `total` key, no budget
status, no on_track/warning/exceeded classification.

### S2. `ExpenseService.get_yearly_summary(year)` returns the wrong shape
**Prompt:** *"returns monthly totals, top spending categories, average monthly
spend"*.
**Actual:** `return {'year': year, 'total_annual_spent': total}` — a single
number. Monthly totals, top categories and the monthly average are all absent.

### S3. `ExpenseService.get_category_spending(...)` returns a mis-keyed dict and is mistyped
**Prompt:** *"returns aggregated spending for a category over a period"*.
**Actual:** declared `-> int`, but returns the repo dict
`{'category_id': int(row["v"])}` — the money total is stored under the key
`category_id`, with no `total`/`count` key.
**Evidence:** `get_category_spending(cid, '2024-01-01', '2024-12-31')` →
`{'category_id': 3000}`.

### S4. `ExpenseService.get_expense_report(id)` reads keys the repo never returns
```python
report['monthly_spending'] = {
    'category_id': monthly_spending.get('category_id'),
    'total_spent': monthly_spending.get('total_spent'),   # repo never emits this
    'count': monthly_spending.get('count'),               # repo never emits this
}
```
**Evidence:** `get_expense_report(1)` →
`monthly_spending: {'category_id': 1000, 'total_spent': None, 'count': None}`.

### S5. `ExpenseRepository.detect_recurring` does not detect recurring expenses
**Prompt:** *"finds expenses with same amount/category recurring monthly and
marks them"*.
**Actual:** a plain `SELECT ... WHERE is_recurring = 1`. No same-amount/same-
category monthly comparison, and it never marks anything.

### S6. `ExpenseService.detect_category(id)` treats `id` as a year
```python
rows = self.expense_repo.list(start_date=str(id) + '-01-01', end_date=str(id) + '-12-31')
```
**Evidence:** `detect_category(2024)` → `{'id': 2024, 'total': 3000}`.
A hallucinated method (product of CLI over-generation) with no coherent meaning.

### S7. Budget semantics are wrong
- `CategoryRepository.check_category_budget_status` sums **all-time** spend for
  the category (ignores the month) and compares it to `monthly_budget`.
- `BudgetRepository.check_budget_status` compares the budget **limit** to the
  category's `monthly_budget` *field* — never to actual spending.
- Prompt intent: *"check if a category has exceeded its budget"* (monthly
  spend vs monthly limit).

---

## LIBRARY SYSTEM

### S8. `LibraryService.return_book` never increments `available_copies`
**Prompt:** *"sets return_date, updates status, increments copies"*.
**Actual:** sets `return_date`/`status='returned'` and returns — no
`book_repo.update(..., available_copies + 1)`.
**Evidence (reproduced):**
```
copies after borrow: 0
copies after return: 0   (expected 1)
```
This breaks the core circulation invariant: copies leave the pool and never
return.

### S9. `LibraryService.return_book` refuses overdue loans
```python
if loan.status == 'overdue':
    raise OverdueLoanError(...)
```
An overdue loan can therefore never be returned. The status guard is inverted
relative to the domain.

### S10. `LibraryService.get_overdue_loans` returns BOOKS, not overdue loans
**Prompt:** *"returns loans past due_date"*.
**Actual:**
```python
def get_overdue_loans(self) -> List[Dict[str, Any]]:
    return self.book_repo.list_books_with_available_copies()
```
**Evidence:** `get_overdue_loans()` → `[]` (returns books-with-stock). The
correct `LoanRepository.list_overdue_loans()` exists but is never called by the
service.

### S11. `LibraryService.renew_membership` does not toggle `is_active`
**Prompt:** *"toggles is_active"*.
**Actual:** writes `membership_date = now` and — inverted — raises
`MemberNotActiveError` when the member is inactive (exactly the case a renewal
is for).
**Evidence:** `active before renew: 1` → `active after renew: 1`.

### S12. `LibraryService.list_author` returns books
```python
def list_author(self) -> List[Dict[str, Any]]:
    return self.book_repo.list_books_with_available_copies()
```
**Evidence:** `list_author()` → `[]` (books, not authors).

### S13. `LibraryService.get_member_history` discards the loan history
Fetches `loan_history = self.member_repo.get_member_loan_history(member_id)`
then `return member` — the loans are thrown away. The CLI's `member-history`
is wired to this method, so `library member history --member-id` prints the
member, not their loans. (The correct `history()` method exists but is
unreferenced by the CLI.)

### S14. `LibraryService.borrow_member(id)` always raises
```python
raise ValidationError('Book identifier is required to perform a borrow operation')
```
A permanently-failing command (also a CLI over-generation artifact).

### S15. `LibraryService.borrow_book` over-restricts
After the availability check it rejects a member who holds **any** active loan,
while the message claims it is about *this* book (`"...for this book"`) — there
is no `book_id` comparison. A member cannot borrow a second book while holding
one.

### S16. `Member.is_active` default is not captured (latent)
`add_member(..., is_active: bool = None)` stores `None`; `borrow_book` then
`if not member.is_active:` → `MemberNotActiveError`. Masked at the front door
because `member-add` forces `--is-active` **required**, but the default per the
prompt is `True`.

### S17. `BookRepository.search_book` omits author
**Prompt:** *"search by title/author/isbn"*. The query only covers `title` and
`isbn`; author name is never searched.

---

## Cross-cutting

- **S18. `bool`-returning methods carry no invariant enforcement.** Because
  `_apply_impl_floors` only stamps `Dict`/`int`/`float` returns, every
  `bool`-returning workflow method (borrow, return, renew, cancel) is entirely
  LLM-authored and only crash-checked. This is the single highest-leverage
  source of Family-B bugs.

- **S19. Dead / duplicated methods.** Both repositories and the service expose
  a generic CRUD set *and* a custom set
  (`add_category`/`update_category`/`check_category_budget_status`,
  `add_budget`/`update_budget`/`check_budget_status`, `detect_category`,
  `borrow_member`). Unioned design surfaces (spec + LLM, plus scoped splits and
  propagation) mean nothing prunes methods no command needs.

---

## What would catch these

None of the current gates can. The only mechanism that can is a **behavioural
oracle per prompt** — spec-derived assertions executed against the generated
code, e.g.:

- expenses: `get_monthly_report("2024-01")` sums only that month;
  `get_yearly_summary(2024)` has monthly buckets that sum to the year total;
  `get_category_spending` returns a total keyed `total`.
- library: after `borrow` then `return`, `available_copies` returns to its prior
  value; `get_overdue_loans` returns loans (and is empty when none are overdue);
  `renew_membership` flips `is_active`; `search_books(author_name)` finds the
  book.

These assertions, not the facade intent/exit-status mapping, are what a
generation gate must run to keep Family-B bugs out.
