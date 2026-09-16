"""SPEC-derived invariants, one builder per generated project.

Each builder returns ``[(id, fn)]`` where ``fn()`` asserts a statement the
SPECIFICATION makes, using CONCRETE data. These functions never read the
generated source: they call the public API and check the observable result,
so they cannot be satisfied by a body that merely looks plausible.

The two project entries below correspond to the two explicit-CLI prompts the
behavioural work targets (``prompts/prompt_library_system.txt`` and
``prompts/prompt_expenses.txt``). Their assertions are transcribed from the
bullets of those prompts, verbatim in intent.
"""

from __future__ import annotations

import datetime
import inspect


def _numeric_leaves(obj, acc=None):
    """Every number reachable in a nested dict/list (bools excluded)."""
    if acc is None:
        acc = []
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        acc.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _numeric_leaves(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numeric_leaves(v, acc)
    return acc


def _report_total(obj):
    """The single TOTAL a report states for its period, or None.

    A compound report repeats the same money figure in several pieces (a
    headline ``total``, a per-category mapping, a monthly breakdown), so
    summing every number in it is meaningless: it counts the same cents three
    times and reads 3000 for a month that spent 1000. The report's OWN total
    key is the statement to check; a bare number is the other shape.
    """
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, dict):
        for key in ("total", "total_spent", "total_amount", "spent", "sum"):
            val = obj.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return val
    return None


def _numeric_mappings(obj):
    """Every nested mapping whose values are ALL numbers (a money breakdown)."""
    out = []
    if isinstance(obj, dict):
        vals = [
            v for v in obj.values()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        if obj and len(vals) == len(obj):
            out.append(obj)
        for v in obj.values():
            out.extend(_numeric_mappings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_numeric_mappings(v))
    return out


def _is_row(obj, name):
    return type(obj).__name__ == name


def _past_iso(days=5):
    return (
        datetime.datetime.now() - datetime.timedelta(days=days)
    ).replace(microsecond=0).isoformat(sep=" ")


def _future_iso(days=5):
    return (
        datetime.datetime.now() + datetime.timedelta(days=days)
    ).replace(microsecond=0).isoformat(sep=" ")


# A method whose NAME carries one of these tokens is a candidate for the
# specification's "check if a category has exceeded its budget". The
# specification fixes neither the name nor the signature, so the probe is
# discovered by name family and its arguments are bound by parameter name.
_BUDGET_PROBE_TOKENS = (
    "budget_status", "budget_check", "check_budget", "budget_exceeded",
    "exceed",
)


# ---------------------------------------------------------------------------
# library_system
# ---------------------------------------------------------------------------

def _library(proj):
    """Invariants for prompts/prompt_library_system.txt."""
    out = []
    models = proj.models

    def _seed():
        book_repo, _ = proj.repo_for("Book")
        member_repo, _ = proj.repo_for("Member")
        loan_repo, _ = proj.repo_for("Loan")
        bid = proj.make("Book", book_repo, {"available_copies": 2, "title": "Dune"})
        mid = proj.make("Member", member_repo, {"is_active": True})
        return book_repo, member_repo, loan_repo, bid, mid

    def _clamp(kwargs, cls):
        """Drop kwargs the designed class does not declare."""
        names = {f["name"] for f in proj.fields.get(cls, [])}
        return {k: v for k, v in kwargs.items() if k in names}

    def _borrow_then_return_roundtrip():
        """'borrow_book ... decrements copies' + 'return_book ... increments
        copies': the pair must be a round-trip."""
        book_repo, _member_repo, loan_repo, bid, mid = _seed()
        svc = proj.service()
        assert svc is not None, "no service class found"
        svc.borrow_book(mid, bid)
        assert book_repo.get_by_id(bid).available_copies == 1, (
            "borrow_book must decrement available_copies to 1")
        loan = _active_loan(loan_repo, bid)
        assert loan is not None, "borrow_book must create a loan row"
        svc.return_book(loan.id)
        assert book_repo.get_by_id(bid).available_copies == 2, (
            "return_book must increment available_copies back to 2 "
            "(got %s)" % book_repo.get_by_id(bid).available_copies)
        returned = loan_repo.get_by_id(loan.id)
        assert str(returned.status).lower() in (
            "returned",), "return_book must set the loan status to 'returned'"
        # 'return_book(loan_id): sets return_date, updates status, increments
        # copies' — the stamped date is a THIRD, separately observable effect:
        # a body that increments the copies and flips the status still leaves
        # the loan's return_date empty, and nothing about the round-trip above
        # would notice.
        assert returned.return_date, (
            "return_book must stamp return_date ('sets return_date, updates "
            "status, increments copies'); it is still empty — loan=%r"
            % returned)

    out.append(("borrow then return restores available_copies",
                _borrow_then_return_roundtrip))

    def _return_accepts_overdue():
        """'return_book(loan_id)' guards on existence, not on lateness: an
        overdue loan is exactly the one being returned."""
        book_repo, member_repo, loan_repo, bid, mid = _seed()
        svc = proj.service()
        kwargs = _clamp({
            "book_id": bid, "member_id": mid,
            "loan_date": _past_iso(30), "due_date": _past_iso(10),
            "status": "overdue",
        }, "Loan")
        lid = loan_repo.create(models.Loan(**kwargs))
        try:
            svc.return_book(lid)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                "return_book refused an OVERDUE loan (%s: %s) — an overdue "
                "loan is the normal case for a return" % (type(exc).__name__, exc))
        assert str(loan_repo.get_by_id(lid).status).lower() == "returned", (
            "return_book must mark the overdue loan returned")

    out.append(("return_book accepts an overdue loan", _return_accepts_overdue))

    def _overdue_loans_are_loans():
        """'get_overdue_loans(): returns loans past due_date'."""
        book_repo, member_repo, loan_repo, bid, mid = _seed()
        kwargs = _clamp({
            "book_id": bid, "member_id": mid,
            "loan_date": _past_iso(30), "due_date": _past_iso(10),
            "status": "active",
        }, "Loan")
        loan_repo.create(models.Loan(**kwargs))
        svc = proj.service()
        rows = svc.get_overdue_loans()
        assert isinstance(rows, list), "get_overdue_loans must return a list"
        assert rows, "get_overdue_loans returned nothing with a past-due loan"
        for r in rows:
            if isinstance(r, dict):
                assert "due_date" in r, (
                    "get_overdue_loans returned a dict without due_date: %r" % r)
                continue
            assert _is_row(r, "Loan"), (
                "get_overdue_loans returned a %s, not a Loan"
                % type(r).__name__)

    out.append(("get_overdue_loans returns overdue LOANS", _overdue_loans_are_loans))

    def _renew_toggles_is_active():
        """'renew_membership(member_id): toggles is_active'."""
        book_repo, member_repo, loan_repo, bid, mid = _seed()
        svc = proj.service()
        before = bool(member_repo.get_by_id(mid).is_active)
        svc.renew_membership(mid)
        after = bool(member_repo.get_by_id(mid).is_active)
        assert after != before, (
            "renew_membership must TOGGLE is_active (stayed %s)" % after)

    out.append(("renew_membership toggles is_active", _renew_toggles_is_active))

    def _member_history_returns_loans():
        """'loan ... member loan history'; the CLI `member history --member-id`
        must show the member's loans."""
        book_repo, member_repo, loan_repo, bid, mid = _seed()
        kwargs = _clamp({
            "book_id": bid, "member_id": mid,
            "loan_date": _past_iso(1), "due_date": _future_iso(10),
            "status": "active",
        }, "Loan")
        loan_repo.create(models.Loan(**kwargs))
        svc = proj.service()
        fn = getattr(svc, "get_member_history", None) or getattr(
            svc, "member_history", None) or getattr(svc, "history", None)
        assert fn is not None, "no member-history method on the service"
        result = fn(mid)
        if isinstance(result, list):
            assert result, "member history returned no loan for a member with one"
            return
        assert result is not None, "member history returned None"
        # A non-list result (the designed Optional[Member]) is acceptable ONLY
        # if it still carries the loans.
        payload = getattr(result, "loans", None)
        if payload is None and isinstance(result, dict):
            payload = result.get("loans") or result.get("history")
        assert payload, (
            "member history discarded the member's loans (returned %s)"
            % type(result).__name__)

    out.append(("member history surfaces the member's loans",
                _member_history_returns_loans))

    def _search_finds_by_title():
        """'search across title/author/isbn' — at least title and isbn."""
        book_repo, _member_repo, _loan_repo, bid, mid = _seed()
        svc = proj.service()
        fn = getattr(svc, "search_books", None) or getattr(
            svc, "search_book", None)
        assert fn is not None, "no search method on the service"
        found = fn("Dune")
        assert found, "search_books('Dune') found nothing"

    out.append(("search_books finds a book by its title",
                _search_finds_by_title))

    def _search_finds_by_author():
        """'search across title/author/isbn'. AUTHOR is the discriminating
        field: it lives on the referenced entity (books.author_id), so a search
        that LIKEs only the book's own columns returns nothing for an author's
        name (S17)."""
        book_repo, _member_repo, _loan_repo, bid, _mid = _seed()
        svc = proj.service()
        fn = getattr(svc, "search_books", None) or getattr(
            svc, "search_book", None)
        assert fn is not None, "no search method on the service"
        author_repo, _ = proj.repo_for("Author")
        if author_repo is None:
            return  # this design carries no Author entity to search through
        # A token that appears in NO book column, so a title/isbn-only search
        # cannot find the book by accident.
        surname = "Herbert"
        aid = proj.make("Author", author_repo, {"name": surname})
        if "author_id" in {f["name"] for f in proj.fields.get("Book", [])}:
            book_repo.update(bid, {"author_id": aid})
        found = fn(surname)
        assert found, (
            "search_books(%r) found nothing: the search must cover the "
            "author's name, which lives on the referenced Author row"
            % surname)

    out.append(("search_books finds a book by its author's name",
                _search_finds_by_author))

    return out


def _active_loan(loan_repo, book_id):
    """The single active loan for ``book_id``, or None."""
    rows = loan_repo.list()
    for r in rows:
        if getattr(r, "book_id", None) == book_id and str(
            getattr(r, "status", "")
        ).lower() not in ("returned", "cancelled"):
            return r
    return None


# ---------------------------------------------------------------------------
# expenses
# ---------------------------------------------------------------------------

def _expenses(proj):
    """Invariants for prompts/prompt_expenses.txt."""
    out = []
    models = proj.models

    def _clamp(kwargs, cls):
        names = {f["name"] for f in proj.fields.get(cls, [])}
        return {k: v for k, v in kwargs.items() if k in names}

    def _string_leaves(obj, acc=None):
        """Every string reachable in a nested report structure, lower-cased
        by the caller. A status label can sit at any depth of a report dict,
        so the assertion must not assume a shape."""
        acc = [] if acc is None else acc
        if isinstance(obj, str):
            acc.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _string_leaves(v, acc)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _string_leaves(v, acc)
        return acc

    seeds = {"n": 0}

    def _seed_expenses(proj=proj, models=models):
        cat_repo, _ = proj.repo_for("Category")
        exp_repo, _ = proj.repo_for("Expense")
        # The category NAME must differ per seed: the schema declares
        # ``categories.name`` UNIQUE, so a fixed name makes the second
        # invariant that seeds data fail with IntegrityError instead of
        # exercising the behaviour under test.
        seeds["n"] += 1
        cid = proj.make("Category", cat_repo, {
            "name": "Food %d" % seeds["n"], "monthly_budget": 1000})
        # 2024-01 and 2024-02 carry the SAME amount in the SAME category, so
        # a recurring pair genuinely exists for detect_recurring to mark;
        # 2024-03 and the 2023 row give the reports discriminating data.
        rows = [
            ("2024-01-15", 1000, False),
            ("2024-02-15", 1000, False),
            ("2024-03-15", 2000, False),
            ("2023-06-10", 5000, False),
        ]
        for date, amount, rec in rows:
            exp_repo.create(models.Expense(**{
                k: v for k, v in {
                    "amount_cents": amount, "description": "d",
                    "expense_date": date, "category_id": cid,
                    "payment_method": "card", "is_recurring": rec,
                }.items() if k in {
                    f["name"] for f in proj.fields.get("Expense", [])
                }
            }))
        return cat_repo, exp_repo, cid

    def _monthly_report_filters_month():
        """'get_monthly_report(month): total spent ... for a given \"YYYY-MM\"
        month' — the month argument MUST restrict the result."""
        _cat, _exp, _cid = _seed_expenses()
        svc = proj.service()
        fn = getattr(svc, "get_monthly_report", None)
        assert fn is not None, "no get_monthly_report on the service"
        for month, want in (("2024-01", 1000), ("2024-03", 2000)):
            res = fn(month)
            total = _report_total(res)
            assert total == want, (
                "get_monthly_report(%r) must report that month's %d cents as "
                "its total, got %r (report=%r)" % (month, want, total, res))
            # Every money breakdown in the report must be scoped too, and add
            # up to the same figure: a body can filter its headline total
            # while summing every month into the pieces.
            assert any(
                sum(piece.values()) == total
                for piece in _numeric_mappings(res)
            ), (
                "get_monthly_report(%r): no per-category/month breakdown sums "
                "to the month's total %d — the pieces are not month-scoped: %r"
                % (month, total, res))

    out.append(("get_monthly_report filters by month", _monthly_report_filters_month))

    def _yearly_summary_buckets_months():
        """'get_yearly_summary(year): returns monthly totals ...' — the year
        must scope the rows AND the monthly breakdown must exist."""
        _cat, _exp, _cid = _seed_expenses()
        svc = proj.service()
        fn = getattr(svc, "get_yearly_summary", None)
        assert fn is not None, "no get_yearly_summary on the service"
        res = fn(2024)
        leaves = [n for n in _numeric_leaves(res) if n != 2024]
        assert 5000 not in leaves, (
            "get_yearly_summary(2024) included a 2023 expense (5000): %r" % res)
        assert 1000 in leaves and 2000 in leaves, (
            "get_yearly_summary(2024) must expose the monthly totals "
            "(January 1000 and March 2000); got %r (leaves=%s)"
            % (res, leaves))

    out.append(("get_yearly_summary exposes monthly totals",
                _yearly_summary_buckets_months))

    def _category_spending_is_a_total():
        """'get_category_spending(category_id, start_date, end_date): returns
        aggregated spending for a category over a period'."""
        _cat, _exp, cid = _seed_expenses()
        svc = proj.service()
        fn = getattr(svc, "get_category_spending", None)
        assert fn is not None, "no get_category_spending on the service"
        res = fn(cid, "2024-01-01", "2024-12-31")
        if isinstance(res, (int, float)) and not isinstance(res, bool):
            assert res == 4000, (
                "get_category_spending must total the year's 4000 cents, got %s" % res)
            return
        if isinstance(res, dict):
            money = {
                k: v for k, v in res.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
            # The declared return type is a free-form Dict, so the key
            # spelling is not fixed by the design — but the aggregate must
            # actually REPORT the total under some key, not just echo the
            # category's identity.
            assert 4000 in money.values(), (
                "get_category_spending must report the year's 4000 cents as "
                "an aggregate, got %r" % res)
            return
        raise AssertionError(
            "get_category_spending returned %s" % type(res).__name__)

    out.append(("get_category_spending reports a total",
                _category_spending_is_a_total))

    def _category_spending_names_its_total():
        """The aggregate must be NAMED for what it is.

        'returns aggregated spending for a category over a period' — the
        defect this locks out is the money total stored under the name of the
        filter that produced it (``{'category_id': 3000}``): that reads as an
        identity echo rather than a spend aggregate, and it silently starves
        any caller reading a ``total``.
        """
        _cat, _exp, cid = _seed_expenses()
        svc = proj.service()
        res = svc.get_category_spending(cid, "2024-01-01", "2024-12-31")
        assert res is not None, (
            "get_category_spending returned None for a category that spent "
            "4000 cents")
        if not isinstance(res, dict):
            # A bare numeric total is the design's other legitimate shape; it
            # has no key to name, so only its value can be observed.
            assert isinstance(res, (int, float)) and not isinstance(res, bool), (
                "get_category_spending returned %s, neither an aggregate "
                "mapping nor a numeric total" % type(res).__name__)
            assert res == 4000, (
                "get_category_spending must total the year's 4000 cents, got "
                "%s" % res)
            return
        assert "total" in res, (
            "get_category_spending must key its aggregate 'total', got %r" % res)
        assert res["total"] == 4000, (
            "get_category_spending['total'] must be the year's 4000 cents, "
            "got %r" % res.get("total"))

    out.append(("get_category_spending keys its aggregate as 'total'",
                _category_spending_names_its_total))

    def _monthly_report_parts():
        """'returns total spent, per-category breakdown, budget status
        (on_track/warning/exceeded) for a given "YYYY-MM" month'.

        Honouring the month is only the FIRST requirement; the three PIECES
        are the rest, and a dict carrying just ``{'month', 'total'}`` drops
        two of them without failing anything that checks a number.
        """
        _cat, _exp, _cid = _seed_expenses()
        svc = proj.service()
        res = svc.get_monthly_report("2024-01")
        assert isinstance(res, dict), (
            "get_monthly_report must return a dict, got %s"
            % type(res).__name__)
        assert 1000 in _numeric_leaves(res), (
            "the report must carry January's 1000-cent total: %r" % res)
        assert any(
            isinstance(v, dict) and 1000 in _numeric_leaves(v)
            for v in res.values()
        ), (
            "the report must carry a per-category BREAKDOWN (a mapping of "
            "category to spend) — January's 1000 belongs to the seeded "
            "category: %r" % res)
        labels = {str(s).lower() for s in _string_leaves(res)}
        assert labels & {"on_track", "warning", "exceeded"}, (
            "the report must carry a budget STATUS in the specification's "
            "own words (on_track/warning/exceeded): %r" % res)

    out.append(("get_monthly_report returns the spec's three pieces",
                _monthly_report_parts))

    def _monthly_status_is_month_scoped():
        """The status compares THAT month's spending to the month's limit.

        An all-time comparison cannot tell the two apart: this seeds a budget
        for a month with NO spending while the category's all-time total is
        4000 cents, so an all-time comparison reports an exceedance where the
        correct answer is 'on track'.
        """
        _cat, _exp, cid = _seed_expenses()
        svc = proj.service()
        budget_repo, _budget_cls = proj.repo_for("Budget")
        assert budget_repo is not None, (
            "no Budget repository to seed a limit with")
        for month, limit in (("2024-03", 100), ("2023-12", 5000)):
            proj.make("Budget", budget_repo, {
                "category_id": cid, "month": month,
                "amount_limit_cents": limit,
            })
        spent = svc.get_monthly_report("2024-03")
        labels = {str(s).lower() for s in _string_leaves(spent)}
        assert labels & {"exceeded", "over_budget", "over budget"}, (
            "March 2024 spent 2000 against a 100-cent limit, so the report "
            "must call it exceeded: %r" % spent)
        quiet = svc.get_monthly_report("2023-12")
        quiet_labels = {str(s).lower() for s in _string_leaves(quiet)}
        assert not (quiet_labels & {"exceeded", "over_budget", "over budget"}), (
            "2023-12 has NO spending, so the report must NOT call it exceeded "
            "(the category's all-time spend is 4000 — an all-time comparison "
            "would): %r" % quiet)

    out.append(("budget status compares the month, not lifetime spending",
                _monthly_status_is_month_scoped))

    def _yearly_summary_parts():
        """'returns monthly totals, top spending categories, average monthly
        spend' — the ranked and averaged pieces must be present too."""
        _cat, _exp, _cid = _seed_expenses()
        svc = proj.service()
        res = svc.get_yearly_summary(2024)
        assert isinstance(res, dict), (
            "get_yearly_summary must return a dict, got %s"
            % type(res).__name__)
        keys = {str(k).lower() for k in res}
        assert any("top" in k for k in keys), (
            "get_yearly_summary must expose the top spending categories: %r"
            % res)
        assert any("average" in k or "avg" in k for k in keys), (
            "get_yearly_summary must expose the average monthly spend: %r" % res)

    out.append(("get_yearly_summary returns top categories and the average",
                _yearly_summary_parts))

    def _budget_row_status_is_month_scoped():
        """'check if a category has exceeded its budget' at the REPOSITORY
        level. The discriminating case: the budget row for March 2024 has a
        100-cent limit while 2000 cents were spent that month, so a status
        that never reads spending (e.g. one comparing the limit to the
        category's own budget FIELD) cannot report an exceedance.
        """
        _cat, _exp, cid = _seed_expenses()
        budget_repo, _budget_cls = proj.repo_for("Budget")
        assert budget_repo is not None, (
            "no Budget repository to seed a limit with")
        bid = proj.make("Budget", budget_repo, {
            "category_id": cid, "month": "2024-03",
            "amount_limit_cents": 100,
        })
        svc = proj.service()
        hot = {
            label: (call, sensitive)
            for label, call, sensitive in _budget_status_probes(
                svc, cid, "2024-03", bid)
        }
        quiet = {
            label: call
            for label, call, _sensitive in _budget_status_probes(
                svc, cid, "2023-12", bid)
        }
        assert hot, (
            "no budget-status method found: the specification requires "
            "BudgetRepository to 'check if a category has exceeded its budget'")
        over = ("exceed", "over")
        seen = []
        for label in sorted(hot):
            call, month_sensitive = hot[label]
            try:
                hot_res = call()
            except Exception as exc:  # noqa: BLE001 - a raising probe is not
                # the one under test; the report also names the working one
                seen.append("%s raised %s" % (label, type(exc).__name__))
                continue
            if hot_res is None:
                seen.append("%s returned None" % label)
                continue
            if not any(w in str(hot_res).lower() for w in over):
                seen.append(
                    "%s said %r for a month that spent 2000 against a "
                    "100-cent limit" % (label, hot_res))
                continue
            if not month_sensitive or label not in quiet:
                return
            try:
                quiet_res = quiet[label]()
            except Exception:  # noqa: BLE001 - no budget row for that month
                return
            if quiet_res is not None and any(
                w in str(quiet_res).lower() for w in over
            ):
                raise AssertionError(
                    "%s called 2023-12 (NO spending) overspent (%r): the "
                    "comparison is not month-scoped" % (label, quiet_res))
            return
        raise AssertionError(
            "no budget-status probe reported an exceeded month: %s"
            % "; ".join(seen))

    out.append(("repository budget status compares the limit to spending",
                _budget_row_status_is_month_scoped))

    def _bind_budget_probe(fn, cid, month, budget_id):
        """Wrap ``fn`` so it is called with the seeded ids it DECLARES.

        The specification fixes neither the name nor the signature of "check
        if a category has exceeded its budget": a design may scope it by
        category alone, or by category AND month (a budget row is keyed by
        both). Binding by parameter name keeps the probe agnostic to that
        choice, instead of demanding one spelling and reporting a TypeError
        for the other.
        """
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return None
        known = {
            "category_id": cid, "category": cid, "cat_id": cid,
            "month": month, "period": month, "budget_month": month,
            "budget_id": budget_id, "id": budget_id,
        }
        kwargs = {}
        for pname, param in sig.parameters.items():
            if pname == "self" or param.kind in (
                param.VAR_POSITIONAL, param.VAR_KEYWORD,
            ):
                continue
            if pname in known:
                kwargs[pname] = known[pname]
            elif param.default is param.empty:
                return None  # a required argument the seed cannot supply
        month_sensitive = any(
            k in kwargs for k in ("month", "period", "budget_month")
        )
        return (lambda: fn(**kwargs)), month_sensitive

    def _budget_status_probes(svc, cid, month, budget_id):
        """(label, callable) for every budget-status probe of ``month``.

        The rule is stated on BudgetRepository ("check if a CATEGORY has
        exceeded its budget"), so a category-scoped probe is tried before a
        budget-row-id one: ``check_budget(budget_id)`` legitimately returns
        None for a category id, while
        ``check_category_budget_status(category_id)`` is the method the
        specification actually describes.
        """
        found = []
        for name in sorted(dir(svc)):
            low = name.lower()
            if not any(t in low for t in _BUDGET_PROBE_TOKENS):
                continue
            found.append(("service.%s" % name, getattr(svc, name)))
        for stem, mod in sorted(proj.repos.items()):
            for attr in sorted(dir(mod)):
                obj = getattr(mod, attr)
                if not isinstance(obj, type):
                    continue
                for mname in sorted(dir(obj)):
                    low = mname.lower()
                    if mname.startswith("_"):
                        continue
                    if not any(t in low for t in _BUDGET_PROBE_TOKENS):
                        continue
                    found.append((
                        "%s.%s" % (stem, mname),
                        getattr(obj(proj.db()), mname),
                    ))
        out = []
        for label, fn in found:
            bound = _bind_budget_probe(fn, cid, month, budget_id)
            if bound is None:
                continue
            call, month_sensitive = bound
            out.append((label, call, month_sensitive))
        # Category-scoped probes first, then the rest.
        out.sort(key=lambda triple: "categor" not in triple[0].lower())
        return out

    def _budget_status_reflects_spending():
        """'check if a category has exceeded its budget' — status is about
        SPENDING against the limit, not the limit against itself."""
        _cat_repo, _exp_repo, cid = _seed_expenses()
        svc = proj.service()
        budget_repo, _budget_cls = proj.repo_for("Budget")
        bid = None
        if budget_repo is not None:
            bid = proj.make("Budget", budget_repo, {
                "category_id": cid, "month": "2024-03",
                "amount_limit_cents": 100,
            })
        probes = _budget_status_probes(svc, cid, "2024-03", bid)
        assert probes, "no budget-status method found"
        # March 2024 spent 2000 cents against a 100-cent limit.
        seen = []
        for label, call, _sensitive in probes:
            try:
                res = call()
            except Exception as exc:  # noqa: BLE001 - a raising probe is not
                # the one under test; the report also names the working one
                seen.append("%s raised %s" % (label, type(exc).__name__))
                continue
            if res is None:
                seen.append("%s returned None" % label)
                continue
            text = str(res).lower()
            if any(w in text for w in ("exceed", "over", "warning")):
                return
            seen.append("%s said %r" % (label, res))
        raise AssertionError(
            "no budget-status probe reported an exceeded category: %s"
            % "; ".join(seen)
        )

    out.append(("budget status reflects actual spending",
                _budget_status_reflects_spending))

    def _detect_recurring_marks_rows():
        """'detect_recurring(): finds expenses with same amount/category
        recurring monthly and MARKS them'."""
        cat_repo, exp_repo, cid = _seed_expenses()
        svc = proj.service()
        fn = getattr(svc, "detect_recurring", None)
        assert fn is not None, "no detect_recurring on the service"
        fn()
        marked = [
            r for r in exp_repo.list()
            if bool(getattr(r, "is_recurring", False))
        ]
        assert marked, (
            "detect_recurring did not mark the recurring expense pair "
            "(same amount and category in two months)")

    out.append(("detect_recurring marks recurring rows",
                _detect_recurring_marks_rows))

    return out


# name -> builder. A project without an entry is reported, never silently
# skipped: the oracle must not appear to pass by having no invariants.
REGISTRY = {
    "library_system": _library,
    "expenses": _expenses,
}
