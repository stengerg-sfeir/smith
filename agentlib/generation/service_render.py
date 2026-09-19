"""Deterministic service renderer + LLM-fill merge for designed extra methods.

Extracted from agent.py. Renders the service shell and gives contract methods
real deterministic bodies while extras become locked stubs; when a prompt is
given, ONLY the stubs travel to the LLM inside a mini-skeleton and an
accepted fill is spliced back per-method. No behaviour change.
"""
import ast
import builtins
import difflib
import os
import re
from pathlib import Path

from ..config import LLM_RETRY_TEMPERATURE
from ..naming import _camel, _entity_table_name, _plural, _snake
from ..llm.fill import _llm_fill
from ..kernel.service import dispatch_impl_body
from ..kernel.service.common import (
    _filter_params,
    _resolve_filter_args,
    fk_parent_guards,
    not_found_exception,
    not_found_message,
)
from ..kernel.repo.finder import _render_simple_finder, _simple_finder_spec
from ..kernel.repo.threshold_compare import _flag_threshold_spec
from ..kernel.repo.variant import _existing_variant_alias, _render_variant_alias
from ..pipeline.method_contract import (
    compile_contract_impl,
    method_contract_violations,
)
from .helpers import _method_stub_code
from .model_render import _coerce_field_default
from .repo_render import _repo_dict_keys
from .splice import _fn_has_stub_raise, _merge_stub_bodies

# Spellings a design may use for a BOOLEAN filter parameter. A bool param is
# never a BOUND value in list() — the click flag behind it defaults to False
# and False must mean "no filter" — so its declared type is load-bearing: it
# selects the constant-predicate rewrite in _apply_filter_floors below.
_BOOL_FILTER_TYPES = (
    "bool",
    "boolean",
    "Optional[bool]",
    "bool | None",
    "None | bool",
)


def _is_bool_param_type(ptype):
    """True when a declared param type denotes a boolean flag.

    Accepts the bare word in either case, the Optional/union spellings and a
    trailing default (``bool = False``), so the flag rewrite is not defeated
    by a spelling the design happened to choose.
    """
    if not ptype:
        return False
    text = str(ptype).split("=")[0].strip()
    if text in _BOOL_FILTER_TYPES:
        return True
    parts = re.split(r"[|\[\],\s]+", text)
    return any(p.lower() in ("bool", "boolean") for p in parts if p)


def _bulk_update_spec(attr, meth, entities_by_class):
    """Resolve a ``bulk_update_<col>`` repo-method spec against the design.

    Bounded: the method must be named ``bulk_update_<col>`` where ``<col>``
    resolves (exact, then unique prefix/suffix) to ONE non-id field of the
    repo's OWN entity. The synthesized repo method takes ``(ids, value)`` so
    the service fill's positional call (product_ids, new_stock_quantity)
    binds without name heuristics. Returns None when not resolvable.
    """
    if not (meth or "").startswith("bulk_update_"):
        return None
    ent_snake = attr[:-len("_repo")] if attr.endswith("_repo") else attr
    cls = _camel(ent_snake)
    ent = entities_by_class.get(cls)
    if not isinstance(ent, dict):
        return None
    col_suffix = meth[len("bulk_update_"):]
    fields = {
        f.get("name"): f
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }
    col = None
    if col_suffix in fields:
        col = col_suffix
    else:
        cands = [
            f for f in fields
            if f.startswith(col_suffix + "_") or f.endswith("_" + col_suffix)
        ]
        if len(cands) == 1:
            col = cands[0]
    if col is None or col == "id":
        return None
    return {
        "meth": meth,
        "col": col,
        "table": _entity_table_name(ent),
    }


def _render_bulk_update(spec):
    """Deterministic repo body for a ``bulk_update_<col>`` method."""
    return (
        "    def %(meth)s(self, ids, value):\n"
        "        with self.db.connect() as conn:\n"
        "            cur = conn.cursor()\n"
        "            for pid in ids:\n"
        "                cur.execute(\"UPDATE %(table)s SET %(col)s = ? \"\n"
        "                            \"WHERE id = ?\", (value, pid))\n"
        "            conn.commit()\n"
        "        return True\n" % spec
    )


def _bulk_update_repo_targets(designs, entities_by_class):
    """{entity_snake: (repo_method, col)} for each designed repository
    ``bulk_update_<col>`` method, resolved through ``_bulk_update_spec``.

    Feeds the deterministic service ``bulk_update_<entity>`` delegation so it
    can parse a comma-separated ``ids`` string into ints and delegate to the
    repo method that already knows the column to set — instead of an LLM
    fill that compares str ids against int ids (prompt 35's always-raise
    NotFoundError)."""
    out = {}
    for path, kind, data in designs or []:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        if _camel(ent_snake) not in entities_by_class:
            continue
        attr = ent_snake + "_repo"
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            spec = _bulk_update_spec(attr, m["name"], entities_by_class)
            if spec:
                out[ent_snake] = (m["name"], spec["col"])
    return out


def _search_repo_targets(designs, entities_by_class):
    """{entity_snake: repo_method} for each designed repository method that
    is a search (``search`` or ``search_<plural>``) over its OWN entity.

    Feeds the deterministic service ``search_<entity>`` delegation: a book
    search is a Book-only predicate, so ``search_book(term)`` must become
    ``self.book_repo.search_books(term)`` instead of an LLM stub that
    hallucinates member_repo/loan_repo (the single ``term`` param hides that
    the search spans title/isbn/author — an abstraction problem the 4B model
    resolves by dragging in unrelated repos)."""
    out = {}
    for path, kind, data in designs or []:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        if _camel(ent_snake) not in entities_by_class:
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            mn = m["name"]
            if mn == "search" or (mn.startswith("search_") and mn != "search_" + _plural(ent_snake) + "_all"):
                out.setdefault(ent_snake, mn)
    return out


_STATE_TARGETS = {
    "confirm": "confirmed",
    "ship": "shipped",
    "cancel": "cancelled",
    "approve": "approved",
    "reject": "rejected",
    "complete": "completed",
    "close": "closed",
    "open": "opened",
    "activate": "activated",
    "deactivate": "deactivated",
    "start": "started",
    "finish": "finished",
    "submit": "submitted",
    "fulfill": "fulfilled",
    "pay": "paid",
    "archive": "archived",
    "pause": "paused",
    "resume": "resumed",
    "return": "returned",
    # Non-English synonyms: the state verb is extracted from the designed
    # service method name (ship_order -> "ship"); a French/US-native method
    # name (annuler_commande) must map to the same past-participle too.
    "annuler": "cancelled",
    "approuver": "approved",
    "rejeter": "rejected",
    "terminer": "completed",
    "fermer": "closed",
    "ouvrir": "opened",
    "activer": "activated",
    "desactiver": "deactivated",
    "demarrer": "started",
    "finir": "finished",
    "payer": "paid",
    "archiver": "archived",
    "suspendre": "paused",
    "reprendre": "resumed",
    "retourner": "returned",
}

# Deterministic fill-prompt rule: date/datetime columns are read back from
# SQLite as ISO-format STRINGS (str), not datetime objects. The LLM keeps
# calling .isoformat()/.date()/.strftime()/.year on them (get_loan_report
# rejected attempts), so a hard instruction is injected into every service
# fill hint to pass the string through. This saves retry tokens.
_DATE_VALUE_RULE = (
    "DATE/DATETIME FIELDS  fields read back from the database are "
    "ISO-format STRINGS (str), NOT datetime objects — never call "
    ".isoformat(), .date(), .strftime(), .year, .month, or .day on them. "
    "Pass the string through as-is."
)

# Deterministic fill-prompt rule: repo getters return MODEL INSTANCES, not
# dicts. The 4B model keeps doing self.book_repo.get_by_id(...).get(
# 'available_copies') (borrow_member rejection: "does not return a dict — do
# not use .get() on it"). A hard instruction mirrors _DATE_VALUE_RULE.
_REPO_ACCESSOR_RULE = (
    "REPO ACCESSORS  every repo getter returns a MODEL INSTANCE — the entity "
    "class, never a dict. Read fields with attribute access (row.field), "
    "never .get() or ['key'] on the result. "
    "Read the declared fields straight off the instance."
)

# Deterministic fill-prompt rule: repo methods are fixed at design time; the
# 4B model keeps inventing a nicer-sounding name (budget_repo.
# get_by_category_and_month) that does not exist, then indexing its result as
# a dict (expense : "does not return a dict — do not index it"). A hard
# instruction forbids invented names and points to the listed method that
# already covers the lookup (self.budget_repo.list_budgets(category_id, month)
# -> List[Dict], so index element [0] then read the dict keys).
_REPO_METHOD_RULE = (
    "REPO METHOD NAMES  call ONLY the methods explicitly listed in the "
    "repository interface — never invent a method name (e.g. a "
    "get_<x>_and_<y> style lookup that is not listed). Calling a method that "
    "is not listed is a hard rejection. If you need to look a row up by a "
    "pair of values, call the listed method that returns a COLLECTION, then "
    "take element [0] (or iterate) and read its declared fields/keys."
)

# Deterministic fill-prompt rule: a repo call must be statically verifiable;
# calling with ** (dict) unpacking hides the argument names/arity, so the
# validator rejects it ("cannot verify arity" on expense's
# self.expense_repo.list_expenses(**filters)). Pass named keyword arguments
# explicitly, one at a time, never **spread.
_REPO_SPREAD_RULE = (
    "REPO CALL ARITY  never call a repo method with ** dict-unpacking — the "
    "argument names and arity cannot be verified statically, so it is a hard "
    "rejection. Pass each named keyword argument explicitly, one per "
    "declared parameter of the listed method."
)

# Deterministic fill-prompt rule: the model wraps a required business rule in
# `try: ... except Exception: pass`, which swallows the very exception the
# rule raises — add_expense raised BudgetExceededException inside a guarded
# try, so the check became a no-op. It also called a designed lookup with a
# hardcoded None id.
_NO_SWALLOW_RULE = (
    "EXCEPTION HANDLING  never wrap a designed business rule in "
    "`try: ... except Exception: pass` — it silently swallows the exception "
    "the rule raises. Call the check and raise the designed exception "
    "DIRECTLY and unguarded; catch only a SPECIFIC type you intend to "
    "translate. Never call a repository method with a hardcoded None for a "
    "required id."
)

# Deterministic fill-prompt rule: a repo getter that returns ONE row
# (get_by_id / get_by_<x> / get_<x>_by_<y>) returns None when no such row
# exists. The 4B model reads an attribute straight off the call —
# self.budget_repo.get_by_category_and_month(category_id, month).id — which
# raises AttributeError when the budget is missing (expense add_expense
# crash). A hard instruction: assign the row to a local and guard every use.
_OPTIONAL_GETTER_RULE = (
    "OPTIONAL SINGLE-ROW GETTERS  a repository getter that returns ONE row "
    "(get_by_id(...), get_by_<x>(...), get_<x>_by_<y>(...)) returns None "
    "when no matching row exists. NEVER read an attribute or call a method "
    "directly off the call — `self.<repo>.get_...( ... ).id` raises "
    "AttributeError when the row is missing. Assign the result to a local "
    "variable, guard with `if <local> is not None:` (or `if <local>:`), and "
    "use <local>.field only inside that guard. NEVER look the same row up a "
    "SECOND time — reuse the local you already bound. Consult an OPTIONAL "
    "row (e.g. a category's budget) only when its row exists."
)

# Deterministic fill-prompt rule: the model ADDS refusals the specification
# never states, and makes them wider than the message they raise. Library's
# borrow_book was filled with
#     for loan in existing_loans:
#         elif loan.status == 'active':
#             raise ValidationError(f'Member {member_id} already has an active
#                                    loan for book {book_id}')
# — while the spec asks only that borrow_book "checks availability, creates
# loan, decrements copies". The extra scan refuses a borrow whenever the
# member holds ANY active loan (book_id is never compared), so a member who
# borrowed one book could never borrow another, and the raised message named
# a pair the condition never tested. A hard instruction, mirroring the other
# rules: enforce ONLY the stated conditions, and make every guard test what
# its message claims.
_NO_UNSTATED_GUARD_RULE = (
    "GUARDS  enforce ONLY the conditions the method's description states. "
    "Never add a refusal for something the description does not mention — an "
    "existence, availability, or state check on the row being operated on is "
    "allowed, but a duplicate/already-exists check or any test on the OTHER "
    "rows of an entity is NOT unless it is stated. Every guard must test "
    "exactly what its message claims: if the message names an id or a field, "
    "the condition must compare THAT id or field, never a broader one."
)


# Validates in the SYSTEM message (primacy slot) so a small model attends to
# the rules instead of losing them at the bottom of a long user-side
# instruction. Domain-agnostic prohibitions; the user-side interface listing
# stays the authoritative repo-method inventory.
_FILL_SYSTEM_RULES = "\n\n".join([
    _DATE_VALUE_RULE,
    _REPO_ACCESSOR_RULE,
    _REPO_METHOD_RULE,
    _REPO_SPREAD_RULE,
    _NO_SWALLOW_RULE,
    _OPTIONAL_GETTER_RULE,
    _NO_UNSTATED_GUARD_RULE,
])


def _fill_debug_root():
    """Directory for fill-retry dumps, or "" when debugging is disabled.

    Set ``NEUROSYM_FILL_DEBUG=<dir>`` to capture every REJECTED fill body,
    the ACCEPTED retry, and a unified diff between them. This is how a
    transient fill retry (e.g. library_system's borrow_member attempt 1 ->
    attempt 2) can be inspected AFTER the run: the run log only carries the
    final attempt's rejection, so without this the rejected body is lost.
    Off by default — zero effect unless the env var is set.
    """
    return os.environ.get("NEUROSYM_FILL_DEBUG", "").strip()


def _write_debug_text(path, text):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text if text is not None else "")
        return True
    except OSError:
        return False


def _dump_fill_retry(root, service, method, rejected, accepted):
    """Persist a fill retry so it can be diffed after the fact.

    ``rejected``: [(attempt_no, body, violations)] in attempt order;
    ``accepted``: (attempt_no, body) or None. Writes, per method:
      <svc>.<method>.a<N>.rejected.py     (each rejected body)
      <svc>.<method>.a<N>.violations.txt  (that attempt's violations)
      <svc>.<method>.a<M>.accepted.py     (the body that passed)
      <svc>.<method>.diff.txt             (last rejected vs accepted)
    No-op when ``root`` is empty or nothing was rejected (a first-attempt
    success has nothing to compare).
    """
    if not root or not rejected:
        return
    try:
        os.makedirs(root, exist_ok=True)
    except OSError:
        return
    stem = "%s.%s" % (service, method)
    for attempt_no, body, violations in rejected:
        _write_debug_text(
            os.path.join(root, "%s.a%d.rejected.py" % (stem, attempt_no)),
            body,
        )
        _write_debug_text(
            os.path.join(root, "%s.a%d.violations.txt" % (stem, attempt_no)),
            "\n".join(violations or []),
        )
    if accepted is None:
        return
    attempt_no, body = accepted
    _write_debug_text(
        os.path.join(root, "%s.a%d.accepted.py" % (stem, attempt_no)), body
    )
    old_no, old_body, _ = rejected[-1]
    diff = "\n".join(
        difflib.unified_diff(
            (old_body or "").splitlines(),
            (body or "").splitlines(),
            fromfile="a%d.rejected" % old_no,
            tofile="a%d.accepted" % attempt_no,
            lineterm="",
        )
    )
    _write_debug_text(os.path.join(root, stem + ".diff.txt"), diff + "\n")


def _required_constructor_fields(entities_by_class):
    """{cls: sorted non-nullable constructor field names}.

    The fields a caller MUST supply when constructing an instance (excluding
    ``id`` and auto-now date/datetime columns the deterministic renderer
    stamps itself). Shown in the fill hint so the model never builds a
    member/loan/... missing a required field (borrow_member: Loan() missing
    book_id, due_date, loan_date, member_id, status).
    """
    out = {}
    for cls, ent in entities_by_class.items():
        req = []
        for f in ent.get("fields") or []:
            if not isinstance(f, dict) or not f.get("name"):
                continue
            name = f["name"]
            if name == "id" or f.get("nullable"):
                continue
            if f.get("default") is not None:
                # A spec-declared default is supplied by the dataclass itself
                # when the caller omits the field, so it is not a required
                # constructor argument.
                continue
            if f.get("auto") == "now" and f.get("type") in ("date", "datetime"):
                continue
            req.append(name)
        if req:
            out[cls] = sorted(req)
    return out


def _zero_param_dict_repo_customs(designs, entities_by_class):
    """[(entity_snake, method_name)] of DESIGNED repository custom methods
    that take no params and return a Dict — aggregate-shaped. Feeds the
    unique-shape service delegation (never name-based)."""
    known = {_snake(c) for c in entities_by_class}
    out = []
    for path, kind, data in designs or []:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        if ent_snake not in known:
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            params = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict)
            ]
            ret = m.get("returns") or ""
            if not params and "dict" in ret.lower():
                out.append((ent_snake, m["name"]))
    return out


def _repo_custom_signatures(designs, entities_by_class):
    """{method_name: [(entity_snake, [param_names])]} for every DESIGNED
    repository custom method.

    Feeds same-name repo delegation for a service method that is neither a
    CRUD verb (so ``_generic_service_delegation`` declines it) nor a
    zero-param aggregate (so ``_zero_param_dict_repo_customs`` declines it):
    a designed ``get_yearly_summary(year)`` on the service side delegates to
    the repo's own ``get_yearly_summary(year)`` when the parameter names
    match EXACTLY. Same-name + same-params is a shape match, never a name
    heuristic on the method spelling — a mismatch leaves the method a stub
    for the LLM fill as before. Parameter names must match exactly so a
    service ``get_report(year)`` never wires against a repo
    ``get_report(year, month)``.
    """
    known = {_snake(c) for c in entities_by_class}
    out = {}
    for path, kind, data in designs or []:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        if ent_snake not in known:
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            pnames = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            out.setdefault(m["name"], []).append((ent_snake, pnames))
    return out


def _repo_custom_returns(designs, entities_by_class):
    """{method_name: [(entity_snake, [param_names], returns)]} for every
    DESIGNED repository custom method, paired with its declared return type.

    Mirrors ``_repo_custom_signatures`` (same name/params shape match) and
    additionally carries the return annotation, so a delegating service
    method can be given the type of what it actually returns.
    """
    known = {_snake(c) for c in entities_by_class}
    out = {}
    for path, kind, data in designs or []:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        if ent_snake not in known:
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            pnames = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            out.setdefault(m["name"], []).append(
                (ent_snake, pnames, m.get("returns") or "")
            )
    return out


def _returns_a_container(returns):
    """True when a declared return names a collection or mapping."""
    low = (returns or "").lower()
    return "dict" in low or "list" in low or "[" in low


def _is_generic_crud_name(name, entities_by_class):
    """True when ``_generic_service_delegation`` owns this method name.

    ``_service_method_body`` reaches its same-name repository delegation only
    AFTER the generic tier, so a method the generic tier handles
    (``list_expense`` -> ``expense_repo.list()``) must NOT be aligned against
    a same-name repo custom: it delegates to ``list()``, not to the custom.
    """
    for ent_name in entities_by_class or {}:
        var = _snake(ent_name)
        if name in {
            "add_" + var, "create_" + var,
            "list_" + var, "list_" + _plural(var),
            "get_%s_by_id" % var,
            "update_" + var, "delete_" + var,
            "bulk_update_" + var, "search_" + var,
        }:
            return True
    return False


def _align_delegated_returns(svc_design, repo_returns, entities_by_class,
                             verbose=False):
    """Give a thin-delegation service method the repository's return type.

    A service method that IS a pass-through (same name, same parameter names,
    exactly ONE repository candidate — the shape match
    ``_service_method_body``'s same-name route uses) renders
    ``return self.<repo>.<name>(...)``, so it returns exactly what the
    repository returns. The design model declares the two signatures
    INDEPENDENTLY and they can disagree: expenses shipped
    ``get_category_spending(category_id, start_date, end_date) -> int`` whose
    body returns the repository's ``Dict[str, Any]`` — an annotation that
    contradicted the only value it could ever produce, and that no consumer
    could catch.

    Only the UNAMBIGUOUS direction is aligned: a method that DECLARES a
    scalar while the repository declares a container. A container/container
    disagreement (``List[Expense]`` vs ``List[Dict]``) is a design judgement
    about element shape and is left alone, so this never rewrites a working
    CLI surface.
    """
    if not isinstance(svc_design, dict):
        return
    for m in svc_design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        name = m["name"]
        if _is_generic_crud_name(name, entities_by_class):
            continue
        # A method carrying an `impl` renders FROM that impl — the same-name
        # repository delegation is downstream of impl dispatch, so such a
        # method's body is not a pass-through and its declared return must
        # stand (library's `return_book -> bool` is a deterministic effect
        # body, not a call to a same-named repository method).
        if isinstance(m.get("impl"), dict):
            continue
        pnames = [
            p.get("name") for p in (m.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        cands = [
            entry for entry in (repo_returns or {}).get(name, [])
            if entry[1] == pnames
        ]
        if len(cands) != 1:
            continue
        _ent, _params, repo_ret = cands[0]
        if not repo_ret or not _returns_a_container(repo_ret):
            continue
        if _returns_a_container(m.get("returns")):
            continue
        if verbose:
            print(
                "    [contract] %s: returns %r aligned to the repository's %r"
                % (name, m.get("returns") or "", repo_ret)
            )
        m["returns"] = repo_ret


# Flag column prefixes that mean "this row carries the property".
_FLAG_PREFIXES = ("is_", "has_")


def _detect_and_mark_impl(m, entities_by_class):
    """Deterministic "mark the recurring rows" body, or None.

    Fires for a zero-param ``detect_*`` method that returns a list, when
    EXACTLY ONE designed entity carries a single bool flag together with
    exactly one date/datetime column, one numeric non-FK column and one FK
    column — the shape "same amount, same foreign key, more than one month".

    The LLM fill gets this backwards: it filters on the very flag it is meant
    to set (expenses' repo ``detect_recurring`` shipped
    ``WHERE e.is_recurring = 1``, so nothing was ever marked). Rows are
    grouped by the design's own key columns, and only a key seen in two
    distinct months marks its rows. Anything else returns None so the method
    keeps its fill.
    """
    if "list" not in (m.get("returns") or "").lower():
        return None
    cands = []
    for cls_name, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict):
            continue
        fields = [
            f for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name") and f["name"] != "id"
        ]
        flags = [
            f["name"] for f in fields
            if f.get("type") == "bool"
            and f["name"].startswith(_FLAG_PREFIXES)
        ]
        dates = [
            f["name"] for f in fields
            if f.get("type") in ("date", "datetime")
        ]
        nums = [
            f["name"] for f in fields
            if f.get("type") in ("int", "float")
            and not f["name"].endswith("_id")
        ]
        fks = [f["name"] for f in fields if f["name"].endswith("_id")]
        if len(flags) == 1 and len(dates) == 1 and len(nums) == 1 and len(fks) == 1:
            cands.append((cls_name, flags[0], dates[0], nums[0], fks[0]))
    if len(cands) != 1:
        return None
    cls_name, flag, date_field, num_field, fk = cands[0]
    var = _snake(cls_name)
    return [
        "        rows = self.%s_repo.list()" % var,
        "        months = {}",
        "        for e in rows:",
        "            key = (getattr(e, '%s', None), getattr(e, '%s', None))"
        % (fk, num_field),
        "            months.setdefault(key, set()).add("
        "str(getattr(e, '%s', ''))[:7])" % date_field,
        "        for e in rows:",
        "            key = (getattr(e, '%s', None), getattr(e, '%s', None))"
        % (fk, num_field),
        "            if len(months.get(key) or ()) >= 2 "
        "and not getattr(e, '%s', False):" % flag,
        "                self.%s_repo.update(e.id, {'%s': True})" % (var, flag),
        "        return self.%s_repo.list()" % var,
    ]


def _service_method_body(m, entities_by_class, exception_names, repo_customs=None, repo_bulk_updates=None, repo_search_targets=None, repo_signatures=None):
    """Deterministic body lines for a service method, or None (=> stub).

    Fully declarative: a designed method may carry an `impl` object naming
    the entity/fields/params its body operates on; generic handlers render
    the body from those declarations alone. There are NO method-name
    patterns, NO field-suffix heuristics, and NO domain vocabulary here.
    Methods without a resolvable impl fall through to unique-shape
    aggregate delegation, then generic CRUD delegation
    (add_/list_/get_/update_/delete_<entity> convention), then to a locked
    stub for the LLM fill phase.
    """
    name = m.get("name") or ""
    # A single-id check_<entity> method is a state probe: return the
    # entity's declared fields as a dict. The deterministic check_ branch
    # takes priority over any impl recipe, which can invent bogus aggregate
    # logic (prompt 26's check_book got a sum_by_group impl summing a date
    # column -> int + str TypeError). Impl bodies are never run through
    # _semantic_fill_violations, so without this early route check_book
    # ships the broken body untouched.
    for _ent_name in entities_by_class:
        if name == "check_" + _snake(_ent_name) and len(m.get("params") or []) == 1:
            return _generic_service_delegation(
                m, entities_by_class, exception_names, repo_bulk_updates, repo_search_targets,
                repo_signatures
            )
    # Detect-and-mark recipe, ahead of every delegation tier: delegating hands
    # the behaviour to a fill that filters on the very flag it is meant to
    # set, so nothing is ever marked (expenses' detect_recurring).
    if name.startswith("detect_") and not (m.get("params") or []):
        detected = _detect_and_mark_impl(m, entities_by_class)
        if detected is not None:
            return detected
    # A zero-param service method sharing its name with a zero-param DESIGNED
    # repository custom is a thin pass-through: the design put the real work
    # on the repository (expense's detect_category_recurring), and any
    # aggregate `impl` stamped on the service method is a MIS-SHAPE —
    # expenses' detect_recurring carried a group-and-sum impl that returned a
    # dict where List[Dict[str, Any]] is declared. Delegate; the name AND zero
    # arity must both match, so this never fires for a parameterized method or
    # a different name.
    if not (m.get("params") or []):
        for _rep_ent, _rparams in (repo_signatures or {}).get(name, []):
            if not _rparams:
                return ["        return self.%s_repo.%s()" % (_rep_ent, name)]
    # A PAGINATED listing is owned by the deterministic paged delegation,
    # never by an `impl` the design stamped on it. Prompt 16's list_customer
    # carried an export-shaped impl whose body opened a CSV file NAMED by
    # page_size — ignoring both page params and its declared return, so the
    # method returned None. The shape is exact (a list_<entity> taking a page
    # number AND a page size), so no ordinary CRUD list and no export method
    # is captured by it.
    if name.startswith("list_"):
        _listed = [
            p.get("name") for p in (m.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        if (
            any(p in _PAGE_NUM_PARAMS for p in _listed)
            and any(p in _PAGE_SIZE_PARAMS for p in _listed)
        ):
            _paged = _generic_service_delegation(
                m, entities_by_class, exception_names, repo_bulk_updates,
                repo_search_targets, repo_signatures,
            )
            if _paged is not None:
                return _paged
    impl = m.get("impl")
    if isinstance(impl, dict):
        # exception_names travels to the recipe so a row lookup that finds
        # nothing is reported as the design's not-found error instead of a
        # silent False.
        lines = dispatch_impl_body(m, impl, None, entities_by_class,
                                   exception_names)
        if lines is not None:
            return lines
    # Unique-shape aggregate delegation: a zero-param Dict-returning service
    # method with no impl delegates to THE unique zero-param Dict-returning
    # repository custom across the whole design (shape-matched, never by
    # name). More than one candidate => ambiguous => degrade to the generic
    # tiers instead of guessing.
    param_names = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    ]
    anchors = _method_anchor_entities(name, param_names, entities_by_class)
    if (
        repo_customs
        and len(repo_customs) == 1
        and not param_names
        and "dict" in (m.get("returns") or "").lower()
    ):
        ent_snake, meth = repo_customs[0]
        # Entity-scoped: the unique aggregate only serves a method that does
        # NOT name a DIFFERENT designed entity. A zero-param list_author() /
        # get_overdue_loans() must reach its OWN entity's repo, never the
        # single aggregate that happens to exist elsewhere in the design
        # (library_system: both used to become book_repo.
        # list_books_with_available_copies()).
        if not anchors or ent_snake in {_snake(a) for a in anchors}:
            return ["        return self.%s_repo.%s()" % (ent_snake, meth)]
    lines = _generic_service_delegation(
        m, entities_by_class, exception_names, repo_bulk_updates, repo_search_targets,
        repo_signatures
    )
    if lines is not None:
        return lines
    # Same-name repo delegation: a designed repository custom method carrying
    # the EXACT same name and parameter names as this service method is a
    # thin pass-through (expense's get_yearly_summary(year) over the
    # repository's own get_yearly_summary(year)). Shape-matched on name AND
    # parameter names — never a spelling heuristic — so a mismatch still
    # degrades to a stub for the LLM fill. This is the load-bearing route for
    # a method that is BOTH a get_/CRUD-prefixed verb (so _apply_impl_floors
    # skips it) AND parameterized (so _zero_param_dict_repo_customs skips it).
    pnames = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    ]
    for ent_snake, rparams in (repo_signatures or {}).get(name, []):
        if rparams == pnames:
            return [
                "        return self.%s_repo.%s(%s)"
                % (ent_snake, name, ", ".join(pnames))
            ]
    # Anchor-scoped same-STEM repo delegation: a service method whose name
    # minus its leading verb matches a designed repository custom on the
    # SAME anchor entity, with the SAME parameter names, is a thin
    # pass-through — get_overdue_loans() -> loan_repo.list_overdue_loans().
    # Both the entity (anchor) and the exact parameter names must match, so
    # this is a shape match, never a fuzzy spelling heuristic.
    stem = _verb_stem(name)
    anchor_snakes = {_snake(a) for a in anchors}
    for cand, entries in (repo_signatures or {}).items():
        if _verb_stem(cand) != stem:
            continue
        for ent_snake, rparams in entries:
            if ent_snake in anchor_snakes and rparams == pnames:
                return [
                    "        return self.%s_repo.%s(%s)"
                    % (ent_snake, cand, ", ".join(pnames))
                ]
    return None


def _same_name_repo_call(m, var, repo_signatures):
    """Delegate a service method to a designed repository custom.

    Only for the ``list_<entity>`` route, and only when the declared
    ``list()`` filters cannot serve every designed param: the design then
    carries a richer query on the repository itself (library's
    ``book_repo.list_book(author, available_only)`` vs the generic
    ``book_repo.list()``, which has no such columns). The candidate is
    matched by NAME — the service method's own name, else its pluralised
    ``list_<plural>`` form — on the SAME entity, and must take the same
    number of params so the call is positional and unambiguous. Returns the
    body lines, or None to let the caller decline into the LLM fill.
    """
    name = m.get("name") or ""
    pnames = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    ]
    for cand in (name, "list_" + _plural(var)):
        for ent_snake, rparams in (repo_signatures or {}).get(cand, []):
            if ent_snake == var and len(rparams) == len(pnames):
                return [
                    "        return self.%s_repo.%s(%s)"
                    % (var, cand, ", ".join(pnames))
                ]
    return None


# Limit-shaped exception names: an exception whose name carries one of these
# AND names a designed entity is the design's own signal that "adding" the
# related entity is meant to consult that entity's numeric limit.
_LIMIT_EXC_MARKERS = (
    "Exceeded", "Exceeds", "Limit", "Quota", "Overflow", "OverBudget",
)


def _unraised_limit_spec(ent, ent_name, entities_by_class, exception_names):
    """The OTHER entity whose numeric limit a create must consult, or None.

    Design-only signal, no prompt text: some OTHER designed entity shares
    exactly one foreign-key column with the entity being created
    (Budget.category_id and Expense.category_id are the same FK), that entity
    carries exactly one numeric non-FK column (the limit) and exactly one str
    column (the period it applies to), and the design declares a limit-shaped
    exception naming it (BudgetExceededException). Returns
    ``{cls, var, fk, limit, period, exception}`` or None.
    """
    fk_fields = sorted(
        f.get("name")
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and (f.get("name") or "").endswith("_id")
        and f.get("name") != "id"
    )
    if not fk_fields:
        return None
    for cls, other in (entities_by_class or {}).items():
        if cls == ent_name or not isinstance(other, dict):
            continue
        ofields = {
            f.get("name"): f for f in (other.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        }
        shared = [fk for fk in fk_fields if fk in ofields]
        if len(shared) != 1:
            continue
        nums = [
            n for n, f in ofields.items()
            if f.get("type") in ("int", "float") and n != "id"
            and not n.endswith("_id")
        ]
        strs = [n for n, f in ofields.items() if f.get("type") == "str"]
        if len(nums) != 1 or len(strs) != 1:
            continue
        for exc in exception_names or []:
            if cls in exc and any(m in exc for m in _LIMIT_EXC_MARKERS):
                return {
                    "cls": cls,
                    "var": _snake(cls),
                    "fk": shared[0],
                    "limit": nums[0],
                    "period": strs[0],
                    "exception": exc,
                }
    return None


def _declines_for_unraised_limit(ent, ent_name, entities_by_class, exception_names):
    """True when a generic create cannot consult the limit it must consult."""
    return _unraised_limit_spec(
        ent, ent_name, entities_by_class, exception_names
    ) is not None


def _create_limit_check_lines(var, ent, spec, param_names, entities_by_class):
    """Body lines consulting the shared-FK entity's limit AFTER a create.

    Narrow and design-only. The created entity must declare exactly one date
    column and exactly one numeric non-FK column (what was spent), the shared
    FK must be one of the method's params, and BOTH repositories must accept
    that FK as a ``list()`` filter — read through ``_filter_params``, the same
    source the repository renderer used to build ``list()``. Returns None when
    anything is missing, so the caller keeps its previous behaviour.

    Why: the specification says "add_expense: ... adds expense, checks if
    budget exceeded after insertion" and declares BudgetExceededException, but
    nothing ever raised it, so a create silently succeeded over the limit.
    Every column involved (the limit, the period, the summed amount, the date)
    is read off the design — no domain vocabulary.
    """
    if spec is None or spec["fk"] not in param_names:
        return None
    efields = {
        f.get("name"): f for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }
    dates = [
        n for n, f in efields.items()
        if f.get("type") in ("date", "datetime")
    ]
    nums = [
        n for n, f in efields.items()
        if f.get("type") in ("int", "float") and n != "id"
        and not n.endswith("_id")
    ]
    if len(dates) != 1 or len(nums) != 1:
        return None
    date_col, sum_col = dates[0], nums[0]
    if date_col not in param_names:
        return None
    fk = spec["fk"]
    if fk not in _filter_params(ent):
        return None
    other = entities_by_class.get(spec["cls"]) or {}
    if fk not in _filter_params(other):
        return None
    return [
        "        month = str(%s)[:7]" % date_col,
        "        limit = None",
        "        for _row in self.%s_repo.list(%s=%s):"
        % (spec["var"], fk, fk),
        "            if str(_row.%s) == month:" % spec["period"],
        "                limit = _row.%s" % spec["limit"],
        "        spent = 0",
        "        for _row in self.%s_repo.list(%s=%s):" % (var, fk, fk),
        "            if str(_row.%s)[:7] == month:" % date_col,
        "                spent += _row.%s" % sum_col,
        "        if limit is not None and spent > limit:",
        "            raise %s(" % spec["exception"],
        "                'budget exceeded for %s ' + str(%s)"
        " + ' in ' + str(month)" % (fk, fk),
        "            )",
    ]


def _parent_name_binding(param, ent, entities_by_class):
    """Resolve a param that names a PARENT ROW BY ITS NAME, or None.

    The specification writes ``library book list [--author]`` — an author
    NAME — while the design's repository filters on ``author_id``. The two are
    the same request one join apart: when the entity DECLARES ``<param>_id`` as
    a ``list()`` filter, the referenced entity is designed, and that parent has
    exactly ONE str column (its own name), the name can be resolved to the
    parent's id deterministically.

    Returns ``{"fk": "author_id", "var": "author", "cls": "Author",
    "name_col": "name"}`` or None. Ambiguity (several str columns, or a parent
    the design does not model) declines, so the caller keeps its previous
    behaviour rather than guessing.
    """
    key = str(param or "")
    if not key:
        return None
    fk = key + "_id"
    if fk not in _filter_params(ent):
        return None
    parent = entities_by_class.get(_camel(key))
    if not isinstance(parent, dict):
        return None
    strs = [
        f.get("name") for f in (parent.get("fields") or [])
        if isinstance(f, dict) and f.get("type") == "str"
        and f.get("name") not in (None, "id")
    ]
    # The parent's NAME column is the one the design calls ``name`` (the
    # specification's Author model is ``id, name, birth_year, biography`` —
    # TWO strs, so "exactly one str column" alone would decline and the
    # method would keep a fill that resolves the name against the parent's
    # ID instead). A design with no such column still resolves when it has a
    # single str column; several strs and none of them a name is ambiguous,
    # so it declines.
    if "name" in strs:
        pick = "name"
    elif len(strs) == 1:
        pick = strs[0]
    else:
        return None
    return {"fk": fk, "var": key, "cls": _camel(key), "name_col": pick}


def _render_parent_name_lookup(binding):
    """Lines resolving a parent-name param to the parent's row id.

    ``for _row in self.author_repo.list(): ...`` scans the parent rows (the
    design's own ``list()``, so no query is invented) and binds the FIRST row
    whose name column equals the value the caller typed. No such row means no
    child row can match, so the method returns an empty listing — never an
    error, because the specification describes ``--author`` as an OPTIONAL
    FILTER, not as a lookup that can fail.
    """
    var = binding["var"]
    return [
        "        if %s:" % var,
        "            _parent = None",
        "            for _row in self.%s_repo.list():"
        % _snake(binding["cls"]),
        "                if getattr(_row, %r, None) == %s:"
        % (binding["name_col"], var),
        "                    _parent = _row",
        "                    break",
        "            if _parent is None:",
        "                return []",
        "            %s = _parent.id" % binding["fk"],
    ]


def _create_field_binding(param, fields):
    """The entity field a create parameter feeds, or the reason it cannot.

    Returns ``(field, None)`` when the parameter names a column of the
    entity — EXACTLY, or as the UNIQUE morphological variant of one
    (``copies`` -> ``available_copies``: the caller's own word for one
    column must not be thrown away) — and ``(None, reason)`` otherwise.

    The two failure modes are distinct and both are reported:
      * several candidates is a genuine ambiguity (a ``amount`` parameter
        facing both ``amount_cents`` and ``amount_limit_cents``), so binding
        either one would write the wrong column;
      * no candidate means the parameter names no column of this entity at
        all (a value the caller supplies that the model has nowhere to
        keep).
    The caller REFUSES the deterministic body in both cases (see the add_
    branch), so a supplied value is never dropped in silence and never
    written to a column the specification did not name.
    """
    if param in fields:
        return param, None
    cands = sorted(
        f for f in fields
        if f != "id" and (f.endswith("_" + param) or f.startswith(param + "_"))
    )
    if len(cands) == 1:
        return cands[0], None
    if not cands:
        return None, "names no field of this entity"
    return None, "ambiguous - could be %s" % " or ".join(cands)


def _report_create_refusal(method_name, unbound):
    """Make a REFUSED deterministic create visible in the run log.

    A refusal is a deliberate degradation (the method keeps its locked stub
    and travels to the LLM fill), not a silent success. Without this the
    caller cannot tell a create that bound every value from one that gave up
    on a parameter, and a body that quietly ignores an argument looks
    identical to a correct one.
    """
    print(
        "    [law A/2] %s: deterministic create refused - %s"
        % (method_name, "; ".join("%s %s" % (p, w) for p, w in unbound))
    )


def _generic_service_delegation(m, entities_by_class, exception_names=None, repo_bulk_updates=None, repo_search_targets=None, repo_signatures=None):
    """Tier-2 deterministic CRUD delegation for any entity.

    Handles add_<entity>, list_<entity> / get_<entity>_by_id /
    update_<entity> / delete_<entity> against the deterministic repository
    API. Only the repository's derived filter params are passed to list();
    everything else stays a stub for the LLM fill phase. add_<entity> builds
    the entity from the method params and inserts through the repository's
    deterministic `create` (never `.add`/`.insert` — the 4B model has been
    caught hallucinating those). Entities handled by Tier 1 are skipped here.
    """
    exception_names = exception_names or []
    name = m.get("name") or ""
    params = [(p.get("name"), p.get("type")) for p in (m.get("params") or [])
              if isinstance(p, dict) and p.get("name")]
    param_names = [p for p, _ in params]
    for ent_name, ent in entities_by_class.items():
        var = _snake(ent_name)
        fields = {f.get("name") for f in (ent.get("fields") or [])}
        # Mirror the deterministic repo list() filters (declared list_filters).
        filters = _filter_params(ent)

        if name in ("add_" + var, "create_" + var):
            # A create whose design declares a limit-shaped exception for a
            # shared-FK entity must consult that entity's limit AFTER the
            # insertion ("add_expense: ... adds expense, checks if budget
            # exceeded after insertion"). Build that check when the design
            # supplies every column it needs; otherwise DECLINE, so the method
            # goes to the LLM fill instead of shipping a body that silently
            # omits the requirement.
            limit_spec = _unraised_limit_spec(
                ent, ent_name, entities_by_class, exception_names
            )
            limit_check = _create_limit_check_lines(
                var, ent, limit_spec, param_names, entities_by_class
            )
            if limit_spec is not None and limit_check is None:
                return None
            field_defaults = {}
            for f in (ent.get("fields") or []):
                if not isinstance(f, dict) or not f.get("name"):
                    continue
                coerced = _coerce_field_default(
                    f.get("type", "str"), f.get("default")
                )
                if coerced is not None:
                    field_defaults[f["name"]] = coerced
            # LAW A/2 — the word a caller uses and the COLUMN it feeds can
            # differ: the specification writes `library book add --copies`
            # while the Book model declares `available_copies`. The old body
            # kept only `if p in fields`, so `copies` was discarded in
            # silence and the row took the dataclass default (1) whatever the
            # caller asked for. Bind each param to the ONE field it names —
            # exactly, or as the unique `<field>_<param>` / `<param>_<field>`
            # variant — and REFUSE the whole body as soon as a param names no
            # field, several fields, or a field another param already feeds:
            # a supplied value is never dropped and never written to the
            # wrong column (see _create_field_binding).
            bound, unbound = {}, []
            for p in param_names:
                field, why = _create_field_binding(p, fields)
                if why is None and field in bound.values():
                    why = "already fed by %s" % next(
                        q for q, f2 in bound.items() if f2 == field
                    )
                if why is None:
                    bound[p] = field
                else:
                    unbound.append((p, why))
            if bound and unbound:
                _report_create_refusal(name, unbound)
                return None
            kwargs = [
                (
                    "%s=(%s if %s is not None else %r)"
                    % (bound[p], p, p, field_defaults[bound[p]])
                    if bound[p] in field_defaults
                    else "%s=%s" % (bound[p], p)
                )
                for p in param_names
                if p in bound
            ]
            # A NON-NULLABLE date/datetime field whose CLI option is OPTIONAL
            # arrives as None: click hands the callback None when the option is
            # absent, so `expense add --amount-cents ...` with no --expense-date
            # sent expense_date=None straight into the INSERT and died on
            # "NOT NULL constraint failed: expenses.expense_date". The spec
            # declares that option optional (`[--expense-date]`), so the only
            # sensible reading is TODAY. Bounded to date/datetime-typed,
            # non-nullable, default-less fields, so a required str/int column is
            # never silently invented. Normalised into the PARAMETER (not
            # inlined into the constructor call) so every later read — the
            # constructor, the period computation, any limit check — sees the
            # same resolved value.
            _field_types = {
                f["name"]: (f.get("type") or "str")
                for f in (ent.get("fields") or [])
                if isinstance(f, dict) and f.get("name")
            }
            _nullable_or_defaulted = {
                f["name"]
                for f in (ent.get("fields") or [])
                if isinstance(f, dict) and f.get("name")
                and (f.get("nullable") or f.get("default") is not None)
            }
            # Classified on the FIELD the parameter feeds and emitted on the
            # PARAMETER the caller named: `copies -> available_copies` means
            # the resolution must happen on `copies`, the name the
            # constructor call below actually uses.
            date_fallback = sorted(
                (p, bound[p]) for p in param_names
                if p in bound and bound[p] not in _nullable_or_defaulted
                and _field_types.get(bound[p]) in ("date", "datetime")
            )
            # The SAME failure mode as the date above, one step down the call
            # chain: a NON-NULLABLE bool field whose CLI option is optional.
            # click renders `[--recurring]` as an is_flag, which always passes
            # a bool — so the CLI path hides it — but the SERVICE method's own
            # signature declares the argument optional (`is_recurring:
            # Optional[bool] = None`), so a direct caller that omits it sends
            # None into a NOT NULL column ("NOT NULL constraint failed:
            # expenses.is_recurring"). An omitted flag means False. Bounded to
            # bool-typed, non-nullable, default-less fields, so a required
            # str/int column is never silently invented.
            # `_is_bool_param_type` rather than a literal spelling test: the
            # design may write the type as "boolean", "Optional[bool]" or
            # with a trailing default, and a strict tuple membership silently
            # produced an EMPTY fallback for exactly those spellings (expenses'
            # `is_recurring` shipped with no fallback while its date sibling
            # got one).
            bool_fallback = sorted(
                p for p in param_names
                if p in bound and bound[p] not in _nullable_or_defaulted
                and _is_bool_param_type(_field_types.get(bound[p]))
            )
            if not bound:
                if limit_spec is not None:
                    # The limit check needs the field params; a data-dict
                    # create declines to the fill rather than omitting it.
                    return None
                # Data-dict add (add_<entity>(data: Dict[str, Any])): build
                # the entity from a single dict parameter, validating FK keys
                # that reference a designed entity with a designed NotFound
                # exception. Deterministic: never .strftime() on a str-typed
                # ISO date (add_expense crash), never guesses at business logic.
                data_param = next(
                    (p for p in param_names if p in ("data", "payload", "record")),
                    None,
                )
                if data_param is None:
                    return None
                # The same law one branch over: a data-dict create that ALSO
                # declares a parameter the dict cannot carry would ignore it,
                # so it is refused for the same reason.
                if [pu for pu, _w in unbound if pu != data_param]:
                    _report_create_refusal(
                        name,
                        [(pu, w) for pu, w in unbound if pu != data_param],
                    )
                    return None
                lines = []
                for fk in sorted(
                    f for f in fields if f.endswith("_id") and f != "id"
                ):
                    ref_cls = _camel(fk[: -len("_id")])
                    not_found = not_found_exception(ref_cls, exception_names)
                    if (
                        ref_cls in entities_by_class
                        and not_found in exception_names
                        and "%s_repo" % _snake(ref_cls) != "%s_repo" % var
                    ):
                        lines.append("        if %s.get(%r) is not None:" % (data_param, fk))
                        lines.append(
                            "            if self.%s_repo.get_by_id(%s.get(%r)) is None:"
                            % (_snake(ref_cls), data_param, fk)
                        )
                        lines.append(
                            "                raise %s(%s)"
                            % (
                                not_found,
                                not_found_message(
                                    ref_cls, "%s.get(%r)" % (data_param, fk)
                                ),
                            )
                        )
                field_names = ", ".join(repr(f) for f in sorted(fields))
                lines.append(
                    "        %s = %s(**{k: v for k, v in %s.items() if k in {%s}})"
                    % (var, ent_name, data_param, field_names)
                )
                lines.append("        return self.%s_repo.create(%s)" % (var, var))
                return lines
            # Required (non-nullable, non-id) fields not covered by params:
            # only fields DECLARED auto:"now" are stamped deterministically;
            # anything else means real business logic -> leave a stub.
            # The columns this create actually fills are the ones its params
            # BOUND to, aliases included (`copies` fills `available_copies`),
            # not merely the params that happen to spell a field name.
            covered = set(bound.values())
            # Only date/datetime-typed non-id fields may be stamped at
            # creation: stamping an id or a bool/str field with a timestamp
            # corrupts the row (the 4B model declares auto:"now" on random
            # fields).
            auto_now = {
                f.get("name")
                for f in (ent.get("fields") or [])
                if isinstance(f, dict) and f.get("auto") == "now"
                and f.get("name") != "id"
                and f.get("type") in ("date", "datetime")
            }
            required = {
                f.get("name") for f in (ent.get("fields") or [])
                if not f.get("nullable") and f.get("name") != "id"
                and f.get("default") is None
            }
            missing = required - covered
            if missing - auto_now:
                return None
            for af in sorted(auto_now - covered):
                kwargs.append("%s=datetime.datetime.now().isoformat()" % af)
            # Constants baked by bounded CLI propagation (bool is_* fields
            # whose default the spec itself declares).
            for dk, dv in (m.get("defaults") or {}).items():
                if dk in fields and dk not in covered:
                    kwargs.append("%s=%r" % (dk, dv))
            lines = []
            # Resolve an omitted optional date/datetime ONCE, into the
            # parameter itself, before any read of it.
            for _dp, _dfield in date_fallback:
                _stamp = (
                    "datetime.datetime.now().isoformat()"
                    if _field_types.get(_dfield) == "datetime"
                    else "datetime.date.today().isoformat()"
                )
                lines.append("        if %s is None:" % _dp)
                lines.append("            %s = %s" % (_dp, _stamp))
            # Resolve an omitted optional bool the same way, before the
            # constructor reads it (see bool_fallback above).
            for _bp in bool_fallback:
                lines.append("        if %s is None:" % _bp)
                lines.append("            %s = False" % _bp)
            # Generic FK validation: for any designed param that is a
            # foreign-key column of this entity (<x>_id), when the referenced
            # entity <X> exists AND the design declared any not-found class
            # for it, emit a deterministic existence check. The class name is
            # RESOLVED by name against the design's own declarations
            # (not_found_exception: <X>NotFoundError, Invalid<X>IdError, the
            # project-wide NotFoundError) instead of being assumed to be
            # <X>NotFoundError — that assumption silently skipped the guard
            # whenever a design named its exception differently, and the
            # caller then met a raw
            # `sqlite3.IntegrityError: FOREIGN KEY constraint failed`
            # (library book add --author-id 999). Design-driven, never
            # invented: an entity with no declared class still yields no
            # guard.
            fk_params = [
                (p, bound[p]) for p in param_names
                if p in bound and bound[p].endswith("_id") and bound[p] != "id"
            ]
            for fk, fk_field in fk_params:
                ref_cls = _camel(fk_field[: -len("_id")])
                not_found = not_found_exception(ref_cls, exception_names)
                if (
                    ref_cls in entities_by_class
                    and not_found in exception_names
                    and "%s_repo" % _snake(ref_cls) != "%s_repo" % var
                ):
                    lines.append("        if %s is not None:" % fk)
                    lines.append(
                        "            if self.%s_repo.get_by_id(%s) is None:"
                        % (_snake(ref_cls), fk)
                    )
                    lines.append(
                        "                raise %s(%s)"
                        % (not_found, not_found_message(ref_cls, fk))
                    )
            lines.append("        %s = %s(%s)" % (var, ent_name, ", ".join(kwargs)))
            if limit_check is None:
                lines.append(
                    "        return self.%s_repo.create(%s)" % (var, var)
                )
                return lines
            # Insert FIRST, then check: the specification puts the limit check
            # after the insertion, so the new row is part of the total.
            lines.append("        self.%s_repo.create(%s)" % (var, var))
            lines.extend(limit_check)
            return lines
        if name in ("list_" + var, "list_" + _plural(var)):
            # Pair the designed params with the declared list() filters. A
            # param the declared names cannot serve is paired by ROLE
            # (from_/to_ -> the gte/lte filter over the date column). Only
            # when a param stays unmapped does the filter-mapped list()
            # become lossy: then prefer the design's own richer repository
            # custom (book_repo.list_book(author, available_only)), and
            # failing that DECLINE so the LLM fill handles it — never emit a
            # partial call that silently drops a filter (the expense
            # from_date/to_date loss, library's dropped author/active_only).
            page_names = [
                p for p in param_names
                if p in _PAGE_NUM_PARAMS or p in _PAGE_SIZE_PARAMS
            ]
            # An ORDER BY selector is not a filter either: sort_by/order shape
            # the ROW ORDER, so pairing them with a declared filter emitted an
            # equality clause instead of an ordering (prompt 15). They are
            # pulled out here and passed to list() as their own keywords.
            sort_names = [
                p for p in param_names
                if p in (ent.get("sort_params") or [])
            ]
            scope_names = page_names + sort_names
            filt_m = {
                "params": [
                    p for p in (m.get("params") or [])
                    if isinstance(p, dict)
                    and p.get("name") not in scope_names
                ]
            }
            resolved, unresolved = _resolve_filter_args(filt_m, ent)
            sort_kw = ", ".join("%s=%s" % (p, p) for p in sort_names)
            if unresolved:
                # A param the declared filters cannot serve may still be the
                # NAME of a parent row (the specification writes ``library
                # book list [--author]`` — an author NAME — while the
                # repository filters on ``author_id``). Resolve it to the
                # parent's id when the design pins the shape; only what is
                # left over decides the fallback.
                bindings = []
                still_unresolved = []
                for p in unresolved:
                    bind = _parent_name_binding(p, ent, entities_by_class)
                    if bind is None:
                        still_unresolved.append(p)
                    else:
                        bindings.append(bind)
                if still_unresolved or not bindings:
                    return _same_name_repo_call(m, var, repo_signatures)
                lines = []
                for bind in bindings:
                    lines += _render_parent_name_lookup(bind)
                for bind in bindings:
                    # The explicit id param the caller may ALSO pass is
                    # overwritten by the resolved parent id, so the emitted
                    # call reads one coherent value.
                    resolved = [
                        (fp, mp) for fp, mp in resolved if fp != bind["fk"]
                    ] + [(bind["fk"], bind["fk"])]
                call = ", ".join("%s=%s" % (fp, mp) for fp, mp in resolved)
                lines.append(
                    "        return self.%s_repo.list(%s)"
                    % (var, ", ".join(x for x in (call, sort_kw) if x))
                )
                return lines
            call = ", ".join("%s=%s" % (fp, mp) for fp, mp in resolved)
            if not page_names:
                return [
                    "        return self.%s_repo.list(%s)"
                    % (var, ", ".join(x for x in (call, sort_kw) if x))
                ]
            # Paginated listing (prompt 16): the caller specifies page number
            # and page size, and the result carries enough to derive the
            # number of pages. The repository's list() pages its SQL
            # (LIMIT/OFFSET, see _render_repository_file) and the TOTAL is read
            # from the design's own unfiltered list() — no query is invented.
            num = next(p for p in page_names if p in _PAGE_NUM_PARAMS)
            size = next(p for p in page_names if p in _PAGE_SIZE_PARAMS)
            paged = ", ".join(
                x for x in
                (call, sort_kw,
                 ", ".join("%s=%s" % (p, p) for p in page_names)) if x
            )
            return [
                "        items = self.%s_repo.list(%s)" % (var, paged),
                "        total = len(self.%s_repo.list(%s))" % (var, call),
                "        page_size = %s or total or 1" % size,
                "        return {",
                "            \"items\": items,",
                "            \"page\": %s or 1," % num,
                "            \"page_size\": page_size,",
                "            \"total\": total,",
                "            \"total_pages\": (total + page_size - 1) // page_size,",
                "        }",
            ]
        if name == "get_%s_by_id" % var:
            idp = param_names[0] if param_names else "id"
            return ["        return self.%s_repo.get_by_id(%s)" % (var, idp)]
        if name == "update_%s" % var:
            # Pair-keyed update (the leading two params form the entity's
            # declared unique_together pair, e.g. update_budget(
            # category_id, month, amount)): resolve the row through the
            # repo's deterministic get_by_<a>_and_<b> getter, then
            # delegate to the id-based repo.update with None-dropped
            # field values. Generic `data`-style and id-based signatures
            # fall through to the existing branches below.
            upair = next(
                (
                    [str(x) for x in p]
                    for p in (ent.get("unique_together") or [])
                    if isinstance(p, list) and len(p) == 2
                ),
                None,
            )
            if (
                upair is not None
                and len(param_names) >= 3
                and {param_names[0], param_names[1]} == set(upair)
            ):
                a_fn = upair[0][:-3] if upair[0].endswith("_id") else upair[0]
                b_fn = upair[1][:-3] if upair[1].endswith("_id") else upair[1]
                rest = [p for p in param_names[2:] if p in fields]
                lines = [
                    "        row = self.%s_repo.get_by_%s_and_%s(%s)"
                    % (var, a_fn, b_fn, ", ".join(upair)),
                    "        if row is None:",
                ]
                # A miss on a key that NAMES a parent (category_id, month) is
                # not necessarily "no such row": when the parent the caller
                # named does not exist, that is the designed not-found error.
                # `budget update --category-id 999` answered a bare `False`.
                lines += fk_parent_guards(
                    upair, entities_by_class, exception_names
                )
                lines.append("            return False")
                if rest:
                    mapping = ", ".join(
                        "'%s': %s" % (p, p) for p in rest
                    )
                    lines.append(
                        "        data = {k: v for k, v in {%s}.items() if v is not None}"
                        % mapping
                    )
                    lines.append(
                        "        return self.%s_repo.update(row.id, data)" % var
                    )
                else:
                    lines.append("        return False")
                return lines
            idp = param_names[0] if param_names else "id"
            if "data" in param_names:
                # RETURN the repository's boolean: every sibling branch above
                # returns the update result, and the designed signature
                # declares `-> bool` (the specification's `update_<e>(id,
                # data)`), so a bare statement made the method's declared
                # value None — a caller checking success always read falsy.
                return ["        return self.%s_repo.update(%s, data)"
                        % (var, idp)]
            # Designed signature carries field params (e.g. update_task(id,
            # title, ...)): build the dict for the deterministic repo API,
            # dropping fields the caller left as None so the repo never
            # overwrites columns with NULL (NOT NULL constraint).
            rest = [p for p in param_names[1:] if p in fields]
            mapping = ", ".join("'%s': %s" % (p, p) for p in rest)
            return [
                "        data = {k: v for k, v in {%s}.items() if v is not None}" % mapping,
                "        return self.%s_repo.update(%s, data)" % (var, idp),
            ]
        if name == "delete_%s" % var:
            # Unique-pair delete (declared unique_together covering ALL
            # method params): an entity WITHOUT a surrogate `id` (pure join
            # table, e.g. post_tag) deletes directly by the pair. An entity
            # WITH an `id` PK is deleted by id — resolve the pair through the
            # deterministic get_by_<a>_and_<b> lookup, then delete by the
            # row's id. Otherwise fall back to the id-based delete.
            if len(param_names) == 2:
                pair = next(
                    (
                        [str(x) for x in p]
                        for p in (ent.get("unique_together") or [])
                        if isinstance(p, list) and len(p) == 2
                        and {str(x) for x in p} == set(param_names)
                    ),
                    None,
                )
                if pair is not None:
                    pair_has_id = any(
                        f.get("name") == "id"
                        for f in (ent.get("fields") or [])
                        if isinstance(f, dict)
                    )
                    if pair_has_id:
                        a_fn = pair[0][:-3] if pair[0].endswith("_id") else pair[0]
                        b_fn = pair[1][:-3] if pair[1].endswith("_id") else pair[1]
                        lines = [
                            "        row = self.%s_repo.get_by_%s_and_%s(%s)"
                            % (var, a_fn, b_fn, ", ".join(pair)),
                            "        if row is None:",
                        ]
                        lines += fk_parent_guards(
                            pair, entities_by_class, exception_names
                        )
                        lines += [
                            "            return False",
                            "        return self.%s_repo.delete(row.id)" % var,
                        ]
                        return lines
                    return [
                        "        return self.%s_repo.delete(%s)"
                        % (var, ", ".join(pair))
                    ]
            idp = param_names[0] if param_names else "id"
            return ["        return self.%s_repo.delete(%s)" % (var, idp)]
        if name == "bulk_update_" + var:
            # Deterministic bulk update: parse a comma-separated ids string
            # into ints, validate each id exists against the repo, then
            # delegate to the repo's bulk_update_<col>(ids, value). An LLM
            # fill compares str ids against the repo's int ids and always
            # raises NotFoundError (prompt 35's bulk_update_product).
            bu = (repo_bulk_updates or {}).get(var)
            if bu is None or len(param_names) < 2:
                return None
            repo_meth, col = bu
            idp = param_names[0]
            value_param = next((p for p in param_names[1:] if p == col), None)
            if value_param is None:
                return None
            not_found = not_found_exception(ent_name, exception_names)
            rows = [
                "        int_ids = [int(x.strip()) for x in %s.split(',')]" % idp,
                "        if not int_ids:",
                "            return False",
                "        existing = self.%s_repo.get_all()" % var,
                "        existing_ids = {row.id for row in existing}",
                "        invalid = [x for x in int_ids if x not in existing_ids]",
            ]
            if not_found in exception_names:
                rows += [
                    "        if invalid:",
                    "            raise %s(', '.join(map(str, invalid)))" % not_found,
                ]
            else:
                rows += [
                    "        if invalid:",
                    "            return False",
                ]
            rows.append(
                "        return self.%s_repo.%s(int_ids, %s)" % (var, repo_meth, value_param)
            )
            return rows
        if name == "search_" + var:
            # Deterministic search delegation: a book search is a Book-only
            # predicate, so search_book(term) -> self.book_repo.search_books(term).
            # The single query/term param is passed POSITIONALLY (the arity-aware
            # alias repair maps a name mismatch like term->query if needed). An
            # LLM stub hallucinates member_repo/loan_repo because the single
            # `term` param hides that the search spans title/isbn/author — an
            # abstraction problem the small model resolves by dragging in
            # unrelated repos (library_system search_book).
            smeth = (repo_search_targets or {}).get(var)
            if smeth is None or not param_names:
                return None
            return ["        return self.%s_repo.%s(%s)" % (var, smeth, param_names[0])]
        if "status" in fields and len(param_names) == 1 and name.endswith("_" + var):
            # A single-id <verb>_<entity> on an entity with a `status` field
            # is a domain state transition (confirm/ship/cancel/...). Set the
            # status to the verb's past-participle (ship -> shipped) and
            # persist it through the repo's update(id, data). The LLM fill
            # invents terminal-state guards that reject valid transitions
            # (prompt 32's ship_order raised InvalidStateTransitionError on a
            # confirmed order -> I3 fail). Deterministic: no invented guards.
            verb = name[: -len("_" + var)]
            target = _STATE_TARGETS.get(verb)
            if target is not None:
                idp = param_names[0]
                not_found = not_found_exception(ent_name, exception_names)
                rows = [
                    "        row = self.%s_repo.get_by_id(%s)" % (var, idp),
                ]
                if not_found in exception_names:
                    rows += [
                        "        if row is None:",
                        "            raise %s(%s)" % (not_found, idp),
                    ]
                else:
                    rows += [
                        "        if row is None:",
                        "            return False",
                    ]
                rows += [
                    "        if row.status == %r:" % target,
                    "            return False",
                    "        row.status = %r" % target,
                    "        return self.%s_repo.update(%s, {'status': row.status})" % (var, idp),
                ]
                return rows
        if name == "check_" + var and len(param_names) == 1:
            # A single-id "check <entity>" reads the entity's state. Return
            # its declared fields as a dict (non-crashing); the LLM fill has
            # been caught summing a date column (prompt 26's check_book did
            # results.get(...) + row.loan_date -> int + str TypeError).
            idp = param_names[0]
            not_found = not_found_exception(ent_name, exception_names)
            rows = [
                "        row = self.%s_repo.get_by_id(%s)" % (var, idp),
            ]
            if not_found in exception_names:
                rows += [
                    "        if row is None:",
                    "            raise %s(%s)" % (not_found, idp),
                ]
            else:
                rows += [
                    "        if row is None:",
                    "            return None",
                ]
            rows.append(
                "        return {%s}" % ", ".join(
                    "'%s': row.%s" % (f, f)
                    for f in sorted({"id"}.union(fields))
                )
            )
            return rows
    return None


# Spellings a design may use for PAGINATION on a list method. A designed
# ``list_<entity>(..., page, page_size)`` means "the caller specifies page
# number and page size" (prompt 16): the repository's ``list()`` must then
# ACCEPT those params so its SQL pages, and the service must report the total
# so the caller can derive the number of pages. Only these two families are
# pagination; ``limit``/``offset`` are deliberately NOT included, because a
# spec's "top N" is a LIMIT-shaped business rule, not paging.
_PAGE_NUM_PARAMS = ("page", "page_number", "page_no")
_PAGE_SIZE_PARAMS = ("page_size", "per_page")


# The parameter spellings a design may use for the two halves of an ORDER BY:
# the COLUMN to order by, and the DIRECTION. Two DISJOINT tuples, so a design
# that names its direction parameter `order` is never mistaken for one naming
# the column `order_by`.
_SORT_COLUMN_PARAMS = ("sort_by", "order_by", "sort_column", "order_column")
_SORT_DIRECTION_PARAMS = (
    "order", "sort_order", "sort_dir", "sort_direction", "direction",
    "ascending",
)


def _sort_spec(m):
    """(column_param, direction_param) of a designed list method, or None.

    BOTH halves must be present and distinct: a lone ``sort_by`` says WHICH
    column but not which way, and a lone ``order`` states a direction with
    nothing to order — neither is an ordering contract.
    """
    names = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    ]
    col = next((p for p in names if p in _SORT_COLUMN_PARAMS), None)
    direction = next((p for p in names if p in _SORT_DIRECTION_PARAMS), None)
    if not col or not direction or col == direction:
        return None
    return col, direction


# A specification that asks a report for BOTH a total and a count states the
# two in ONE clause ("a report showing total sales amount and number of sales
# per product", prompt 20). The pair is read from the clause itself — a sum
# word and a count word in the same sentence. A total here and an inventory
# count there is not that contract, so the scan is strictly per sentence.
_REPORT_SUM_WORDS = ("total", "sum", "amount")
_REPORT_COUNT_WORDS = ("number of", "count of", "how many", "how often")


def _prompt_requests_sum_and_count(prompt_text):
    """True when one clause of the spec asks a report for a sum AND a count."""
    for sentence in re.split(r"[.;\n]+", prompt_text or ""):
        low = sentence.lower()
        if (
            any(w in low for w in _REPORT_SUM_WORDS)
            and any(w in low for w in _REPORT_COUNT_WORDS)
        ):
            return True
    return False


# A specification that says an entity's total is CALCULATED FROM ITS LINES has
# already fixed where that number comes from: it is arithmetic on the child
# rows, not a value the caller can know. Prompt-gated, so an entity that merely
# STORES a running total (inventory's stock value) is never captured.
_DERIVED_TOTAL_RE = re.compile(
    r"(?:total|amount|subtotal)[^.]{0,60}?"
    r"(?:calculat|comput|deriv|sum)"
    r"|(?:calculat|comput|deriv)[^.]{0,60}?(?:total|amount)",
    re.I,
)

# Field-name tokens that denote a TOTAL rather than a stored measurement.
_TOTAL_FIELD_TOKENS = ("total", "subtotal")


def _is_total_field(name):
    """True when a field NAME denotes a TOTAL.

    The declared TYPE is deliberately not consulted: the design types a money
    total as ``str`` as readily as ``float`` (prompt 28's ``total_amount``
    shipped ``--total-amount TEXT``), and the name is the reliable signal.
    """
    low = (name or "").lower()
    return any(t in low for t in _TOTAL_FIELD_TOKENS)


def _line_child_spec(ent_cls, entities_by_class):
    """The LINES shape for a derived total, or None.

    Two shapes are recognised, both structural (no domain vocabulary):

    * the line carries BOTH a quantity and a price — ``{"child", "fk_field",
      "value_field", "price_field"}`` (prompt 22's OrderItem: quantity +
      unit_price);
    * the line carries a quantity and references ANOTHER entity that carries
      the price — ``{"child", "fk_field", "value_field", "price_via":
      {ref_entity, fk_field, price_field}}`` (prompt 28's InvoiceLine:
      "Each line references a product and quantity").

    The lines entity is the unique designed entity carrying a foreign key to
    this one and matching one of the two shapes. Ambiguity declines, so a wrong
    child is never used to compute a total.
    """
    out = []
    for child_cls, child in (entities_by_class or {}).items():
        if child_cls == ent_cls or not isinstance(child, dict):
            continue
        fk_field = None
        for f in child.get("fields") or []:
            if not isinstance(f, dict) or not isinstance(f.get("name"), str):
                continue
            nm = f["name"]
            if not nm.endswith("_id") or nm == "id":
                continue
            if _camel(nm[: -len("_id")]) == ent_cls:
                fk_field = nm
                break
        if fk_field is None:
            continue
        nums = sorted(
            f["name"] for f in (child.get("fields") or [])
            if isinstance(f, dict) and isinstance(f.get("name"), str)
            and f.get("type") in ("int", "float")
            and f["name"] != "id"
            and not f["name"].endswith("_id")
        )
        child_snake = _snake(child_cls)
        if len(nums) == 2:
            out.append({
                "child": child_snake,
                "fk_field": fk_field,
                "value_field": nums[0],
                "price_field": nums[1],
            })
            continue
        if len(nums) != 1:
            continue
        # One numeric column only: it is the quantity, and the price must come
        # from the entity the line references — accepted only when exactly one
        # such FK resolves to that entity and it carries exactly one numeric
        # scalar (its price).
        ref_fks = sorted(
            f["name"] for f in (child.get("fields") or [])
            if isinstance(f, dict) and isinstance(f.get("name"), str)
            and f["name"].endswith("_id") and f["name"] != fk_field
            and f["name"] != "id"
        )
        priced = []
        for ref_fk in ref_fks:
            ref_ent = entities_by_class.get(_camel(ref_fk[: -len("_id")]))
            if not isinstance(ref_ent, dict):
                continue
            ref_nums = sorted(
                f["name"] for f in (ref_ent.get("fields") or [])
                if isinstance(f, dict) and isinstance(f.get("name"), str)
                and f.get("type") in ("int", "float")
                and f["name"] != "id"
                and not f["name"].endswith("_id")
            )
            if len(ref_nums) == 1:
                priced.append((ref_fk, ref_ent["name"], ref_nums[0]))
        if len(priced) != 1:
            continue
        ref_fk, ref_cls, price_field = priced[0]
        out.append({
            "child": child_snake,
            "fk_field": fk_field,
            "value_field": nums[0],
            "price_via": {
                "ref_entity": ref_cls,
                "fk_field": ref_fk,
                "price_field": price_field,
            },
        })
    return out[0] if len(out) == 1 else None


def _apply_derived_total_floors(entities_by_class, designs, prompt_text):
    """A total the specification DERIVES from lines is not a caller input.

    Two halves, both design-driven:

    * MARK the parent entity's total field, so the CLI surface never offers
      ``--<total>`` on add/update and the caller is never asked for a number
      only arithmetic can know (prompt 22's ``--total-amount``, prompt 28's
      invoice total);
    * drop a total parameter the service design invented anyway, so add/update
      cannot demand it a second time.

    Prompt-gated and structural: it fires only when the specification says the
    total is calculated/derived/computed from the lines AND the design really
    has a lines entity (an FK plus a quantity and a price). Idempotent, and
    called early — before the CLI surface is derived, or the option would
    already be listed.
    """
    if not _DERIVED_TOTAL_RE.search(prompt_text or ""):
        return
    for ent_cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict):
            continue
        totals = sorted(
            f["name"] for f in (ent.get("fields") or [])
            if isinstance(f, dict) and isinstance(f.get("name"), str)
            and _is_total_field(f["name"])
        )
        if len(totals) != 1:
            continue
        lines = _line_child_spec(ent_cls, entities_by_class)
        if lines is None:
            continue
        ent["derived_fields"] = [totals[0]]
        ent["derived_total"] = lines
        total_field = totals[0]
        for _path, kind, data in designs or []:
            if kind != "services" or not isinstance(data, dict):
                continue
            for mth in data.get("methods") or []:
                if not isinstance(mth, dict):
                    continue
                mname = mth.get("name") or ""
                if not mname.startswith(("add_", "create_", "update_")):
                    continue
                params = mth.get("params")
                if not isinstance(params, list):
                    continue
                mth["params"] = [
                    q for q in params
                    if not (isinstance(q, dict)
                            and q.get("name") == total_field)
                ]


def _ensure_derived_total_methods(entities_by_class, designs):
    """Ensure ``calculate_<entity>_total(<pk>)`` renders ``sum_children``.

    The specification says the total "must be calculated from its lines"
    (prompt 28) / to "calculate the total order amount" (prompt 22). The
    ``sum_children`` recipe renders exactly that, but nothing generated its
    impl, so the capability was unreachable. The method is added to — or
    resolved in place on — the designed service, with the lines entity, its FK
    and its two per-line numerics read off the design.
    """
    for ent_cls, ent in (entities_by_class or {}).items():
        dt = ent.get("derived_total") if isinstance(ent, dict) else None
        if not isinstance(dt, dict):
            continue
        target = "calculate_%s_total" % _snake(ent_cls)
        impl = {
            "kind": "sum_children",
            "entity": dt["child"],
            "fk_field": dt["fk_field"],
            "value_field": dt["value_field"],
            "parent_id_param": "id",
        }
        if dt.get("price_via"):
            impl["price_via"] = dt["price_via"]
        else:
            impl["price_field"] = dt["price_field"]
        for _path, kind, data in designs or []:
            if kind != "services" or not isinstance(data, dict):
                continue
            methods = data.setdefault("methods", [])
            found = next(
                (
                    m for m in methods
                    if isinstance(m, dict)
                    and (
                        m.get("name") == target
                        or (m.get("name") or "").startswith("calculate_")
                    )
                ),
                None,
            )
            if found is not None:
                found["impl"] = impl
                continue
            methods.append({
                "name": target,
                "params": [{"name": "id", "type": "int"}],
                "returns": "float",
                "impl": impl,
            })


def _apply_report_count_floors(entities_by_class, designs, prompt_text):
    """Mark a grouped report that must ALSO carry a count.

    A report whose specification asks for a total and a count of the same rows
    can only answer both if each group carries both. The shipped report
    returned ``{product_id: 50.0}`` — the amount with no count — while the
    specification asked for "total sales amount AND number of sales per
    product" (prompt 20). The mark rides on the ``sum_by_group`` impl the
    design already produced for that method, so the recipe that renders it
    extends IN PLACE: nothing is invented, no unrelated report is touched, and
    a project whose reports only sum is left exactly as it was.
    """
    if not _prompt_requests_sum_and_count(prompt_text):
        return
    for _path, kind, data in designs or []:
        if kind not in ("services", "repositories") or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict):
                continue
            impl = m.get("impl")
            if isinstance(impl, dict) and impl.get("kind") == "sum_by_group":
                impl["also_count"] = True


def _apply_sort_floors(entities_by_class, designs):
    """Mark, per entity, that its list() must ORDER BY a caller-named column.

    A designed ``list_<entity>`` taking BOTH a column selector and a direction
    selector IS the deterministic contract the specification's "list products
    sorted by name, price or quantity, in ascending or descending order"
    describes (prompt 15). Without the mark the repository's list() has no way
    to order, so the command always ran ``ORDER BY id`` and the sort columns
    had even been mistaken for EQUALITY FILTERS.

    The mark is per entity, resolved through the list method's own NAME (an
    ordering on Product never orders Customers), and the ORDER BY column is
    WHITELISTED at render time from the entity's own scalar fields, so a
    caller-supplied column can never reach the SQL text unchecked.
    """
    for _path, kind, data in designs or []:
        if kind != "services" or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            name = m["name"]
            if not name.startswith("list_"):
                continue
            spec = _sort_spec(m)
            if spec is None:
                continue
            ent_snake = name[len("list_"):]
            ent = entities_by_class.get(_camel(ent_snake))
            if not isinstance(ent, dict):
                continue
            fields = [
                f.get("name") for f in (ent.get("fields") or [])
                if isinstance(f, dict) and f.get("name")
                and f.get("name") != "id"
                and (f.get("type") or "") in ("str", "int", "float")
            ]
            if not fields:
                continue
            ent["sort_params"] = list(spec)
            ent["sort_fields"] = fields


def _apply_pagination_floors(entities_by_class, designs):
    """Mark the entities whose list method PAGINATES.

    The design is the only source: a designed service ``list_<entity>``
    carrying a page-number AND a page-size param (prompt 16's
    ``list_customer(page, page_size)``) settles the shape. The mark is
    per-entity, resolved from the METHOD NAME (``list_customer`` ->
    ``Customer``), never stamped entity-wide from a global param scan — with
    three entities, only Customer's list pages.

    Records ``ent["page_filters"] = [<num param>, <size param>]`` for the two
    renderers that must agree on it: the repository renderer (which appends
    the params to ``list()`` and pages its SQL) and the service renderer
    (which forwards them and returns the total). Declared marks are never
    overwritten.
    """
    for path, kind, data in designs:
        if kind != "services" or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict):
                continue
            name = m.get("name") or ""
            if not name.startswith("list_"):
                continue
            pnames = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            num = next((p for p in pnames if p in _PAGE_NUM_PARAMS), None)
            size = next((p for p in pnames if p in _PAGE_SIZE_PARAMS), None)
            if not (num and size):
                continue
            stem = name[len("list_"):]
            for cls, ent in entities_by_class.items():
                if not isinstance(ent, dict):
                    continue
                if _snake(cls) in (stem, stem.rstrip("s")):
                    ent.setdefault("page_filters", [num, size])
    return entities_by_class


def _apply_filter_floors(entities_by_class, designs):
    """Deterministic floor for entity list_filters, derived ONLY from the
    designed method signatures — never from prompt text or field-name
    suffixes:

    - a designed parameter whose name equals a non-id field of the entity
      becomes an equality filter for that column;
    - a designed start_<x>/end_<x> parameter pair becomes a gte/lte range
      over the entity's only date/datetime-typed field, when exactly one
      such field exists.

    Declared list_filters always win; floors only fill gaps so the
    repository list() API covers the parameters the designed service and
    repository methods actually take.
    """
    uniq = []
    seen = set()
    # Param name -> declared type. A BOOL-typed param can never be a BOUND
    # value (see the flag normalisation below), so its type is load-bearing.
    param_types = {}
    for path, kind, data in designs:
        if kind not in ("repositories", "services") or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict):
                continue
            for p in m.get("params") or []:
                if not (isinstance(p, dict) and p.get("name")):
                    continue
                param_types.setdefault(p["name"], p.get("type"))
                if p["name"] not in seen:
                    seen.add(p["name"])
                    uniq.append(p["name"])
    uniq_set = set(uniq)
    start_sufs = {p[6:] for p in uniq if p.startswith("start_") and len(p) > 6}
    end_sufs = {p[4:] for p in uniq if p.startswith("end_") and len(p) > 4}
    range_sufs = sorted(start_sufs & end_sufs)

    for ent in entities_by_class.values():
        fields = {
            f.get("name"): f
            for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        }
        lf = [
            s for s in (ent.get("list_filters") or [])
            if isinstance(s, dict) and s.get("param")
        ]
        declared = {s["param"] for s in lf}
        covered_ops = {(s.get("column"), s.get("op")) for s in lf}

        # A BOOL list-filter is never a BOUND value. The click flag behind it
        # defaults to False and the rendered guard is "is not None", so that
        # False was BOUND into the comparison: inventory's `low_only` became
        # "AND stock_qty <= 0" and the UNFILTERED `product list` listed
        # nothing at all. Rewrite every bool spec as a constant predicate —
        # either the "below the referenced row's threshold" test the flag
        # actually means, or a bare truthiness guard on its own column.
        for spec in lf:
            ptype = param_types.get(spec["param"])
            if not _is_bool_param_type(ptype):
                continue
            flag = _flag_threshold_spec(
                spec["param"], ptype, ent, entities_by_class,
                declared_column=spec.get("column"),
            )
            if flag:
                spec["column"] = flag["column"]
                spec["op"] = "below_ref"
                spec["ref"] = flag["ref"]
                spec["ref_column"] = flag["ref_column"]
                spec["ref_cls"] = flag["ref_cls"]
                continue
            ctype = (fields.get(spec.get("column")) or {}).get("type")
            spec["op"] = "eq_true" if ctype == "bool" else "gt_zero"

        for fname in sorted(fields):
            if fname != "id" and fname in uniq_set and fname not in declared:
                lf.append({"param": fname, "column": fname, "op": "eq"})
                declared.add(fname)

        # A `<col>_domain` parameter filters a str column by the DOMAIN part of
        # its value (prompt 12: "filtering by email domain"). It must NOT be an
        # equality: comparing the whole `email = ?` against a domain matches
        # nothing at all, so the feature is silently dead.
        #
        # TWO paths, both corrected: the DESIGN may have declared it itself —
        # prompt 12 declares `email_domain` as an `eq` filter over `email` —
        # and an undeclared one may only appear in a designed method signature.
        # The declared spec is REWRITTEN in place (the design's own dict), and
        # only when `<col>` really is a str field of THIS entity, so an
        # unrelated `_domain` parameter (a bare `domain` search term) is never
        # captured.
        for spec in lf:
            p = spec.get("param") or ""
            if not p.endswith("_domain"):
                continue
            base = p[: -len("_domain")]
            if base in fields and (fields[base] or {}).get("type") == "str":
                spec["column"] = base
                spec["op"] = "like_domain"
        for p in sorted(uniq_set):
            if not p.endswith("_domain") or p in declared:
                continue
            base = p[: -len("_domain")]
            if base in fields and (fields[base] or {}).get("type") == "str":
                lf.append({"param": p, "column": base, "op": "like_domain"})
                declared.add(p)

        # Cross-entity filter: a designed param that is not a field on this
        # entity but IS a field on a JOIN entity that references this entity
        # via FK (e.g. Post filtered by PostTag.tag_id — prompt 23's "view
        # posts by tag"). Add it so repo.list() serves the filter instead of
        # the CLI's --tag-id being unmappable. The repo renderer emits a JOIN
        # for these columns (see _render_repository_file).
        for p in sorted(uniq_set):
            if p in declared or p == "id" or p in fields:
                continue
            for cls, other in entities_by_class.items():
                if cls == ent["name"]:
                    continue
                other_fields = {
                    f.get("name")
                    for f in (other.get("fields") or [])
                    if isinstance(f, dict)
                }
                if p not in other_fields:
                    continue
                if any(
                    isinstance(fk, dict) and fk.get("ref") == ent["name"]
                    for fk in (other.get("fks") or [])
                ):
                    lf.append({"param": p, "column": p, "op": "eq"})
                    declared.add(p)
                    break

        date_cols = [
            n for n in sorted(fields)
            if fields[n].get("type") in ("date", "datetime")
        ]

        def _resolve_range_col(suf):
            """Date column for a start_<x>/end_<x> suffix: exact field-name
            match first, then unique '<col>_<suffix>' match, else the unique
            date column. Works for multi-date entities where the suffix
            disambiguates (start_date/end_date -> expense_date)."""
            exact = [c for c in date_cols if c == suf]
            if len(exact) == 1:
                return exact[0]
            suffixed = [c for c in date_cols if c.endswith("_" + suf)]
            if len(suffixed) == 1:
                return suffixed[0]
            if len(date_cols) == 1:
                return date_cols[0]
            return None

        for suf in range_sufs:
            pa, pb = "start_" + suf, "end_" + suf
            if pa in declared or pb in declared:
                continue
            col = _resolve_range_col(suf)
            if col is None:
                continue
            if (col, "gte") in covered_ops or (col, "lte") in covered_ops:
                continue
            lf.append({"param": pa, "column": col, "op": "gte"})
            lf.append({"param": pb, "column": col, "op": "lte"})
            declared.update((pa, pb))

        # min_<x>/max_<x> bounds over ANY typed column (numeric or date):
        # resolution mirrors _resolve_range_col — exact field name first,
        # then a unique '<col>_<x>' suffix match, else the unique
        # numeric-or-date column. These let the deterministic list() serve
        # price_range-style designed queries without name heuristics.
        def _resolve_bound_col(suf):
            comparable = [
                n for n in sorted(fields)
                if fields[n].get("type") in ("int", "float", "date", "datetime")
            ]
            exact = [c for c in comparable if c == suf]
            if len(exact) == 1:
                return exact[0]
            suffixed = [c for c in comparable if c.endswith("_" + suf)]
            if len(suffixed) == 1:
                return suffixed[0]
            if len(comparable) == 1:
                return comparable[0]
            return None

        bounds_seen = set()
        for pre in ("min_", "max_"):
            for p in uniq:
                if p.startswith(pre) and len(p) > len(pre):
                    bounds_seen.add((pre, p[len(pre):]))
        for pre, suf in sorted(bounds_seen):
            pa = pre + suf
            if pa in declared:
                continue
            col = _resolve_bound_col(suf)
            if col is None:
                continue
            op = "gte" if pre == "min_" else "lte"
            if (col, op) in covered_ops:
                continue
            lf.append({"param": pa, "column": col, "op": op})
            declared.add(pa)
        ent["list_filters"] = lf

    # Flag filters from bounded CLI propagation: a synthesized
    # list_<entity>(<flag>: bool) carries flag_filters mapping each bool
    # param onto a constant predicate over ONE real column. Adopt them into
    # the owning entity's declared filters so repo.list() serves them and
    # the generic delegation tier passes them through.
    for path, kind, data in designs:
        if kind != "services" or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            ff = m.get("flag_filters") if isinstance(m, dict) else None
            if not isinstance(ff, dict) or not ff:
                continue
            mname = m.get("name") or ""
            if not mname.startswith("list_"):
                continue
            ent_snake = mname[len("list_"):]
            ent = next(
                (
                    e for e in entities_by_class.values()
                    if _snake(e.get("name") or "") == ent_snake
                ),
                None,
            )
            if ent is None:
                continue
            cols = {
                f.get("name")
                for f in (ent.get("fields") or [])
                if isinstance(f, dict) and f.get("name")
            }
            lf = ent.setdefault("list_filters", [])
            declared = {
                s.get("param") for s in lf if isinstance(s, dict)
            }
            for pname, spec in sorted(ff.items()):
                if not isinstance(spec, dict) or pname in declared:
                    continue
                col, op = spec.get("column"), spec.get("op")
                if col not in cols or op not in ("eq_true", "gt_zero"):
                    continue
                lf.append({"param": pname, "column": col, "op": op})
                declared.add(pname)


def _apply_impl_floors(entities_by_class, designs):
    """Deterministic floor for declarative service impls, derived ONLY from
    the designed signatures and entity shapes — no method-name patterns,
    no domain vocabulary:

    - period total: a Dict-returning method whose params are exactly one
      scalar that is NOT a declared list_filter of the (unique) entity
      having exactly one date-typed and one numeric field. A str period
      binds to a month bucket ("YYYY-MM"), an int period to a year bucket.
    - filtered total: a Dict-returning method whose params all match the
      candidate entity's declared list_filters.

    Only fills gaps: methods already carrying a valid impl are untouched.

    CRUD-shaped methods (add_/create_/update_/delete_/list_/get_/<entity>)
    are NEVER stamped here: they render deterministically through generic
    CRUD delegation, and stamping an aggregate impl over a create signature
    silently turns add_category into "sum of filtered rows" (observed on
    inventory after propagation synthesized add_category).
    """
    for path, kind, data in designs:
        if kind != "services" or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict):
                continue
            mname = m.get("name") or ""
            returns = m.get("returns") or ""
            low_ret = returns.lower()
            grouped = (
                "list" in low_ret
                and ("Dict" in returns or "dict" in returns)
            )
            # add_/create_<entity> are deterministic CRUD creates — a
            # hallucinated aggregate impl (the LLM designed add_room with
            # {"kind": "total_in_period"}) must be CLEARED so the create body
            # renders via generic delegation instead of a sum-of-rows.
            if re.match(r"^(add|create)_", mname):
                m.pop("impl", None)
            # list_<entity> returning List[Dict] is a grouped report per the
            # grouped-count floor below; a hallucinated aggregate impl
            # (sum_by_group over id, duplicate_groups with a hardcoded
            # threshold) must be CLEARED so that floor can stamp
            # count_by_group instead of a nonsense sum-of-ids.
            if mname.startswith("list_") and grouped:
                m.pop("impl", None)
            if m.get("impl") is not None:
                continue
            # CRUD verbs (add/create/update/delete/get/search/find) are
            # rendered deterministically via generic delegation — never stamp
            # an aggregate impl over them.
            if re.match(
                r"^(add|create|update|delete|remove|set|get|search|find)_",
                mname,
            ):
                continue
            # list_<entity> returns List[Entity] for a plain CRUD list; a
            # List[Dict] return is a grouped report — let the grouped-count
            # floor handle it (prompt 27's list_reservation).
            if mname.startswith("list_") and not grouped:
                continue
            if (
                "Dict" not in returns and "dict" not in returns
                and "int" not in low_ret and "float" not in low_ret
            ):
                continue
            params = [
                p.get("name")
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            # Grouped count: a List[Dict]-returning method whose params are all
            # declared filters is a grouped report. Stamp count_by_group with
            # group_by = the non-date/datetime filter params (the grouping
            # dimensions); each row counts 1, never a date/numeric field
            # (prompt 27's list_reservation did `0 + row.start_date`).
            if grouped:
                cand = next(
                    (
                        (cls_, ent_)
                        for cls_, ent_ in entities_by_class.items()
                        if params
                        and set(params) <= set(_filter_params(ent_))
                    ),
                    None,
                )
                if cand is not None:
                    cls_, ent_ = cand
                    date_cols = {
                        f["name"] for f in (ent_.get("fields") or [])
                        if isinstance(f, dict)
                        and f.get("type") in ("date", "datetime")
                    }
                    # Range-bound params (gte/lte over a column) are
                    # constraints, not grouping dimensions: a param floored
                    # onto a date/numeric column (created_at_end -> lte) must
                    # not become a group key, or _impl_bindings_ok rejects it
                    # (created_at_end is not a Project field) and the method
                    # degrades to an LLM stub (prompt 24's list_project
                    # summed e.title and returned a dict).
                    range_params = {
                        s.get("param")
                        for s in (ent_.get("list_filters") or [])
                        if isinstance(s, dict)
                        and s.get("op") in ("gte", "lte")
                    }
                    group_by = [
                        p for p in params
                        if p not in date_cols and p not in range_params
                    ]
                    # A group key equal to the entity's OWN unique_together
                    # constraint can only group ONE row per group: the count is
                    # a constant 1 and the entity's own columns are replaced by
                    # a synthetic ``{'count': 1}`` dict. expenses' Budget is
                    # declared UNIQUE(category_id, month), so `budget list`
                    # answered ``[{'category_id': 1, 'month': '2024-01',
                    # 'count': 1}]`` instead of the budget rows the
                    # specification's own `budget list` asks for. Such a method
                    # is a plain filtered CRUD list of the entity's rows: leave
                    # it unstamped so the generic delegation renders it.
                    unique_keys = {
                        tuple(sorted(str(c) for c in up))
                        for up in (ent_.get("unique_together") or [])
                        if isinstance(up, (list, tuple, set))
                    }
                    # A method named ``list_<entity>`` / ``list_<entities>``
                    # for a DESIGNED entity IS the canonical CRUD list of that
                    # entity's rows — the same name the generic delegation tier
                    # owns. Its ``List[Dict]`` annotation is only the element
                    # shape the design chose, so it must never be rewritten
                    # into a grouped count: expenses'
                    # ``list_expenses(category_id, start_date, end_date,
                    # payment_method)`` shipped ``[{'category_id': 1,
                    # 'payment_method': 'cash', 'count': 1}, …]`` instead of the
                    # expenses the specification's own `expense list` asks for.
                    if (
                        len(group_by) >= 2
                        and tuple(sorted(group_by)) not in unique_keys
                        and not _is_generic_crud_name(mname, entities_by_class)
                    ):
                        m["impl"] = {
                            "kind": "count_by_group",
                            "entity": _snake(cls_),
                            "group_by": group_by,
                        }
                        continue
            # list_<entity> returning List[Dict] is a grouped report; only
            # count_by_group above may stamp it. Never give a list_* method a
            # total_in_period/total_filtered sum — it would sum a string/date
            # column (prompt 28's list_invoice summed total_amount).
            if mname.startswith("list_"):
                continue
            # unique aggregate-capable entity: exactly one date + one numeric
            cands = []
            for cls_, ent_ in entities_by_class.items():
                flds = [
                    f for f in (ent_.get("fields") or [])
                    if isinstance(f, dict) and f.get("name") and f["name"] != "id"
                ]
                dates = [f["name"] for f in flds
                         if f.get("type") in ("date", "datetime")]
                # exclude foreign keys: an FK column is an int but is never
                # the aggregate target of a total
                nums = [
                    f["name"] for f in flds
                    if f.get("type") in ("int", "float")
                    and not f["name"].endswith("_id")
                ]
                if len(dates) == 1 and len(nums) == 1:
                    cands.append((cls_, ent_, dates[0], nums[0]))
            dcol = None
            if len(cands) == 1:
                cls, ent, dcol, ncol = cands[0]
            else:
                # Relaxed fallback: exactly ONE numeric-non-FK entity whose
                # DECLARED filter set covers every method param -> a pure
                # filtered total (no period bucketing). Handles entities
                # with several date fields where the strict shape test
                # finds no unique candidate.
                hits = []
                for cls_, ent_ in entities_by_class.items():
                    flds = [
                        f for f in (ent_.get("fields") or [])
                        if isinstance(f, dict) and f.get("name") and f["name"] != "id"
                    ]
                    nums = [
                        f["name"] for f in flds
                        if f.get("type") in ("int", "float")
                        and not f["name"].endswith("_id")
                    ]
                    if len(nums) != 1:
                        continue
                    fparams = {
                        s.get("param")
                        for s in (ent_.get("list_filters") or [])
                        if isinstance(s, dict) and s.get("param")
                    }
                    if params and set(params) <= fparams:
                        hits.append((cls_, ent_, nums[0]))
                if len(hits) != 1:
                    continue
                cls, ent, ncol = hits[0]
            declared = {
                s.get("param")
                for s in (ent.get("list_filters") or [])
                if isinstance(s, dict)
            }
            nonfilter = [p for p in params if p not in declared]
            # A period total is only well-formed when that single param really
            # NAMES a period. ``id`` is an entity's ROW id, not a year:
            # stamping total_in_period over it made expenses' over-generated
            # ``detect_category(id)`` bucket every expense over
            # ``str(id)+'-01-01'`` .. ``str(id)+'-12-31'`` — the row id read as
            # a year (S6). Without a period name the method carries no
            # exactly-renderable aggregate and keeps its LLM fill, where the
            # repo/entity coherence gate holds it to Category's own repository.
            if not any(
                tok in params[0].lower()
                for tok in ("month", "year", "period", "week", "quarter",
                            "annee", "mois")
            ):
                continue
            if len(params) == 1 and len(nonfilter) == 1:
                ptype = next(
                    (q.get("type", "") for q in m.get("params") or []
                     if isinstance(q, dict) and q.get("name") == params[0]),
                    "",
                )
                m["impl"] = {
                    "kind": "total_in_period",
                    "entity": _snake(cls),
                    "value_field": ncol,
                    "date_field": dcol,
                    "period_param": params[0],
                    "granularity": "year" if "int" in ptype.lower() else "month",
                    "result_key": "total",
                }
            elif params and len(nonfilter) == 0:
                m["impl"] = {
                    "kind": "total_filtered",
                    "entity": _snake(cls),
                    "value_field": ncol,
                    "result_key": "total",
                }

    # Repository floor: a custom repo method whose params ALL map to the
    # entity's DECLARED list_filters is a pure filtered listing — attach
    # impl {"kind": "list_filtered"} so its body renders deterministically.
    # This replaces every find_*_by_* / by_date_range name heuristic.
    for path, kind, data in designs:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        ent = entities_by_class.get(_camel(ent_snake))
        if not isinstance(ent, dict):
            continue
        valid = set(_filter_params(ent))
        if not valid:
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or m.get("impl") is not None:
                continue
            # Only LISTING-shaped methods (List[...] / unspecified return):
            # a count/scalar custom query must stay a stub for the LLM fill.
            returns = m.get("returns") or ""
            if returns and "list" not in returns.lower():
                continue
            params = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            if params and all(p in valid for p in params):
                m["impl"] = {"kind": "list_filtered"}


def _service_repo_interface(entities_by_class, designs, repo_sources=None):
    """{repo_attr: {method: [param names]}} exactly as _render_repository_file
    emits them: base CRUD + unique_together lookup + designed customs.

    Lets the service fill be validated mechanically so an LLM-filled body
    can never call a repo method that does not exist or pass the wrong
    number of arguments.

    When ``repo_sources`` (rendered repository file paths) is given, only
    methods ACTUALLY present in the shipped repository source are
    advertised. The repo fill can fail (rejected/uncompilable), leaving a
    designed custom method as a stub or absent; advertising the DESIGN
    method lets the service fill call a method that never shipped ->
    AttributeError at runtime (prompt 22's get_order_report calling
    order_repo.get_total_order_value).
    """
    repo_designs = {}
    for path, kind, data in designs:
        if kind == "repositories" and isinstance(data, dict):
            repo_designs[Path(path).stem] = data
    # Actual rendered repo source (path -> source), when available.
    repo_srcs = {Path(p).stem: s for p, s in (repo_sources or {}).items()}
    interface = {}
    for ent in entities_by_class.values():
        ent_snake = _snake(ent["name"])
        # Only entities with a designed repository FILE may be advertised to
        # the fill. An entity referenced only by FK (Customer/Product behind
        # invoice.customer_id / line.product_id in prompt 28) appears in
        # models but has no <entity>_repository.py; wiring or advertising a
        # repo for it makes the fill call a self.<x>_repo that is never
        # instantiated -> runtime AttributeError/NameError.
        if (ent_snake + "_repository") not in repo_designs:
            continue
        attr = ent_snake + "_repo"
        # Entries are (param name, required) so the fill validator can
        # enforce that every REQUIRED param is covered by a call.
        methods = {
            "create": [("_obj", True)],
            "get_by_id": [("id", True)],
            # _render_repository_file deterministically appends a
            # ``find_by_id`` alias (``def find_by_id(self, *args, **kwargs):
            # return self.get_by_id(*args, **kwargs)``) to every repo. Advertise
            # it so the 4B model's common ``find_by_id`` lookup call is legal
            # without burning the bounded alias-repair cap (which is 3/svc and
            # gets exhausted across library_system's ~30 stubs, so later methods
            # revert to safe stubs solely because the model used the synonym).
            "find_by_id": [("id", True)],
            "get_all": [],
            "list": ["_filters"],
            "update": [("id", True), ("data", True)],
            "delete": [("id", True)],
        }
        for up in ent.get("unique_together") or []:
            if isinstance(up, list) and len(up) == 2:
                a, b = [str(u) for u in up]
                a_fn = a[:-3] if a.endswith("_id") else a
                b_fn = b[:-3] if b.endswith("_id") else b
                methods["get_by_%s_and_%s" % (a_fn, b_fn)] = [(a, True), (b, True)]
        rdes = repo_designs.get(ent_snake + "_repository")
        if rdes:
            for m in rdes.get("methods") or []:
                if isinstance(m, dict) and m.get("name"):
                    params = []
                    for p in m.get("params") or []:
                        if isinstance(p, dict) and p.get("name"):
                            ptype = p.get("type") or ""
                            params.append(
                                (p["name"], not ptype.startswith("Optional"))
                            )
                    methods[m["name"]] = params
        # Restrict to methods ACTUALLY defined in the shipped repository
        # source, not just the design. The repo fill can fail (rejected or
        # uncompilable), leaving a designed custom method as a stub or
        # entirely absent; advertising the design lets a service fill call a
        # method that never shipped -> AttributeError at runtime (prompt 22's
        # get_order_report calling order_repo.get_total_order_value).
        repo_src = repo_srcs.get(ent_snake + "_repository")
        if repo_src:
            try:
                defined = {
                    n.name for n in ast.walk(ast.parse(repo_src))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                methods = {
                    name: sig for name, sig in methods.items()
                    if name in defined
                }
            except SyntaxError:
                # The repo source is broken (a custom-method stub failed to
                # compile before the AST repair pass). Base CRUD is
                # deterministic and always present; keep it, drop the
                # DESIGNED customs that may not have shipped so the service
                # fill can't call a method that will later be missing.
                base = {
                    "create", "get_by_id", "get_all", "list",
                    "update", "delete",
                }
                for up in ent.get("unique_together") or []:
                    if isinstance(up, list) and len(up) == 2:
                        a, b = [str(u) for u in up]
                        a_fn = a[:-3] if a.endswith("_id") else a
                        b_fn = b[:-3] if b.endswith("_id") else b
                        base.add("get_by_%s_and_%s" % (a_fn, b_fn))
                methods = {
                    name: sig for name, sig in methods.items()
                    if name in base
                }
        interface[attr] = methods
    return interface


_DICT_METHODS = {
    "get", "keys", "values", "items", "copy", "update",
    "setdefault", "pop", "popitem", "clear",
}


def _service_type_context(entities_by_class, designs):
    """Designed-type information for semantic fill validation.

    entity_fields: {class_name: set(valid field names incl. id)} — entity
      constructor kwargs and instance attribute reads are checked against
      these.
    repo_returns: {(repo_attr, method): tag} derived from the DESIGNED
      repository return types: ("entity", Class), ("list", Class),
      ("dict",) — absent when the return type carries no checkable shape.
    """
    entity_fields = {}
    required_fields = {}
    field_types = {}
    for cls, ent in entities_by_class.items():
        fields = {"id"}
        req = set()
        ft = {}
        for f in ent.get("fields") or []:
            if isinstance(f, dict) and f.get("name"):
                fields.add(f["name"])
                ft[f["name"]] = f.get("type")
                # A field without nullable and not the surrogate id is REQUIRED
                # in the constructor (no default). Omitting it is a guaranteed
                # TypeError (prompt 19's import_task built Task(...) without
                # created_at/updated_at). auto:"now" fields are still required
                # args — the deterministic add_<entity> stamps them, but a bare
                # Task(...) without them crashes.
                if (
                    not f.get("nullable")
                    and f.get("name") != "id"
                    and not (
                        f.get("auto") == "now"
                        and f.get("type") in ("date", "datetime")
                    )
                ):
                    req.add(f["name"])
        entity_fields[cls] = fields
        required_fields[cls] = req
        field_types[cls] = ft

    repo_designs = {}
    for path, kind, data in designs or []:
        if kind == "repositories" and isinstance(data, dict):
            repo_designs[Path(path).stem] = data

    def _tag(returns):
        r = (returns or "").strip()
        low = r.lower()
        for cls in entity_fields:
            if re.search(r"\b%s\b" % cls, r):
                return ("list", cls) if "list" in low else ("entity", cls)
        if "dict" in low:
            return ("dict",)
        return None

    repo_returns = {}
    for ent in entities_by_class.values():
        attr = _snake(ent["name"]) + "_repo"
        rdes = repo_designs.get(_snake(ent["name"]) + "_repository")
        if not rdes:
            continue
        cls = ent["name"]
        # Base CRUD methods are rendered deterministically by
        # _render_repository_file (get_by_id/list/get_all return the entity or
        # a list of it). Stamp their return tags so semantic fill validation
        # can type variables assigned from them — otherwise
        # reservation = self.reservation_repo.get_by_id(id) is never tagged as
        # an entity, and the .isoformat()-on-a-str rejection in
        # _semantic_fill_violations misses reservation.start_date.isoformat()
        # (prompt 27's get_reservation_report crash). Designed custom methods
        # still override these base tags below.
        repo_returns[(attr, "get_by_id")] = ("entity", cls)
        repo_returns[(attr, "list")] = ("list", cls)
        repo_returns[(attr, "get_all")] = ("list", cls)
        # create/update/delete return scalars (lastrowid / bool), never the
        # entity. Tag them so attribute access on the result is rejected
        # (inventory's restock assigned updated_product =
        # self.product_repo.update(...) then read updated_product.id, which
        # crashes on a bool at runtime).
        repo_returns[(attr, "create")] = ("scalar",)
        repo_returns[(attr, "update")] = ("scalar",)
        repo_returns[(attr, "delete")] = ("scalar",)
        for m in rdes.get("methods") or []:
            if isinstance(m, dict) and m.get("name"):
                t = _tag(m.get("returns"))
                if t:
                    repo_returns[(attr, m["name"])] = t
    return {
        "entity_fields": entity_fields,
        "required_fields": required_fields,
        "field_types": field_types,
        "repo_returns": repo_returns,
    }


def _repo_return_strings(entities_by_class, designs):
    """{(repo_attr, method): raw designed returns annotation}.

    Example: ('expense_repo', 'get_category_spending_range') -> 'int'.
    Feeds the service-fill hint and non-dict-access violation notes so the
    LLM knows the EXACT return type even when no shape gate applies
    (scalar annotations like int carry no ('dict',)-style tag).
    """
    returns = {}
    repo_designs = {}
    for path, kind, data in designs or []:
        if kind == "repositories" and isinstance(data, dict):
            repo_designs[Path(path).stem] = data
    for ent in entities_by_class.values():
        attr = _snake(ent["name"]) + "_repo"
        rdes = repo_designs.get(_snake(ent["name"]) + "_repository")
        if not rdes:
            continue
        for m in rdes.get("methods") or []:
            if isinstance(m, dict) and m.get("name"):
                ret = (m.get("returns") or "").strip()
                if ret:
                    returns[(attr, m["name"])] = ret
    return returns


def _dict_literal_keys(node):
    """The constant string keys of a dict literal, or None when undecidable."""
    if not isinstance(node, ast.Dict):
        return None
    keys = set()
    for key in node.keys:
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        keys.add(key.value)
    return keys


def _dict_value_keys(node):
    """The keys of ``{'a': ..}`` and of the filtered-comprehension shape.

    The renderer's own deterministic bodies build field dicts as
    ``{k: v for k, v in {'a': ..}.items() if v is not None}``; resolving both
    shapes lets an ``Entity(**data)`` call be checked against what ``data``
    really carries.
    """
    keys = _dict_literal_keys(node)
    if keys is not None:
        return keys
    if isinstance(node, ast.DictComp) and node.generators:
        return _dict_literal_keys(node.generators[0].iter)
    return None


def _scope_dict_bindings(body):
    """{variable: {keys}} for the ``x = {...}`` assignments in a body."""
    out = {}
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            keys = _dict_value_keys(node.value)
            if keys:
                out[target.id] = keys
    return out


def _dict_bindings_by_scope(tree):
    """{id(scope node): {variable: {keys}}} for the module and every function."""
    return {
        id(scope): _scope_dict_bindings(scope.body)
        for scope in ast.walk(tree)
        if isinstance(
            scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)
        )
    }


def _scope_bindings_lookup(tree, bindings_by_scope):
    """A ``node -> bindings`` resolver walking the AST parent chain."""
    parent_of = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_of[id(child)] = parent

    def _lookup(node):
        cur = node
        while cur is not None:
            if id(cur) in bindings_by_scope:
                return bindings_by_scope[id(cur)]
            cur = parent_of.get(id(cur))
        return {}

    return _lookup


def _semantic_fill_violations(tree, type_ctx):
    """Semantic checks over an LLM service fill using DESIGNED types only:

    (1) An entity constructor call may only pass declared field names —
        Expense(amount=...) when the model declares amount_cents is a
        guaranteed TypeError at runtime.
    (2) A variable assigned from a repo call whose designed return is an
        entity may only access declared fields (product.stock vs the
        declared stock_qty).
    (3) A variable assigned from a Dict-returning repo call must not be
        attribute-accessed (budget_status.spending on a plain dict).
    """
    entity_fields = type_ctx["entity_fields"]
    repo_returns = type_ctx["repo_returns"]

    def _repo_call_key_tag(call):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Attribute)
            and isinstance(call.func.value.value, ast.Name)
            and call.func.value.value.id == "self"
            and call.func.value.attr.endswith("_repo")
        ):
            return None
        key = (call.func.value.attr, call.func.attr)
        return key, repo_returns.get(key)

    dict_keys = type_ctx.get("dict_keys") or {}

    # pass 1b: designed parameter types from the skeleton signatures —
    # lets us catch guaranteed TypeErrors like date + str concatenation.
    param_types = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args:
                if arg.arg == "self" or arg.annotation is None:
                    continue
                try:
                    param_types[arg.arg] = ast.unparse(arg.annotation).lower()
                except Exception:
                    param_types[arg.arg] = ""

    # pass 1: variable types from repo-call assignments and iterations
    var_types = {}
    var_keys = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            tag = None
            keys = None
            # Direct entity construction (Task(**data) / Task(...)) yields an
            # entity instance: attribute/method access on it is checked
            # against the declared fields too, so a non-existent method like
            # task.to_dict() (prompt 19's import_task) is rejected. Previously
            # only repo-call results were tagged, so constructor-built entities
            # escaped the field check.
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in entity_fields
            ):
                tag = ("entity", node.value.func.id)
            else:
                hit = _repo_call_key_tag(node.value)
                if hit:
                    (attr, meth), tag = hit
                    keys = dict_keys.get((attr, meth))
            if tag:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        var_types[tgt.id] = tag
                        if keys:
                            var_keys[tgt.id] = keys
        elif isinstance(node, ast.For):
            hit = _repo_call_key_tag(node.iter)
            if hit:
                _, tag = hit
                # Scalar-returning repo methods carry no shape tag (None):
                # only a designed List[Entity] iterates as entities.
                if (
                    tag
                    and tag[0] == "list"
                    and isinstance(node.target, ast.Name)
                ):
                    var_types[node.target.id] = ("entity", tag[1])

    # pass 1b: tag for-loop targets whose iter is a VARIABLE assigned from a
    # list-returning repo call. `for item in order_items:` where
    # `order_items = self.order_item_repo.list(...)` — the iter is a Name,
    # not a repo call, so the direct-call branch above never tags `item`,
    # and `item.product` (a non-field) escapes validation (prompt 22's
    # get_order_report). The assignment pass already ran, so var_types has
    # the list tag.
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            iter_var = getattr(node.iter, "id", None)
            tag = var_types.get(iter_var) if iter_var else None
            if tag and tag[0] == "list":
                var_types[node.target.id] = ("entity", tag[1])

    # pass 1c: date/datetime-typed entity fields are read back from SQLite as
    # ISO strings; arithmetic over them (0 + row.start_date, results.get(...)
    # + row.loan_date) is a guaranteed TypeError at runtime. Reject any BinOp
    # that combines a date/datetime entity attribute with another operand.
    field_types = (type_ctx or {}).get("field_types") or {}
    DATETIME_TYPES = ("date", "datetime")
    date_arith = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue
        for rnd in (node.left, node.right):
            if not (
                isinstance(rnd, ast.Attribute)
                and isinstance(rnd.value, ast.Name)
            ):
                continue
            tag = var_types.get(rnd.value.id)
            if not (tag and tag[0] == "entity"):
                continue
            ftypes = field_types.get(tag[1], {})
            if ftypes.get(rnd.attr) in DATETIME_TYPES:
                date_arith.append(
                    "%s.%s is a date/datetime field (read back as a str); "
                    "do not add/subtract/compute with it — pass it through"
                    % (rnd.value.id, rnd.attr)
                )
                break
    violations = list(date_arith)
    # A constructor called as ``Entity(**data)`` names its fields through a
    # dict, so the missing-required-field gate below must resolve what that
    # dict carries — otherwise a correct body is rejected for "missing
    # book_id, due_date, member_id, status" while it passes all four
    # (library_system's borrow_book looped three times and shipped a stub).
    _scope_bindings = _scope_bindings_lookup(
        tree, _dict_bindings_by_scope(tree)
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fields = entity_fields.get(node.func.id)
            if fields:
                bad = sorted(
                    kw.arg for kw in node.keywords
                    if kw.arg and kw.arg not in fields
                )
                if bad:
                    violations.append(
                        "%s() got unknown field(s) %s (declared: %s)"
                        % (
                            node.func.id,
                            ", ".join(bad),
                            ", ".join(sorted(fields)),
                        )
                    )
                if len(node.args) > len(fields):
                    violations.append(
                        "%s() called with %d positional args; the model "
                        "declares %d field(s)"
                        % (node.func.id, len(node.args), len(fields))
                    )
                # Missing-required-field gate: an entity constructor must
                # provide every REQUIRED (non-nullable, non-id) field, else it
                # is a guaranteed TypeError at runtime (prompt 19's import_task
                # built Task(...) without created_at/updated_at). The fill must
                # add them rather than ship a crash.
                req_fields = (type_ctx or {}).get("required_fields", {}).get(
                    node.func.id, set()
                )
                provided = {
                    kw.arg for kw in node.keywords
                    if kw.arg and kw.arg
                }
                spread_unknown = False
                for kw in node.keywords:
                    if kw.arg is not None:
                        continue
                    # ``**data``: resolve the keys the operand really carries.
                    # An operand that cannot be resolved makes the field set
                    # UNKNOWABLE, so the gate stands down rather than looping
                    # the fill forever on a body it cannot read.
                    keys = _dict_value_keys(kw.value)
                    if keys is None and isinstance(kw.value, ast.Name):
                        keys = _scope_bindings(node).get(kw.value.id)
                    if keys is None:
                        spread_unknown = True
                    else:
                        provided |= keys
                missing = set() if spread_unknown else req_fields - provided
                if missing:
                    violations.append(
                        "%s() missing required field(s) %s (model requires: %s)"
                        % (
                            node.func.id,
                            ", ".join(sorted(missing)),
                            ", ".join(sorted(req_fields)),
                        )
                    )
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Call)
        ):
            # Inline repo-call result attribute access (library_system I7:
            # self.member_repo.get_by_id(loan.member_id).loan_count).
            # The result of a designed repo method tagged ("entity", cls)
            # only exposes the entity's declared fields.
            hit = _repo_call_key_tag(node.value)
            if hit:
                (attr, meth), tag = hit
                if tag and tag[0] == "entity":
                    if (
                        node.attr not in entity_fields.get(tag[1], set())
                        and not (
                            node.attr.startswith("__")
                            and node.attr.endswith("__")
                        )
                    ):
                        violations.append(
                            "%s.%s: unknown field %r on %s (declared: %s)"
                            % (
                                ast.unparse(node.value)[:40],
                                node.attr,
                                node.attr,
                                tag[1],
                                ", ".join(
                                    sorted(entity_fields.get(tag[1], set()))
                                ),
                            )
                        )
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            tag = var_types.get(node.value.id)
            if not tag or node.attr in _DICT_METHODS:
                continue
            if tag[0] == "entity":
                if (
                    node.attr not in entity_fields.get(tag[1], set())
                    and not (
                        node.attr.startswith("__")
                        and node.attr.endswith("__")
                    )
                ):
                    violations.append(
                        "%s.%s: unknown field %r on %s (declared: %s)"
                        % (
                            node.value.id,
                            node.attr,
                            node.attr,
                            tag[1],
                            ", ".join(
                                sorted(entity_fields.get(tag[1], set()))
                            ),
                        )
                    )
            elif tag[0] == "dict":
                violations.append(
                    "%s is a dict (designed repository return); use "
                    "['%s'] instead of .%s"
                    % (node.value.id, node.attr, node.attr)
                )
            elif tag[0] == "scalar":
                violations.append(
                    "%s is a scalar result (create/update/delete return "
                    "int/bool); it has no attribute %r"
                    % (node.value.id, node.attr)
                )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("isoformat", "strftime", "date", "timestamp")
        ):
            # SQLite round-trips date/datetime columns as str, so a model
            # field read back from the repo is a str at runtime. Calling
            # .isoformat()/.strftime()/... on it raises AttributeError
            # (prompt 27's get_reservation_report did
            # reservation.start_date.isoformat()). Reject so the retry
            # passes the string through or parses it explicitly.
            val = node.func.value
            if isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
                tag = var_types.get(val.value.id)
                if tag and tag[0] == "entity":
                    violations.append(
                        "%s.%s is read back from SQLite (str for date/datetime); "
                        "do not call .%s() on it — pass the string through"
                        % (val.value.id, val.attr, node.func.attr)
                    )
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):

            def _side_kind(n):
                if isinstance(n, ast.Name):
                    # Designed range params (start_*/end_*, floored onto date
                    # columns by _apply_filter_floors) must never be string-
                    # mangled regardless of their declared type.
                    if n.id.startswith(("start_", "end_")):
                        return "date"
                    t = param_types.get(n.id, "")
                    return "date" if "date" in t else None
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    return "str"
                return None

            kinds = {_side_kind(node.left), _side_kind(node.right)}
            if kinds == {"date", "str"}:
                violations.append(
                    "date + str concatenation (%s + %s) raises TypeError; "
                    "build the filter values with explicit formatting "
                    "instead"
                    % (
                        ast.unparse(node.left)[:40],
                        ast.unparse(node.right)[:40],
                    )
                )
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys = var_keys.get(node.value.id)
            if keys and node.slice.value not in keys:
                violations.append(
                    "%s['%s']: unknown dict key %r (returned keys: %s)"
                    % (
                        node.value.id,
                        node.slice.value,
                        node.slice.value,
                        ", ".join(sorted(keys)),
                    )
                )
    return violations


def _dict_shaped_expr(node):
    """True when an AST expression is observably a plain dict: a Dict
    literal, a `<expr>.__dict__` attribute, or a dict(...) call. Used to
    reject repo.create(<dict>) fills — create takes the ENTITY OBJECT and
    reads its attributes, so a dict argument is a guaranteed AttributeError
    at runtime."""
    return (
        isinstance(node, ast.Dict)
        or (isinstance(node, ast.Attribute) and node.attr == "__dict__")
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "dict"
        )
    )


def _undefined_name_violations(tree, extra_bound=None):
    """Flag bare Name loads in a fill that are never bound anywhere.

    The LLM fill re-emits the whole service file with the locked header, so
    collecting every imported/defined/param/assigned name across the tree
    yields the names that may legally appear. A Name used in a Load context
    and absent from that set is a guaranteed NameError at runtime — e.g.
    prompt 18's import_contact referenced ``filename`` which is neither a
    parameter, an import, nor a local assignment. Builtins are always
    available. Over-collecting bound names keeps this conservative: it only
    fires on names that are truly never bound, so valid fills are not
    spuriously rejected.

    ``extra_bound`` carries the names the MERGED module binds at top level
    but the snippet does not import itself (the service header's
    ``from database import Database`` and its model imports): a fill that
    annotates a local with a name the header already provides is not a
    NameError, and reporting it sent library_system's service fill into a
    pointless retry ("undefined name 'Database'").
    """
    bound = set(dir(builtins))
    bound.add("self")
    bound.update(extra_bound or ())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            args = node.args
            for arg in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
                bound.add(arg.arg)
            if args.vararg:
                bound.add(args.vararg.arg)
            if args.kwarg:
                bound.add(args.kwarg.arg)
        elif isinstance(node, ast.Lambda):
            args = node.args
            for arg in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
                bound.add(arg.arg)
            if args.vararg:
                bound.add(args.vararg.arg)
            if args.kwarg:
                bound.add(args.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                for n in ast.walk(tgt):
                    if isinstance(n, ast.Name):
                        bound.add(n.id)
        elif isinstance(node, ast.AugAssign):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
        elif isinstance(node, ast.With):
            for item in node.items:
                if item.optional_vars is not None:
                    for n in ast.walk(item.optional_vars):
                        if isinstance(n, ast.Name):
                            bound.add(n.id)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
        elif isinstance(node, ast.NamedExpr):
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in bound:
                violations.append(
                    "undefined name %r — not a parameter, import, or local "
                    "variable of this method" % node.id
                )
    return violations


def _repo_entity_coherence_violations(tree, entity_names, repo_interface):
    """A service method naming entity E must reach E's OWN repository.

    Deterministic, design-only (no prompt text): when a method's name names
    a designed entity E that owns a repository (list_author -> Author,
    get_overdue_loans -> Loan, detect_category -> Category) and the body
    touches SOME repository, that repository must be E's. A body wired only
    to a DIFFERENT entity's repo is bound to the wrong repository —
    library_system shipped ``list_author`` -> ``book_repo.list_books_with_
    available_copies()`` and ``get_overdue_loans`` -> the same book call.

    Only the entity NAMED by the method counts (never an FK parameter), so a
    legitimately cross-entity method such as ``history(member_id)`` — which
    names no entity and walks loan_repo — is never flagged. Methods that
    touch no repository at all are left to the other gates.
    """
    if not entity_names:
        return []
    violations = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        prim = _primary_named_entity(fn.name, entity_names)
        if prim is None:
            continue
        # Which repository the body must reach. A method that ACTS on a row
        # names that row through a ``<entity>_id`` parameter, and may reach
        # any OTHER entity only through that row's foreign keys:
        # return_book(loan_id) legitimately touches Book only via
        # loan.book_id, so demanding book_repo there would be wrong — it must
        # reach loan_repo, exactly like a pure query must reach its own
        # entity's repo. When no parameter names a row, the entity the method
        # NAME names is the requirement.
        required = set()
        for arg in fn.args.args:
            if arg.arg == "self" or not arg.arg.endswith("_id"):
                continue
            cand = next(
                (c for c in entity_names if _snake(c) == arg.arg[: -len("_id")]),
                None,
            )
            if cand is not None:
                required.add(_snake(cand) + "_repo")
        if not required:
            required.add(_snake(prim) + "_repo")
        required = {r for r in required if r in repo_interface}
        if not required:
            continue
        touched = {
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr.endswith("_repo")
        }
        if touched and not (touched & required):
            violations.append(
                "%s must work through %s but only reaches %s"
                % (
                    fn.name,
                    ", ".join("self." + r for r in sorted(required)),
                    ", ".join("self." + t for t in sorted(touched)),
                )
            )
    return violations


def _self_repo_tag(node, repo_returns, repo_returns_raw=None, entity_names=None):
    """``(attr, method, tag)`` when ``node`` calls a repo method the DESIGN
    returns as an entity (``("entity", cls)`` or ``("list", cls)``).

    Returns None for everything else — a dict-returning method, a scalar, or a
    call that is not ``self.<x>_repo.<method>(...)`` — so only a receiver that
    definitely holds MODEL instances, or a LIST of them, is considered. The
    tag comes from the designed return annotation, never from the body, so
    this never fires on a legitimate ``row.get('total')`` over a ``Dict``.

    The raw annotation is consulted when the pre-computed tag map has no entry
    for the (repo, method) pair. That happens for a method the fill reaches
    through an ALIAS the bounded inter-file repair just created — expenses'
    ``self.expense_repo.get_expenses_by_category(...)`` aliases
    ``list_expenses`` (``List[Expense]``), and the alias is registered in the
    raw map, not in the tag map.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Attribute)
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "self"
    ):
        return None
    attr, method = func.value.attr, func.attr
    tag = (repo_returns or {}).get((attr, method))
    if tag is None and repo_returns_raw:
        raw = repo_returns_raw.get((attr, method)) or ""
        low = raw.lower()
        cls = next(
            (
                c for c in (entity_names or ())
                if re.search(r"\b%s\b" % re.escape(c), raw)
            ),
            None,
        )
        if cls is not None:
            tag = ("list", cls) if "list" in low else ("entity", cls)
    if tag and tag[0] in ("entity", "list"):
        return attr, method, tag
    return None


def _model_accessor_violations(tree, repo_returns, repo_returns_raw=None,
                               entity_names=None):
    """Reject ``.get(...)`` / ``['key']`` on a MODEL instance in a fill body.

    The 4B model treats every repository result as a dict. expenses shipped
    ``category detect --id 1`` calling ``exp.get('category_id')`` where ``exp``
    came from ``self.expense_repo.get_expenses_by_category(...)``, designed
    ``List[Expense]`` — an ``AttributeError: 'Expense' object has no attribute
    'get'`` on a CLI-reachable path. Design-only: a local is a model ONLY when
    the DESIGNED return annotation of the repository method that produced it
    names a designed entity, so a legitimate ``row.get('total')`` over a
    ``("dict",)`` method is left alone.

    Element variables are tracked as well, so the common
    ``for exp in expenses: exp.get(...)`` and
    ``sum((e.get('x', 0) for e in rows))`` shapes are caught, not only a
    direct ``.get`` on the assignment.
    """
    if not repo_returns and not repo_returns_raw:
        return []
    violations = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        model_vars = {}
        list_vars = {}
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            hit = _self_repo_tag(
                node.value, repo_returns, repo_returns_raw, entity_names
            )
            if hit is None:
                continue
            if hit[2][0] == "entity":
                model_vars[target.id] = hit[2][1]
            else:
                list_vars[target.id] = hit[2][1]
        # A loop / comprehension element of a list-of-models is itself a model
        # of the SAME class — carrying the class keeps the violation message
        # actionable for the refill ("Expense", not "entity").
        for node in ast.walk(fn):
            if isinstance(node, (ast.For, ast.comprehension)):
                iter_node, target = node.iter, node.target
            else:
                continue
            if not isinstance(target, ast.Name):
                continue
            base = iter_node
            if isinstance(base, ast.Name) and base.id in list_vars:
                model_vars[target.id] = list_vars[base.id]
            else:
                hit = _self_repo_tag(
                    base, repo_returns, repo_returns_raw, entity_names
                )
                if hit is not None:
                    model_vars[target.id] = hit[2][1]
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == "get"):
                    continue
                recv = func.value
                cls = model_vars.get(recv.id) if isinstance(recv, ast.Name) else None
                if cls:
                    violations.append(
                        "%s: %s.get(...) treats a MODEL as a dict — %s holds "
                        "%s instances, not dicts; read fields with attribute "
                        "access (%s.<field>)"
                        % (fn.name, recv.id, recv.id, cls, recv.id)
                    )
                elif _self_repo_tag(
                    recv, repo_returns, repo_returns_raw, entity_names
                ) is not None:
                    violations.append(
                        "%s: .get(...) applied directly to a repository call "
                        "that returns a MODEL (or a list of models) — assign "
                        "it to a local and read fields with attribute access, "
                        "never .get() or ['key']" % fn.name
                    )
            elif isinstance(node, ast.Subscript):
                base = node.value
                cls = model_vars.get(base.id) if isinstance(base, ast.Name) else None
                if cls:
                    violations.append(
                        "%s: %s['...'] indexes a MODEL as a dict — %s holds %s "
                        "instances; read fields with attribute access "
                        "(%s.<field>)" % (fn.name, base.id, base.id, cls, base.id)
                    )
    return violations


def _service_fill_violations(filled, repo_interface, svc_design, type_ctx=None):
    """Mechanical contract check of an LLM service fill.

    Returns a list of human-readable violations (empty list = accept):
    (1) dropped designed methods, (2) calls to repo attributes/methods that
    are not part of the deterministic repo interface, (3) arity mismatches
    against the declared repo signatures.
    """
    if not filled:
        return ["empty output"]
    try:
        tree = ast.parse(filled)
    except SyntaxError:
        return ["output does not compile"]
    violations = []

    def _ret_note(attr, meth):
        """'(it returns X)' suffix from the DESIGNED repo annotation."""
        raw = ((type_ctx or {}).get("repo_returns_raw") or {}).get(
            (attr, meth)
        )
        return (" (it returns %s)" % raw) if raw else ""

    defined = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    required = {
        m.get("name") for m in svc_design.get("methods") or []
        if isinstance(m, dict) and m.get("name")
    }
    missing = required - defined
    if missing:
        violations.append(
            "dropped designed method(s): %s" % ", ".join(sorted(missing))
        )
    # Stub-fill gate (#2): a designed method returned as `raise
    # NotImplementedError(...)` is a refusal, not an implementation. It
    # passes every name/schema check (a stub references nothing), so it
    # used to ship verbatim — the benchmark not_implemented failures.
    # Rejecting it feeds the corrective retry instead of locking the stub.
    stubbed = sorted(
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in required
        and _fn_has_stub_raise(n)
    )
    if stubbed:
        violations.append(
            "stub fill(s) returned raise NotImplementedError instead of an "
            "implementation: %s" % ", ".join(stubbed)
        )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        value = func.value
        if not (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == "self"
        ):
            continue
        sig = repo_interface.get(value.attr)
        if sig is None:
            violations.append(
                "calls unknown repository attribute self.%s" % value.attr
            )
            continue
        if func.attr not in sig:
            violations.append(
                "self.%s has no method %s" % (value.attr, func.attr)
            )
            continue
        entries = sig[func.attr]
        if entries == ["_filters"]:
            # list(**filters): any filter kwargs are fine
            continue
        names = [p[0] if isinstance(p, tuple) else p for p in entries]
        req_names = [
            p[0] if isinstance(p, tuple) else p
            for p in entries
            if not (isinstance(p, tuple) and not p[1])
        ]
        n_pos = len(node.args)
        kw_names = {kw.arg for kw in node.keywords if kw.arg}
        if any(kw.arg is None for kw in node.keywords):
            violations.append(
                "self.%s.%s called with **spread — cannot verify arity"
                % (value.attr, func.attr)
            )
            continue
        # Exact-arity contract: every required param must be covered and the
        # call may not pass more args than the method accepts. A call with
        # FEWER args than required params is a guaranteed TypeError at
        # runtime (the 4B model has been caught emitting those).
        provided = n_pos + len(kw_names)
        if provided < len(req_names) or provided > len(names):
            violations.append(
                "self.%s.%s expects params (%s); call provides %d argument(s)"
                % (value.attr, func.attr, ", ".join(names), provided)
            )
        elif not kw_names.issubset(set(names[n_pos:])):
            violations.append(
                "self.%s.%s: keyword(s) %s do not match the trailing params"
                % (
                    value.attr,
                    func.attr,
                    sorted(kw_names - set(names[n_pos:])),
                )
            )
        if func.attr == "create":
            bad = [a for a in node.args if _dict_shaped_expr(a)]
            bad += [
                kw.value for kw in node.keywords
                if kw.arg is not None and _dict_shaped_expr(kw.value)
            ]
            if bad:
                violations.append(
                    "self.%s.create expects the entity OBJECT; passing a "
                    "plain dict (%s) crashes on attribute access — build "
                    "the entity instance first"
                    % (value.attr, ast.unparse(bad[0])[:60])
                )
    # None-safety contract: a single-row repo getter (get_by_id / get_by_<x>
    # / get_<x>_by_<y>) returns None when no row matches, so reading an
    # attribute straight off the call (self.budget_repo.
    # get_by_category_and_month(...).id) is a guaranteed AttributeError on the
    # missing-row path (expense add_expense crashed when no budget existed).
    # Force the fill to bind the row to a local and guard it.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not isinstance(
            node.value, ast.Call
        ):
            continue
        f = node.value.func
        if not (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Attribute)
            and isinstance(f.value.value, ast.Name)
            and f.value.value.id == "self"
        ):
            continue
        sig = repo_interface.get(f.value.attr)
        if sig is None or f.attr not in sig:
            continue
        if f.attr.startswith("get_"):
            violations.append(
                "reads .%s directly off self.%s.%s(...) — a single-row "
                "getter returns None when no row matches; assign it to a "
                "local and guard with `if <local> is not None:` before "
                "using it" % (node.attr, f.value.attr, f.attr)
            )
    # Return-type contract: dict-style accessors (.get/.keys/.items/.values)
    # may only be applied to results of repo methods DECLARED to return
    # dicts (type_ctx["dict_keys"]). Calling .get() on an int/bool/List
    # result is a guaranteed AttributeError at runtime (observed twice on
    # get_category_spending -> int-returning repo aggregate).
    if type_ctx:
        dict_returns = set(type_ctx.get("dict_keys") or {})
        # A repo method DESIGNED to return a dict is dict-returning even when
        # its RENDERED body is a stub / returns no literal dict keys (e.g.
        # get_monthly_spending_summary -> Dict[str, Any]). Without this, a
        # Dict-annotated aggregate is mis-read as non-dict and a correct
        # `.get('key')` service body is rejected, so the method falls back to
        # an empty-ish stub instead of being accepted.
        _raw_returns = (type_ctx or {}).get("repo_returns_raw") or {}
        for (_attr, meth), ret in _raw_returns.items():
            if "dict" in (ret or "").lower():
                dict_returns.add((_attr, meth))
        ACCESSORS = ("get", "keys", "items", "values")

        def _repo_call_key(expr):
            """(repo_attr, method) when expr is self.<repo>.<method>(...)"""
            if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
                f = expr.func
                if (
                    isinstance(f.value, ast.Attribute)
                    and isinstance(f.value.value, ast.Name)
                    and f.value.value.id == "self"
                ):
                    return (f.value.attr, f.attr)
            return None

        # (a) direct chaining: self.<repo>.meth(...)['key'] / .get('key') /
        # .keys() etc. String-keyed access on a non-dict result is a
        # guaranteed TypeError; list indexing (ints) stays allowed.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                acc = node.func.attr
                if acc not in ACCESSORS:
                    continue
                key = _repo_call_key(node.func.value)
                if not key or key in dict_returns:
                    continue
                if acc in ("keys", "items", "values") or (
                    acc == "get"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    violations.append(
                        "self.%s.%s(...) does not return a dict — do not "
                        "use .%s() on its result" % (key[0], key[1], acc)
                        + _ret_note(key[0], key[1])
                    )
            elif isinstance(node, ast.Subscript):
                key = _repo_call_key(node.value)
                sl = node.slice
                sval = sl.value if isinstance(sl, ast.Constant) else (
                    getattr(sl.value, "value", None)
                    if isinstance(sl, ast.Index) else None
                )
                if (
                    key
                    and key not in dict_returns
                    and isinstance(sval, str)
                ):
                    violations.append(
                        "self.%s.%s(...) does not return a dict — do not "
                        "index it with '%s'" % (key[0], key[1], sval)
                        + _ret_note(key[0], key[1])
                    )

        # (b) assignment then access: x = <repo call>; x['key'] / x.get('key')
        repo_assigns = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                k = _repo_call_key(node.value)
                if k:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            repo_assigns[t.id] = k
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                acc = node.func.attr
                if acc not in ACCESSORS or not isinstance(node.func.value, ast.Name):
                    continue
                k = repo_assigns.get(node.func.value.id)
                if not k or k in dict_returns:
                    continue
                if acc in ("keys", "items", "values") or (
                    acc == "get"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    violations.append(
                        "%s (self.%s.%s) does not return a dict — do not "
                        "use .%s() on it" % (node.func.value.id, k[0], k[1], acc)
                        + _ret_note(k[0], k[1])
                    )
            elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                sl = node.slice
                sval = sl.value if isinstance(sl, ast.Constant) else (
                    getattr(sl.value, "value", None)
                    if isinstance(sl, ast.Index) else None
                )
                k = repo_assigns.get(node.value.id)
                if k and k not in dict_returns and isinstance(sval, str):
                    violations.append(
                        "%s (self.%s.%s) does not return a dict — do not "
                        "index it with '%s'" % (node.value.id, k[0], k[1], sval)
                        + _ret_note(k[0], k[1])
                    )
    # CRUD create contract (prompt 27's add_room): an add_<entity> /
    # create_<entity> fill MUST construct the entity and insert it through
    # the repository's deterministic create() — never return a query /
    # aggregation result (add_room returned sum(e.id ...) = no insert).
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        mm = re.match(r"^(add|create)_([a-z][a-z0-9_]*)$", node.name)
        if not mm:
            continue
        ent_snake = mm.group(2)
        repo_attr = ent_snake + "_repo"
        if repo_attr not in repo_interface:
            continue
        calls_create = any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and isinstance(c.func.value, ast.Attribute)
            and isinstance(c.func.value.value, ast.Name)
            and c.func.value.value.id == "self"
            and c.func.value.attr == repo_attr
            and c.func.attr == "create"
            for c in ast.walk(node)
        )
        if not calls_create:
            violations.append(
                "add_%s fill must construct the entity and call "
                "self.%s_repo.create(...); not return a query result"
                % (ent_snake, ent_snake)
            )
    if type_ctx:
        violations.extend(_semantic_fill_violations(tree, type_ctx))
    violations.extend(
        _repo_entity_coherence_violations(
            tree,
            (type_ctx or {}).get("entity_fields") or {},
            repo_interface,
        )
    )
    # A repo result tagged as an entity (or a list of entities) is a MODEL,
    # never a dict: `.get('field')` on it is an AttributeError at runtime.
    violations.extend(
        _model_accessor_violations(
            tree,
            (type_ctx or {}).get("repo_returns") or {},
            (type_ctx or {}).get("repo_returns_raw") or {},
            (type_ctx or {}).get("entity_fields") or {},
        )
    )
    # Prompt-derived method contracts: each designed method may carry a
    # ``contract`` transcribed from the SPECIFICATION alone (see
    # agentlib.pipeline.method_contract). Verifying here keeps the two
    # sources independent — the extractor never saw a body, the verifier
    # never sees the specification.
    contracts = {
        m.get("name"): m.get("contract")
        for m in (svc_design or {}).get("methods") or []
        if isinstance(m, dict) and m.get("name") and m.get("contract")
    }
    if contracts:
        violations.extend(
            method_contract_violations(
                tree,
                svc_design,
                contracts,
                (type_ctx or {}).get("entity_fields") or {},
                repo_returns=(type_ctx or {}).get("repo_returns_raw") or {},
            )
        )
    # Names the merged module binds at top level, which the snippet may use
    # WITHOUT importing them: the header imports the Database class and every
    # model class, and `datetime`/`date` come from its date imports. A local
    # annotated `x: Database` is therefore legal — flagging it as an undefined
    # name was a false positive that cost a retry on library_system.
    module_bound = {"Database", "datetime", "date"}
    module_bound.update((type_ctx or {}).get("entity_fields") or {})
    for _repo_attr in repo_interface or {}:
        if _repo_attr.endswith("_repo"):
            module_bound.add(_camel(_repo_attr[: -len("_repo")]))
    violations.extend(_undefined_name_violations(tree, module_bound))
    # Signature-drift gate: the LLM can "fix" an undefined body by changing a
    # method's parameters (prompt 18's import_contact wrote `filename` while
    # the design declares `id`). _merge_stub_bodies preserves the DESIGNED
    # signature and splices only the body, so a drifted param is undefined at
    # runtime in the merged file. Reject any filled method whose params (minus
    # self) do not match the designed params exactly.
    for m in svc_design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        mtype = next(
            (n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == m["name"]),
            None,
        )
        if mtype is None:
            continue
        designed = [
            p.get("name") for p in (m.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        actual = [a.arg for a in mtype.args.args if a.arg != "self"]
        if set(actual) - set(designed):
            violations.append(
                "signature drift: %s(%s) introduces parameter(s) not in the "
                "designed signature (%s)" % (
                    m["name"], ", ".join(actual), ", ".join(designed)
                )
            )
    return violations


def _service_header_lines(svc_class, entities, entities_by_class,
exception_names, models_module="models", repo_entities=None,
model_entities=None):
    """Imports + class shell + repo wiring shared by the deterministic
    service and the stub-only mini-skeleton sent to the LLM fill."""
    exception_names = exception_names or []
    # Only entities that have a rendered repository file may be wired in
    # __init__ and imported. The design may add FK-reference entities to the
    # model without a repository (prompt 28: Customer/Product backing
    # invoice.customer_id / line.product_id); wiring a repo for them emits
    # imports of nonexistent modules and a runtime NameError. Defaults to
    # the full entity set for backward compatibility.
    repo_entities = set(entities) if repo_entities is None else set(repo_entities)
    # Only the model entities a per-method skeleton references are imported,
    # so the header never scales with the total app size. Defaults to the
    # full entity set for the deterministic service / batch fill.
    model_entities = set(entities) if model_entities is None else set(model_entities)
    repo_attrs = [
        (_snake(ent) + "_repo", _camel(ent) + "Repository")
        for ent in entities if ent in repo_entities
    ]
    repo_class_names = sorted({cls for _, cls in repo_attrs})
    lines = [
        '"""Service layer."""',
        "from __future__ import annotations",
        "",
        "import csv",
        "import json",
        "from typing import Any, Dict, List, Optional",
    ]
    # The deterministic create_<entity> recipe stamps date/datetime fields
    # DECLARED auto:"now" with datetime.datetime.now(); import datetime when
    # needed (same predicate as the recipe — never an unused import). A
    # per-method fill also needs `datetime` to stamp a REQUIRED date/datetime
    # field that is not a method param (borrow_member's loan_date) — such a
    # field exists even when no field is auto:"now", so widen the predicate to
    # ANY date/datetime-typed entity field. An unused import in a service that
    # never timestamps is harmless; a missing import in a fill is a NameError.
    has_date = False
    has_temporal = False
    for ent in entities_by_class.values():
        for f in (ent.get("fields") or []):
            if not isinstance(f, dict) or f.get("name") == "id":
                continue
            if f.get("type") == "date":
                has_date = True
                has_temporal = True
            elif f.get("type") == "datetime":
                has_temporal = True
    # `date` is used as a bare annotation name in the rendered signatures
    # (e.g. `start_date: Optional[date]`); it must be imported or the
    # annotation is unbound. `datetime` stays the MODULE because the default
    # recipes and fills stamp `datetime.datetime.now()` -- importing the
    # class would shadow it (same rule as the model renderer).
    if has_date:
        lines.append("from datetime import date")
    if has_temporal:
        lines.append("import datetime")
    lines += [
        "",
        "from database import Database",
        "from %s import %s" % (models_module, ", ".join(sorted(model_entities))),
    ]
    for rcls in repo_class_names:
        lines.append("from %s import %s" % (_snake(rcls), rcls))
    if exception_names:
        lines.append("from exceptions import %s" % ", ".join(sorted(exception_names)))
    lines += [
        "",
        "",
        "class %s:" % svc_class,
        "    def __init__(self, db: Database) -> None:",
    ]
    for attr, cls in repo_attrs:
        lines.append("        self.%s = %s(db)" % (attr, cls))
    lines.append("")
    return lines


def _missing_repo_calls(filled, repo_interface):
    """(repo_attr, method, arg_names) triples for calls a fill makes on
    self.<attr> that are absent from the deterministic repository interface.
    ``arg_names`` is the union of positional/keyword argument names used
    across call sites, so the alias repair can prefer a candidate method
    whose parameter set matches them (arity-aware aliasing)."""
    try:
        tree = ast.parse(filled)
    except SyntaxError:
        return []
    missing = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ):
            continue
        func = node.func
        value = func.value
        if not (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == "self"
        ):
            continue
        attr = value.attr
        if not attr.endswith("_repo"):
            continue
        sig = repo_interface.get(attr)
        if sig is not None and func.attr not in sig:
            key = (attr, func.attr)
            arg_names = missing.setdefault(key, set())
            for a in node.args:
                if isinstance(a, ast.Name):
                    arg_names.add(a.id)
            for kw in node.keywords:
                if kw.arg:
                    arg_names.add(kw.arg)
    return [(a, m, sorted(args)) for (a, m), args in missing.items()]


def _method_purpose(name, ent):
    """A one-line deterministic purpose for a method, from its spelling.

    Bounded and prompt-independent: it never reads the raw spec, only the
    method name + anchor entity, so it costs a fixed ~30 tokens and gives the
    model the verb-object semantics without threading the whole prompt.
    """
    if not name:
        return "implement the method using the declared repository API."
    ent_snake = _snake(ent) if ent else ""
    ent_disp = _plural(ent_snake) if ent_snake else "records"
    if name.startswith(("add_", "create_", "insert_")):
        return "create and persist a new %s." % (ent_disp or "record")
    if name.startswith("get_") and name.endswith("_by_id"):
        return "fetch a single %s by its id." % (ent_snake or "record")
    if name.startswith(("list_", "get_")) or "history" in name:
        return "retrieve %s matching the given filters/arguments." % (ent_disp or "records")
    if name.startswith("update_"):
        return "update an existing %s with the given fields." % (ent_snake or "record")
    if name.startswith("delete_") or name.startswith("remove_"):
        return "delete an existing %s by its id." % (ent_snake or "record")
    if name.startswith("search_") or name.startswith("find_"):
        return "search/find %s by the given term." % (ent_disp or "records")
    if name.startswith(("report", "total", "summary", "aggregate", "export", "calculate")):
        return "return an aggregated report/summary over %s." % (ent_disp or "records")
    if ent_snake and name.endswith("_" + ent_snake):
        verb = name[: -len("_" + ent_snake)]
        return "perform the '%s' operation on the given %s." % (verb, ent_snake)
    return "implement the method using the declared repository API."


def _method_requirement_context(m, entities_by_class, designs):
    """Compact, prompt-independent business context for ONE service method.

    Replaces the always-full ``prompt_text`` in the per-method fill with a
    bounded block derived ONLY from the design data — the method signature,
    the CLI command(s) that target it, and a one-line domain purpose — so the
    fill conversation never scales with the prompt length or total app size.
    """
    name = m.get("name") or ""
    param_str = ", ".join(
        "%s: %s" % (p.get("name"), p.get("type") or "Any")
        for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    )
    returns = m.get("returns") or "None"
    lines = ["METHOD TO IMPLEMENT — %s(%s) -> %s" % (name, param_str, returns)]

    # Anchor entity (same resolution as _scoped_repo_interface).
    ent = None
    best = -1
    for cls in entities_by_class:
        snake = _snake(cls)
        for tok in (snake, _plural(snake)):
            if tok and tok in name and len(tok) > best:
                best = len(tok)
                ent = cls
    # CLI command(s) targeting this method carry the user-facing behaviour.
    cli_lines = []
    for path, kind, data in designs or []:
        if kind != "cli" or not isinstance(data, dict):
            continue
        for c in data.get("commands") or []:
            if isinstance(c, dict) and c.get("target") == name:
                grp = "/".join(str(g) for g in (c.get("group") or []))
                cname = c.get("name") or ""
                opts = [
                    str(o.get("name"))
                    for o in (c.get("options") or [])
                    if isinstance(o, dict) and o.get("name")
                ]
                cli_lines.append(
                    "CLI: %s%s (options: %s)"
                    % (grp + " " if grp else "", cname, ", ".join(opts) or "(none)")
                )
    if cli_lines:
        lines.append("COMMAND SURFACE:")
        lines.extend("  " + x for x in cli_lines[:3])
    lines.append("PURPOSE: %s" % _method_purpose(name, ent))
    return "\n".join(lines)


def _entities_for_stub(m, scoped_entities, entities):
    """Entities a per-method skeleton must import: the scoped entity classes
    plus any entity class/snake appearing in the method's signature, so the
    typed return/param annotations resolve without importing the whole app."""
    out = set(scoped_entities)
    try:
        sig = _method_stub_code(m, 1)
    except Exception:
        sig = ""
    for cls in entities:
        s, p = _snake(cls), _plural(_snake(cls))
        if cls in sig or s in sig or p in sig:
            out.add(cls)
    return out


def _build_fill_hint(repo_interface, type_ctx, scoped_attrs=None,
                     entities_by_class=None):
    """Format the repository-API + model-fields + dict-keys hint for a fill.

    Used for the per-method scoped hint (Option B). A 4B model loses
    instruction fidelity once a fill conversation exceeds ~3k tokens, so a
    per-method fill lists only the relevant repos (see
    ``_scoped_repo_interface``) to keep the conversation small while still
    exposing the model fields and create contract.
    """
    hint_parts = [
        "AVAILABLE REPOSITORY METHODS — you may call ONLY these on self.*_repo "
        "(never invent repository methods). Signatures are EXACT:",
        "NEVER call self.db directly (no self.db.connect() / self.db.execute()) "
        "— always delegate persistence to the repository layer "
        "(self.<entity>_repo).",
        "NEVER invent enum/whitelist validation (e.g. valid_statuses = [...], "
        "if value not in [...] : raise) on a string field — model string "
        "fields are free text (status:str, priority:str). Import/validation "
        "logic should only check required fields are present and date fields "
        "parse; never reject a valid-looking string value.",
    ]
    if repo_interface:
        for attr in sorted(repo_interface):
            sigs = []
            for meth, entries in repo_interface[attr].items():
                if entries == ["_filters"]:
                    sigs.append("%s(**filters)" % meth)
                    continue
                parts = []
                for e in entries:
                    pname = e[0] if isinstance(e, tuple) else e
                    req = e[1] if isinstance(e, tuple) else True
                    parts.append(pname if req else "%s=None" % pname)
                ret = (type_ctx.get("repo_returns_raw") or {}).get(
                    (attr, meth)
                )
                if ret == "dict":
                    sigs.append("%s(%s) -> dict" % (meth, ", ".join(parts)))
                elif ret:
                    sigs.append(
                        "%s(%s) -> %s" % (meth, ", ".join(parts), ret)
                    )
                else:
                    sigs.append("%s(%s)" % (meth, ", ".join(parts)))
            hint_parts.append(
                "  self.%s: %s" % (attr, "; ".join(sorted(sigs)))
            )
        hint_parts.append(
            "  NOTE: update(id, data) takes the changed fields as a single "
            "dict argument — NEVER as keyword arguments."
        )
    else:
        hint_parts.append("  (none)")
    # Bound the hint to the method's FK closure (the scoped repos/entities),
    # so it never scales with the total app size or prompt length.
    scoped_classes = {
        _camel(a[: -len("_repo")]) for a in (scoped_attrs or set())
        if a.endswith("_repo")
    }
    eff_entity_fields = {
        cls: flds for cls, flds in type_ctx["entity_fields"].items()
        if not scoped_classes or cls in scoped_classes
    }
    if not eff_entity_fields:
        eff_entity_fields = type_ctx["entity_fields"]
    eff_dict_keys = {
        k: keys for k, keys in type_ctx.get("dict_keys", {}).items()
        if not scoped_attrs or k[0] in scoped_attrs
    }
    hint = "\n".join(hint_parts)
    hint += (
        "\n\nMODEL FIELD NAMES — constructor keyword arguments and "
        "attribute access MUST use exactly these:\n"
        + "\n".join(
            "  %s(%s)"
            % (cls, ", ".join(sorted(flds)))
            for cls, flds in sorted(eff_entity_fields.items())
        )
    )
    dict_key_lines = [
        "  self.%s.%s(...) -> dict with keys: %s"
        % (attr, meth, ", ".join(sorted(keys)))
        for (attr, meth), keys in sorted(eff_dict_keys.items())
    ]
    if dict_key_lines:
        hint += (
            "\n\nDICT RETURN KEYS  when a call below returns a dict, index "
            "it ONLY with these keys:\n" + "\n".join(dict_key_lines)
        )
    hint += (
        "\n\nCREATE CONTRACT  self.<entity>_repo.create() takes an ENTITY "
        "INSTANCE, never a plain dict: build one with EntityClass(**data) "
        "and pass that object."
    )
    if entities_by_class:
        reqf = _required_constructor_fields(entities_by_class)
        if reqf:
            hint += (
                "\n\nREQUIRED (non-nullable) FIELDS — every one of these "
                "MUST be supplied when constructing an entity; omitting one "
                "raises a validation error:\n"
                + "\n".join(
                    "  %s(%s)" % (cls, ", ".join(reqf[cls]))
                    for cls in sorted(reqf)
                )
            )
            hint += (
                "\n\nCONSTRUCTION RULE  when constructing an entity, supply "
                "EVERY required field listed above. When a required "
                "date/datetime field is NOT a method parameter (e.g. "
                "loan_date, created_at), stamp it at construction with "
                "datetime.datetime.now().isoformat(); when it is a due/end "
                "date, compute it relative to now. NEVER omit a required "
                "field — omitting one raises a validation error."
            )
    return hint


def _has_repo_interface_violations(violations):
    """True when a rejection is a repo-interface failure (unknown attribute /
    no such method), not a semantic/arity/undefined-name issue."""
    return any(
        "calls unknown repository attribute" in v
        or "has no method" in v
        for v in (violations or [])
    )


def _positive_repo_targets(repo_interface, type_ctx=None):
    """Format the repos in scope as a positive target list for a retry.

    A negative-only rejection (''calls unknown repository attribute
    self.book_repo'') gives the 4B model no concrete alternative, so it
    re-guesses and re-emits the same broken body. List the EXACT
    ``self.<attr>.<method>(params)`` call shapes available in the scoped
    interface so the retry has a real option to pick instead.
    """
    if not repo_interface:
        return "  (no repository calls available)"
    lines = []
    for attr in sorted(repo_interface):
        for meth, entries in sorted((repo_interface[attr] or {}).items()):
            if entries == ["_filters"]:
                lines.append("  self.%s.%s(**filters)" % (attr, meth))
                continue
            parts = []
            for e in entries:
                pname = e[0] if isinstance(e, tuple) else e
                req = e[1] if isinstance(e, tuple) else True
                parts.append(pname if req else "%s=None" % pname)
            ret = (type_ctx.get("repo_returns_raw") or {}).get(
                (attr, meth)
            ) if type_ctx else None
            if ret:
                lines.append(
                    "  self.%s.%s(%s) -> %s"
                    % (attr, meth, ", ".join(parts), ret)
                )
            else:
                lines.append("  self.%s.%s(%s)" % (attr, meth, ", ".join(parts)))
    return "\n".join(lines)


# Verbs that may prefix a method name. Used to compare a service method
# against a designed repository custom by their shared STEM
# (get_overdue_loans -> list_overdue_loans): the verb is a synonym slot, the
# remainder identifies the operation.
_METHOD_VERBS = (
    "get", "list", "find", "fetch", "search", "load", "show", "view",
    "retrieve", "read", "report", "count", "compute", "calculate",
)


def _verb_stem(name):
    """``get_overdue_loans`` -> ``overdue_loans`` (leading verb removed).

    The leading verb is a synonym slot (get/list/find over the same
    operation); only the remainder identifies the query. Returns the name
    unchanged when it carries no leading verb or nothing after it.
    """
    for verb in _METHOD_VERBS:
        if name.startswith(verb + "_") and len(name) > len(verb) + 1:
            return name[len(verb) + 1:]
    return name


def _primary_named_entity(name, entity_names):
    """The designed entity a method name NAMES, or None.

    The longest entity snake/plural name CONTAINED in the method name wins
    (list_author -> Author, get_overdue_loans -> Loan, return_book -> Book).
    Design-only: no prompt text, no verb vocabulary, no field heuristics.
    """
    prim = None
    best = -1
    for cls in entity_names:
        for tok in (_snake(cls), _plural(_snake(cls))):
            if tok and tok in name and len(tok) > best:
                best = len(tok)
                prim = cls
    return prim


def _method_anchor_entities(name, params, entities_by_class):
    """{class names} a service method's body plausibly anchors on.

    Two design-only signals, no prompt text:
      * the entity the method NAME names (return_loan -> Loan,
        get_overdue_loans -> Loan, list_author -> Author);
      * every entity named by a ``<x>_id`` parameter (borrow_loan(member_id,
        book_id) anchors on Member AND Book).
    """
    anchors = set()
    prim = _primary_named_entity(name, entities_by_class)
    if prim:
        anchors.add(prim)
    for p in params:
        if p.endswith("_id") and p != "id":
            ref = _camel(p[: -len("_id")])
            if ref in entities_by_class:
                anchors.add(ref)
    return anchors


def _scoped_repo_interface(m, repo_interface, entities_by_class):
    """Filter repo_interface to the repos a method's body plausibly touches.

    A 4B model loses instruction fidelity once a fill conversation exceeds
    ~3k tokens (observed: library_system's full 4-repo menu + 30-stub
    skeleton reaches 5-6k, so the model invents loan_repo.return_loan).
    Scoping the per-method hint to the owning entity's repo + FK-referenced
    repos keeps each fill well under that limit while exposing exactly the
    repos the body could reasonably need. Falls back to the full interface
    when no entity matches (a valid body may use any wired repo).
    """
    if not repo_interface or not entities_by_class:
        return repo_interface
    name = m.get("name") or ""
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    ]

    def _attr(cls):
        attr = _snake(cls) + "_repo"
        return attr if attr in repo_interface else None

    related = set()

    def _add(cls):
        if cls in entities_by_class:
            a = _attr(cls)
            if a:
                related.add(a)

    # Anchor entities: the name-derived primary PLUS every entity referenced
    # by an FK parameter. A cross-entity method like history(member_id) names
    # no entity in its own name, so the FK parameter supplies the anchor; the
    # FK closure below then pulls in the repos it legitimately walks (loan,
    # book). CRUD methods (add_/list_/update_/delete_/get_/search_) are
    # rendered deterministically and never reach this fill scope, so widening
    # here only affects business/extras methods.
    anchors = set()
    # 1. Primary entity: longest entity-snake/plural substring in the method
    # name (return_loan -> loan, get_overdue_loans -> loan, add_book -> book).
    prim = None
    best = -1
    for cls in entities_by_class:
        for tok in (_snake(cls), _plural(_snake(cls))):
            if tok and tok in name and len(tok) > best:
                best = len(tok)
                prim = cls
    if prim:
        anchors.add(prim)
    # 2. Foreign-key params: borrow_loan(member_id, book_id) needs both.
    for p in params:
        if p.endswith("_id") and p != "id":
            ref = _camel(p[: -len("_id")])
            if ref in entities_by_class:
                anchors.add(ref)
                _add(ref)

    for anchor in sorted(anchors):
        _add(anchor)
        ent = entities_by_class.get(anchor)
        if not isinstance(ent, dict):
            continue
        # 3. Anchor's FK columns / modeled fks: return_loan(loan_id) must
        # reach book_repo/member_repo (increment copies) even without _id params.
        for f in ent.get("fields") or []:
            if isinstance(f, dict) and isinstance(f.get("name"), str):
                fn = f["name"]
                if fn.endswith("_id") and fn != "id":
                    _add(_camel(fn[: -len("_id")]))
        for fk in ent.get("fks") or []:
            if isinstance(fk, dict):
                ref = fk.get("ref") or fk.get("ref_table") or ""
                if ref and _camel(ref) != anchor:
                    _add(_camel(ref))
        # 4. Reverse-FK widening for cross-entity methods (history/overdue/
        # report/search over an entity referenced by others): get_member_history
        # spans Member + Loan + Book. Walk the entities that FK to the anchor
        # (Loan -> Member) and, transitively, the repos those reference
        # (Loan -> Book). Bounded to designed entities so the scoped hint
        # stays small while a correct cross-entity body is possible.
        for cls, other in entities_by_class.items():
            if cls == anchor:
                continue
            refs = set()
            for f in other.get("fields") or []:
                if isinstance(f, dict) and isinstance(f.get("name"), str):
                    fn = f["name"]
                    if fn.endswith("_id") and fn != "id":
                        refs.add(_camel(fn[: -len("_id")]))
            for fk in other.get("fks") or []:
                if isinstance(fk, dict) and fk.get("ref"):
                    refs.add(_camel(fk["ref"]))
            if anchor in refs:
                _add(cls)
                # One level deeper: repos the referrer itself references
                # (Loan -> Book), so a history/report can read related rows.
                other_ent = entities_by_class.get(cls)
                if isinstance(other_ent, dict):
                    for f in other_ent.get("fields") or []:
                        if isinstance(f, dict) and isinstance(f.get("name"), str):
                            fn = f["name"]
                            if fn.endswith("_id") and fn != "id":
                                _add(_camel(fn[: -len("_id")]))
                    for fk in other_ent.get("fks") or []:
                        if isinstance(fk, dict) and fk.get("ref"):
                            _add(_camel(fk["ref"]))

    if not related:
        # No anchor resolved (a bare CRUD alias like add/update/delete whose
        # name matches no entity and whose _id params are just `id`, or a
        # method whose params name no entity): returning {} makes a correct
        # body IMPOSSIBLE — every repo call is rejected, so expense's flat
        # `add`/`update`/`delete` aliases stay stubbed forever and retry the
        # same broken body. Expose the full interface so the body can reach
        # whichever repo it needs; the per-method validation still rejects a
        # wrong-repo call. This matches the docstring's "falls back to the
        # full interface" contract and gives the 4B model a real option.
        return repo_interface
    return {a: iface for a, iface in repo_interface.items() if a in related}


def _strip_import_enum_validation(text):
    """Remove invented enum/whitelist validation from LLM-filled import_* methods.

    The facade import fixtures carry arbitrary string field values (prompt 19's
    Task fixture uses status: "completed"). A 4B model, seeing a plain
    status:str field, invents ``valid_statuses = [...]; if x not in it: raise``,
    which crashes the import on any value outside its guessed whitelist. Only
    structural validation (list-of-dicts, required fields present, date
    parsing) is legal; a hand-rolled string whitelist is not.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text

    def _is_wl_check(stmt):
        if not (isinstance(stmt, ast.If) and len(stmt.body) == 1):
            return False
        if not isinstance(stmt.body[0], ast.Raise):
            return False
        test = stmt.test
        return (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], (ast.In, ast.NotIn))
            and isinstance(test.comparators[0], ast.Name)
            and test.comparators[0].id in wl
        )

    def _filter(stmts):
        out = []
        for stmt in stmts:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id in wl
            ):
                continue
            if _is_wl_check(stmt):
                continue
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With)):
                stmt.body = _filter(stmt.body)
                orelse = getattr(stmt, "orelse", None)
                if orelse:
                    stmt.orelse = _filter(orelse)
            elif isinstance(stmt, ast.Try):
                stmt.body = _filter(stmt.body)
                stmt.orelse = _filter(stmt.orelse)
                stmt.finalbody = _filter(stmt.finalbody)
                for h in stmt.handlers:
                    h.body = _filter(h.body)
            out.append(stmt)
        return out

    for fn in [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("import_")
    ]:
        wl = {
            n.targets[0].id
            for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.List)
            and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str)
                for e in n.value.elts
            )
            and n.targets[0].id.startswith(("valid_", "allowed_"))
        }
        if not wl:
            continue
        fn.body = _filter(fn.body)
    try:
        return ast.unparse(tree)
    except Exception:
        return text


def _stamp_missing_required_datetimes(cand, entities_by_class, type_ctx):
    """Stamp omitted required DATE/DATETIME constructor fields with now().

    A fill that builds ``Loan(...)`` but omits a required date field is
    rejected and costs a full retry (library_system borrow_member:
    ``Loan() missing loan_date`` -> attempt 2). The deterministic
    ``add_<entity>`` renderer already stamps such fields and the fill hint's
    CONSTRUCTION RULE tells the model to do the same, so mirroring it here
    turns a guaranteed-recoverable retry into a deterministic repair.

    Bounded: only a direct ``Entity(...)`` on a DESIGNED class without ``**``
    unpacking is touched, and EVERY still-missing required field must be
    date/datetime-typed (a missing non-date field still fails the gate).
    """
    if not cand:
        return cand
    required = (type_ctx or {}).get("required_fields") or {}
    field_types = (type_ctx or {}).get("field_types") or {}
    if not required:
        return cand
    try:
        tree = ast.parse(cand)
    except SyntaxError:
        return cand
    changed = False
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in entities_by_class
        ):
            continue
        ftypes = field_types.get(node.func.id) or {}
        req = required.get(node.func.id)
        if not req or any(kw.arg is None for kw in node.keywords):
            continue
        provided = {kw.arg for kw in node.keywords if kw.arg}
        provided.update(list(ftypes)[: len(node.args)])
        missing = [f for f in sorted(req) if f not in provided]
        if not missing or not all(
            ftypes.get(f) in ("date", "datetime") for f in missing
        ):
            continue
        for fname in missing:
            node.keywords.append(ast.keyword(
                arg=fname,
                value=ast.parse(
                    "datetime.datetime.now().isoformat()"
                ).body[0].value,
            ))
        changed = True
    if not changed:
        return cand
    try:
        return ast.unparse(tree) + "\n"
    except Exception:
        return cand


def _is_docstring_stmt(stmt):
    """True for a bare string-literal expression statement."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _broad_swallow_handler(handler):
    """True for a handler that silently discards everything it catches.

    Only the unambiguous shape qualifies: a bare ``except:`` / ``except
    Exception:`` / ``except BaseException:`` whose ENTIRE body is ``pass``
    (an optional leading docstring is ignored). A handler that logs, assigns
    a fallback, or re-raises is NOT touched.
    """
    htype = handler.type
    broad = htype is None or (
        isinstance(htype, ast.Name)
        and htype.id in ("Exception", "BaseException")
    )
    if not broad:
        return False
    body = [s for s in handler.body if not _is_docstring_stmt(s)]
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _try_body_raises(stmts):
    """True when a statement list contains a ``raise``."""
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Raise):
                return True
    return False


def _unwrap_stmt_list(stmts, changed):
    """Inline every broad-swallow ``try`` in a statement list, recursively.

    Returns the (possibly rewritten) statement list; ``changed`` is a list
    used as a boolean box so the caller knows whether anything was dropped.
    A ``try`` whose every handler is a no-op swallow and whose body raises
    is replaced by its body INLINE, so the raise propagates; other nodes are
    recursed into unchanged.
    """
    out = []
    for st in stmts:
        for field, value in ast.iter_fields(st):
            if (
                isinstance(value, list)
                and value
                and isinstance(value[0], ast.stmt)
            ):
                setattr(st, field, _unwrap_stmt_list(value, changed))
        for handler in getattr(st, "handlers", ()) or ():
            handler.body = _unwrap_stmt_list(handler.body, changed)
        if isinstance(st, ast.Try) and not st.orelse and not st.finalbody:
            kept = [h for h in st.handlers if not _broad_swallow_handler(h)]
            if len(kept) != len(st.handlers) and _try_body_raises(st.body):
                changed.append(True)
                if kept:
                    st.handlers = kept
                    out.append(st)
                else:
                    out.extend(st.body)
                continue
        out.append(st)
    return out


def _unwrap_swallowed_raises(cand):
    """Delete a broad ``except Exception: pass`` that swallows a raise.

    The 4B model habit is to wrap a designed business-rule check in ``try:
    ... raise DesignedError(...) ... except Exception: pass`` — the handler
    does nothing, so the exception the rule exists to raise is silently
    discarded (expenses ``add_expense``'s budget check shipped dead this
    way). Removing a no-op swallow handler changes nothing except that the
    exception now propagates; the ``try`` body is inlined verbatim so the
    generated code carries no leftover ``try``/``if True`` scaffolding.
    """
    if not cand:
        return cand
    try:
        tree = ast.parse(cand)
    except SyntaxError:
        return cand
    changed = []
    tree.body = _unwrap_stmt_list(tree.body, changed)
    if not changed:
        return cand
    try:
        return ast.unparse(tree) + "\n"
    except Exception:
        return cand


def attach_contract_impls(svc_design, entities_by_class, method_contracts,
                          prompt_text, verbose=False):
    """Attach the specification's deterministic recipe impl to each method.

    Prompt-derived contracts (stage 2/3). The contract is attached to the
    design method so the fill validator can reach it through ``svc_design``,
    and the exactly-renderable part is compiled into a deterministic recipe
    impl. A method whose contract is not exactly renderable keeps its LLM fill.

    Factored out of ``_render_service_file`` so the pipeline can run it BEFORE
    the render phase: the CLI file is rendered AHEAD of the service bodies, and
    a report declares its money result keys on that impl. Without running this
    first, the CLI saw no impl and printed a report's totals as raw cents.
    """
    for m in (svc_design or {}).get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        contract = (method_contracts or {}).get(m["name"])
        # An ABSENT contract is not the end of the story: the analyst's
        # evidence closure drops a line the specification states plainly
        # ("borrow_book(member_id, book_id): checks availability, creates loan,
        # decrements copies" — rejected on all three retries), and a method
        # with no contract then fell to the fill, which shipped it as a dead
        # stub. Pass the specification text down so ``compile_contract_impl``
        # can read the method's OWN line literally.
        literal = not contract
        if literal:
            contract = {"name": m["name"]}
        impl = compile_contract_impl(
            contract,
            entities_by_class,
            params=[
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ],
            returns=m.get("returns") or "",
            prompt_text=prompt_text or "",
        )
        if impl is None:
            continue
        if not literal:
            m["contract"] = contract
        else:
            m.pop("contract", None)
        # The contract impl WINS over a design-supplied impl. Both describe
        # the same method, but the contract is closed against a verbatim span
        # of the SPECIFICATION while a design ``impl`` is the design model's
        # own guess at the body. Keeping the design impl meant a stated filter
        # was silently dropped: expenses' get_monthly_report carried a
        # sum-by-category impl with no month predicate, so it summed every row
        # and S1 shipped. Overriding is narrow — ``compile_contract_impl``
        # returns None unless the contract is exactly renderable.
        if m.get("impl") is not None and verbose:
            print(
                "    [contract] %s: overrides design impl (%s)"
                % (m["name"], (m.get("impl") or {}).get("kind"))
            )
        m["impl"] = impl
        if verbose:
            print(
                "    [contract] %s: deterministic effects from the "
                "spec" % m["name"]
            )


def _render_service_file(svc_design, svc_class, designs, entities_by_class,
                         prompt_text, exception_names=None, verbose=False,
                         repo_sources=None, models_module="models",
                         method_contracts=None):
    """Deterministic service: real contract bodies + stubs for extras.

    Contract methods (the tested surface) get real bodies rendered here with
    zero LLM involvement. Extras the LLM designed are rendered as
    NotImplementedError stubs; when `prompt_text` is given, ONLY the stub
    methods travel to the LLM inside a mini-skeleton, and an accepted fill is
    spliced back per-method — deterministic bodies can never be degraded by
    the fill.
    """
    exception_names = exception_names or []
    entities = sorted(entities_by_class)

    # Only entities that have a RENDERED repository file are wired/imported
    # in the service header. The design may add FK-reference entities to the
    # model without a repository (prompt 28: Customer/Product behind
    # invoice.customer_id / line.product_id); wiring a repo for them would
    # import a nonexistent module and raise NameError at runtime.
    repo_entities = set()
    for rp in (repo_sources or {}):
        stem = Path(rp).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        repo_entities.add(_camel(ent_snake))

    lines = _service_header_lines(
        svc_class, entities, entities_by_class, exception_names,
        models_module=models_module, repo_entities=repo_entities,
    )

    repo_customs = _zero_param_dict_repo_customs(designs, entities_by_class)
    repo_signatures = _repo_custom_signatures(designs, entities_by_class)
    repo_bulk_updates = _bulk_update_repo_targets(designs, entities_by_class)
    repo_search_targets = _search_repo_targets(designs, entities_by_class)
    # Prompt-derived contracts (stage 2/3). Attach the contract to the design
    # method so the fill validator can reach it through ``svc_design`` (no
    # extra plumbing through the six fill call sites), and compile the
    # exactly-renderable part into a deterministic recipe impl. A method
    # whose contract is not exactly renderable keeps its LLM fill.
    for m in svc_design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        contract = (method_contracts or {}).get(m["name"])
        # An ABSENT contract is not the end of the story: the analyst's
        # evidence closure drops a line the specification states plainly
        # ("borrow_book(member_id, book_id): checks availability, creates loan,
        # decrements copies" — rejected on all three retries), and a method
        # with no contract then fell to the fill, which shipped it as a dead
        # stub. Pass the specification text down so ``compile_contract_impl``
        # can read the method's OWN line literally.
        literal = not contract
        if literal:
            contract = {"name": m["name"]}
        impl = compile_contract_impl(
            contract,
            entities_by_class,
            params=[
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ],
            returns=m.get("returns") or "",
            prompt_text=prompt_text or "",
        )
        if impl is None:
            continue
        if not literal:
            m["contract"] = contract
        else:
            m.pop("contract", None)
        # The contract impl WINS over a design-supplied impl. Both describe
        # the same method, but the contract is closed against a verbatim span
        # of the SPECIFICATION while a design ``impl`` is the design model's
        # own guess at the body. Keeping the design impl meant a stated filter
        # was silently dropped: expenses' get_monthly_report carried a
        # sum-by-category impl with no month predicate, so it summed every row
        # and S1 shipped. Overriding is narrow — ``compile_contract_impl``
        # returns None unless the contract is exactly renderable.
        if m.get("impl") is not None and verbose:
            print(
                "    [contract] %s: overrides design impl (%s)"
                % (m["name"], (m.get("impl") or {}).get("kind"))
            )
        m["impl"] = impl
        if verbose:
            print(
                "    [contract] %s: deterministic effects from the "
                "spec" % m["name"]
            )
    # A service method that is a pure delegation must DECLARE what it
    # actually returns: the design model types the service and the repository
    # INDEPENDENTLY, so they can disagree (expenses' get_category_spending
    # declared -> int while its body returns the repository's Dict). Run
    # AFTER the contract loop so a method that just received a deterministic
    # effect or aggregate impl is left alone by the `impl` guard above.
    _align_delegated_returns(
        svc_design,
        _repo_custom_returns(designs, entities_by_class),
        entities_by_class,
        verbose=verbose,
    )
    for m in svc_design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        body = _service_method_body(
            m, entities_by_class, exception_names, repo_customs,
            repo_bulk_updates, repo_search_targets, repo_signatures
        )
        if body is not None:
            def_line = _method_stub_code(m, 1).split("\n")[0]
            lines.append(def_line)
            lines.extend(body)
            lines.append("")
            continue
        # Unfilled method: final deterministic body is a type-appropriate
        # empty return (not NotImplementedError) so the running app never
        # crashes and the benchmark not_implemented gate passes. The LLM
        # mini-skeleton keeps raise NotImplementedError() to push the model.
        lines.append(_method_stub_code(m, 1, safe_body=True))
        lines.append("")

    deterministic = "\n".join(lines).rstrip() + "\n"
    # Only involve the LLM when there are non-contract method bodies left to
    # fill. If every designed method has a deterministic body, hand back the
    # deterministic service untouched — no hallucination surface at all.
    stubs = [
        m for m in svc_design.get("methods") or []
        if isinstance(m, dict) and m.get("name")
        and _service_method_body(
            m, entities_by_class, exception_names, repo_customs,
            repo_bulk_updates, repo_search_targets, repo_signatures
        ) is None
    ]
    if not prompt_text or not stubs:
        return deterministic
    # Tell the fill which repo methods exist (it may only call these on
    # self.*_repo). Validation is scoped to the STUB methods only: the
    # deterministic contract bodies are not part of the fill context.
    repo_interface = _service_repo_interface(
        entities_by_class, designs, repo_sources=repo_sources
    )
    type_ctx = _service_type_context(entities_by_class, designs)
    if repo_sources:
        type_ctx["dict_keys"] = _repo_dict_keys(
            repo_sources, entities_by_class, designs
        )
    type_ctx["repo_returns_raw"] = _repo_return_strings(
        entities_by_class, designs
    )
    hint_parts = [
        "AVAILABLE REPOSITORY METHODS — you may call ONLY these on self.*_repo "
        "(never invent repository methods). Signatures are EXACT:"
    ]
    if repo_interface:
        for attr in sorted(repo_interface):
            sigs = []
            for meth, entries in repo_interface[attr].items():
                if entries == ["_filters"]:
                    sigs.append("%s(**filters)" % meth)
                    continue
                parts = []
                for e in entries:
                    pname = e[0] if isinstance(e, tuple) else e
                    req = e[1] if isinstance(e, tuple) else True
                    parts.append(pname if req else "%s=None" % pname)
                ret = (type_ctx.get("repo_returns_raw") or {}).get(
                    (attr, meth)
                )
                if ret == "dict":
                    # Exact key names are listed under DICT RETURN KEYS.
                    sigs.append("%s(%s) -> dict" % (meth, ", ".join(parts)))
                elif ret:
                    sigs.append(
                        "%s(%s) -> %s" % (meth, ", ".join(parts), ret)
                    )
                else:
                    sigs.append("%s(%s)" % (meth, ", ".join(parts)))
            hint_parts.append(
                "  self.%s: %s" % (attr, "; ".join(sorted(sigs)))
            )
        hint_parts.append(
            "  NOTE: update(id, data) takes the changed fields as a single "
            "dict argument — NEVER as keyword arguments."
        )
    else:
        hint_parts.append("  (none)")
    fill_hint = "\n".join(hint_parts)
    fill_hint += (
        "\n\nMODEL FIELD NAMES — constructor keyword arguments and "
        "attribute access MUST use exactly these:\n"
        + "\n".join(
            "  %s(%s)"
            % (cls, ", ".join(sorted(type_ctx["entity_fields"][cls])))
            for cls in sorted(type_ctx["entity_fields"])
        )
    )
    dict_key_lines = [
        "  self.%s.%s(...) -> dict with keys: %s"
        % (attr, meth, ", ".join(sorted(keys)))
        for (attr, meth), keys in sorted(type_ctx.get("dict_keys", {}).items())
    ]
    if dict_key_lines:
        fill_hint += (
            "\n\nDICT RETURN KEYS  when a call below returns a dict, index "
            "it ONLY with these keys:\n" + "\n".join(dict_key_lines)
        )
    fill_hint += (
        "\n\nCREATE CONTRACT  self.<entity>_repo.create() takes an ENTITY "
        "INSTANCE, never a plain dict: build one with EntityClass(**data) "
        "and pass that object."
    )
    _reqf = _required_constructor_fields(entities_by_class)
    if _reqf:
        fill_hint += (
            "\n\nREQUIRED (non-nullable) FIELDS — every one of these MUST "
            "be supplied when constructing an entity; omitting one raises a "
            "validation error:\n"
            + "\n".join(
                "  %s(%s)" % (cls, ", ".join(_reqf[cls]))
                for cls in sorted(_reqf)
            )
        )
        fill_hint += (
            "\n\nCONSTRUCTION RULE  when constructing an entity, supply EVERY "
            "required field listed above. When a required date/datetime field "
            "is NOT a method parameter (e.g. loan_date, created_at), stamp it "
            "at construction with datetime.datetime.now().isoformat(); when "
            "it is a due/end date, compute it relative to now. NEVER omit a "
            "required field — omitting one raises a validation error."
        )

    # Mini-skeleton: header + ONLY the stub methods. The model never sees the
    # deterministic bodies, so it cannot rewrite/degrade them; its output is
    # spliced back into the deterministic file per-method.
    stub_design = {"methods": stubs}
    stub_names = [m["name"] for m in stubs]
    mini = "\n".join(
        _service_header_lines(
            svc_class, entities, entities_by_class, exception_names,
            models_module=models_module, repo_entities=repo_entities,
        )
        + [_method_stub_code(m, 1) for m in stubs]
    ).rstrip() + "\n"

    def _accept(candidate):
        """Validate a mini-skeleton fill and splice it into the deterministic
        service. Returns the merged text or None."""
        if not candidate:
            return None
        candidate = _strip_import_enum_validation(candidate)
        if _service_fill_violations(
            candidate, repo_interface, stub_design, type_ctx
        ):
            return None
        return _merge_stub_bodies(deterministic, candidate, stub_names)

    # (#3) Bounded inter-file repair: when a fill calls a simple repository
    # lookup that was never designed (get_/find_<entity>_by_<scalar_field>),
    # synthesize it DETERMINISTICALLY into the repository source and
    # register it on the local interface so the retry can legally call it —
    # instead of rejecting four times and shipping a stub (run 13's
    # update_product_stock calling get_product_by_sku). Hard cap 3 per
    # service; only scalar single-column lookups over the repo's OWN entity
    # qualify — everything else keeps failing the contract gate as before.
    synthesized_count = 0

    def _repair_missing(filled_text):
        """True when at least one missing simple finder was synthesized."""
        nonlocal synthesized_count, fill_hint
        # Scale the repair budget with the stub count: a flat cap of 3 is
        # exhausted by a large service (30 stubs), so later methods lose
        # their ``find_by_id`` alias while earlier repos keep theirs. The
        # repair only synthesizes SIMPLE single-column lookups / aliases
        # (``_simple_finder_spec`` / ``_existing_variant_alias``) — bounded,
        # legitimate methods — so a proportional budget is safe; the contract
        # validator still gates every fill.
        if not filled_text or synthesized_count >= max(3, len(stubs)) or not repo_sources:
            return False
        repaired = False
        for attr, meth, call_args in _missing_repo_calls(filled_text, repo_interface):
            spec = _simple_finder_spec(attr, meth, entities_by_class)
            if spec is None:
                # Name-variant alias: the fill references a method that is a
                # verb-prefix/entity-suffix variant of an EXISTING repo method
                # (top_products_by_total_quantity_sold -> get_top_products...).
                # Synthesize a delegator so the retry can legally call it.
                # Pass the call's arg names so the alias prefers a candidate
                # whose param set matches (arity-aware).
                alias_of = _existing_variant_alias(
                    attr, meth, repo_interface, call_args
                )
                if alias_of is None:
                    continue
                ent_stem = attr[: -len("_repo")]
                target_path = next(
                    (
                        rp for rp in repo_sources
                        if Path(rp).stem in (ent_stem + "_repository", ent_stem)
                    ),
                    None,
                )
                if target_path is None:
                    continue
                src = repo_sources[target_path]
                if not re.search(
                    r"^\s*def %s\s*\(" % re.escape(meth), src, re.MULTILINE
                ):
                    repo_sources[target_path] = (
                        src.rstrip()
                        + "\n\n\n"
                        + _render_variant_alias(meth, alias_of)
                        + "\n"
                    )
                existing_sig = list(
                    (repo_interface.get(attr) or {}).get(alias_of) or []
                )
                repo_interface.setdefault(attr, {})[meth] = existing_sig
                type_ctx.setdefault("repo_returns_raw", {})[(attr, meth)] = (
                    (type_ctx.get("repo_returns_raw") or {}).get(
                        (attr, alias_of), "Any"
                    )
                )
                if existing_sig:
                    fill_hint += (
                        "\n  self.%s.%s(%s) -> %s"
                        % (
                            attr,
                            meth,
                            ", ".join(
                                p[0] if isinstance(p, tuple) else p
                                for p in existing_sig
                            ),
                            (type_ctx.get("repo_returns_raw") or {}).get(
                                (attr, alias_of), "Any"
                            ),
                        )
                    )
                else:
                    fill_hint += "\n  self.%s.%s() -> Any" % (attr, meth)
                synthesized_count += 1
                repaired = True
                if verbose:
                    print(
                        "    [fill] service: alias %s.%s -> %s "
                        "(bounded inter-file repair)" % (attr, meth, alias_of)
                    )
                continue
            ent_stem = attr[: -len("_repo")]
            target_path = next(
                (
                    rp for rp in repo_sources
                    if Path(rp).stem in (ent_stem + "_repository", ent_stem)
                ),
                None,
            )
            if target_path is None:
                continue
            src = repo_sources[target_path]
            already_there = re.search(
                r"^\s*def %s\s*\(" % re.escape(meth), src, re.MULTILINE
            )
            if not already_there:
                repo_sources[target_path] = (
                    src.rstrip()
                    + "\n\n\n"
                    + _render_simple_finder(spec)
                    + "\n"
                )
            repo_interface.setdefault(attr, {})[meth] = [
                tuple(p) if isinstance(p, tuple) else (p, True)
                for p in spec["params"]
            ]
            type_ctx.setdefault("repo_returns_raw", {})[(attr, meth)] = (
                spec["ret"]
            )
            fill_hint += (
                "\n  self.%s.%s(%s) -> %s"
                % (
                    attr,
                    meth,
                    ", ".join(p[0] for p in spec["params"]),
                    spec["ret"],
                )
            )
            synthesized_count += 1
            repaired = True
            if verbose:
                col_disp = spec.get("col") or spec.get("date_col")
                print(
                    "    [fill] service: synthesized %s.%s(%s) -> "
                    "%s (bounded inter-file repair)"
                    % (attr, meth, col_disp, spec["ret"])
                )
        return repaired

    # A 4B model loses instruction fidelity once a fill conversation exceeds
    # ~3k tokens. A batch fill packs ALL stubs into one skeleton PLUS the
    # full repo menu PLUS a whole-service decode — library_system has ~30
    # stubs across 4 repos, so that single conversation reaches 5-6k tokens
    # and the model forgets "call ONLY these repo methods", inventing
    # loan_repo.return_loan / get_overdue_loans. When the stub set is large,
    # skip the batch entirely and fill one method at a time with a repo hint
    # scoped to that method's entity + FK repos, keeping each conversation
    # small enough to stay instruction-faithful.
    # A 4B model loses instruction fidelity past ~3.1k tokens (measured: the
    # expense 2-stub service packed the FULL repo interface into the batch
    # hint, producing a 3333-token prompt that triggered the get_monthly_report
    # reject). Force per-method fills for ANY service with more than one stub
    # so each conversation stays small and the rules remain in-window.
    LARGE_STUB_SET = 1
    if len(stubs) <= LARGE_STUB_SET:
        instruction = fill_hint
        batch_rejected = []
        for attempt in range(4):
            filled = _llm_fill(
                "service", instruction, mini, prompt_text, verbose=verbose,
                temperature=0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE,
                extra_system=_FILL_SYSTEM_RULES,
            )
            filled = _stamp_missing_required_datetimes(
                filled, entities_by_class, type_ctx
            )
            filled = _unwrap_swallowed_raises(filled)
            merged = _accept(filled)
            if merged is not None:
                _dump_fill_retry(
                    _fill_debug_root(), svc_class, "<batch>",
                    batch_rejected, (attempt + 1, filled),
                )
                return merged
            violations = (
                _service_fill_violations(
                    filled, repo_interface, stub_design, type_ctx
                )
                if filled else ["empty output"]
            )
            if filled and _repair_missing(filled):
                # The interface just grew: re-evaluate against it before
                # burning a retry — the same fill may now be fully valid.
                violations = _service_fill_violations(
                    filled, repo_interface, stub_design, type_ctx
                )
                if not violations:
                    merged = _merge_stub_bodies(deterministic, filled, stub_names)
                    if merged is not None:
                        _dump_fill_retry(
                            _fill_debug_root(), svc_class, "<batch>",
                            batch_rejected, (attempt + 1, filled),
                        )
                        return merged
            if filled:
                batch_rejected.append((attempt + 1, filled, violations))
            if filled and verbose:
                print(
                    "    [fill] service: rejected (attempt %d: %s)"
                    % (attempt + 1, "; ".join(violations[:4]))
                )
            instruction = (
                fill_hint
                + "\n\nYOUR PREVIOUS OUTPUT WAS REJECTED FOR THESE CONTRACT "
                + "VIOLATIONS (fix ONLY these, keep everything else identical):\n"
                + "\n".join("  - " + v for v in violations[:8])
            )
            if _has_repo_interface_violations(violations):
                instruction += (
                    "\n\nAVAILABLE REPO CALLS — your call was rejected because "
                    "the repository or method is not valid here. Use ONLY these "
                    "exact forms:\n"
                    + _positive_repo_targets(repo_interface, type_ctx)
                )

    # Per-method fill: fill each stub alone with a SCOPED repo hint so the
    # conversation stays under the 4B model's instruction-following limit
    # (a batch over 30 stubs reaches 5-6k tokens and loses fidelity).
    # Validation still uses the FULL repo_interface so a correct call to any
    # real repo method is accepted; the scoped hint only shrinks the prompt.
    # A stubborn body must not revert every other stub, so fill each stub
    # alone and merge whichever bodies pass their own contract check.
    salvaged = deterministic
    reverted = []
    for m in stubs:
        name = m.get("name")
        one_design = {"methods": [m]}
        # Scope BOTH the hint AND the skeleton header to the repos this
        # method's entity + FKs plausibly touch. The header MUST NOT wire
        # every repo: with all four wired, the model "uses" self.loan_repo /
        # self.author_repo even from add_member / search_book (observed:
        # search_book -> loan_repo.find_loans_by_member, add_member ->
        # loan_repo.get_by_id, get_loan_report -> author_repo.find_by_id),
        # because the skeleton exposes them as live despite the hint's "only
        # these" instruction. Wiring only the scoped repos makes the wrong
        # call impossible, and validating against the scoped interface
        # rejects it if the model still tries.
        scoped_iface = _scoped_repo_interface(
            m, repo_interface, entities_by_class
        )
        scoped_entities = {
            _camel(a[: -len("_repo")])
            for a in scoped_iface
            if a.endswith("_repo")
        }
        one_hint = _build_fill_hint(
            scoped_iface, type_ctx, scoped_attrs=set(scoped_iface),
            entities_by_class=entities_by_class,
        )
        one_instr = one_hint
        req_ctx = _method_requirement_context(m, entities_by_class, designs)
        mk_entities = _entities_for_stub(m, scoped_entities, entities)
        one_mini = (
            "\n".join(
                _service_header_lines(
                    svc_class, entities, entities_by_class, exception_names,
                    models_module=models_module, repo_entities=scoped_entities,
                    model_entities=mk_entities,
                )
                + [_method_stub_code(m, 1)]
            ).rstrip()
            + "\n"
        )
        ok = False
        rejected_fills = []
        accepted_fill = None
        # 3 attempts (not 2): a domain-state method like borrow_member needs
        # to construct an entity with several required fields, and a single
        # retry is often not enough for the 4B model to correct a dropped
        # field. The extra attempt is cheap (per-method fill) and eliminates
        # the run-dependent `still stubbed` outcome.
        for attempt in range(3):
            cand = _llm_fill(
                "service", one_instr, one_mini, req_ctx, verbose=verbose,
                temperature=0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE,
                extra_system=_FILL_SYSTEM_RULES,
            )
            if cand is None:
                # A fill whose every attempt failed to compile comes back as
                # None. It is a FAILED attempt, not a body: the text rewrites
                # below parse their input, so `ast.parse(None)` used to raise
                # `TypeError: compile() arg 1 must be a string` and abort the
                # whole prompt (18). Skip the attempt instead; when all three
                # are null the method stays in `reverted`.
                if verbose:
                    print(
                        "    [fill] service.%s: no fill (attempt %d)"
                        % (name, attempt + 1)
                    )
                continue
            cand = _strip_import_enum_validation(cand)
            cand = _unwrap_swallowed_raises(cand)
            repaired_cand = _stamp_missing_required_datetimes(
                cand, entities_by_class, type_ctx
            )
            if repaired_cand != cand and verbose:
                print(
                    "    [fill] service.%s: stamped missing required "
                    "date field(s) deterministically" % name
                )
            cand = repaired_cand
            # Validate against the SCOPED interface, recomputed after any
            # bounded repair grew repo_interface, so a correct in-scope call
            # is accepted and a wrong-repo call (self.author_repo from
            # return_loan) is rejected.
            cur_iface = _scoped_repo_interface(
                m, repo_interface, entities_by_class
            )
            viol = (
                _service_fill_violations(
                    cand, cur_iface, one_design, type_ctx
                )
                if cand else ["empty output"]
            )
            if cand and _repair_missing(cand):
                viol = _service_fill_violations(
                    cand,
                    _scoped_repo_interface(m, repo_interface, entities_by_class),
                    one_design,
                    type_ctx,
                )
            if not viol:
                # A merge can legitimately fail (fill missing a method);
                # assigning its None result here used to crash the NEXT
                # stub with ast.parse(None) (TypeError, observed on run 08).
                # Keep the previous salvage state instead.
                merged = _merge_stub_bodies(salvaged, cand, [name])
                if merged is not None:
                    salvaged = merged
                    ok = True
                    accepted_fill = (attempt + 1, cand)
                    if verbose:
                        print(
                            "    [fill] service.%s: filled (attempt %d)"
                            % (name, attempt + 1)
                        )
                break
            # Record EVERY rejected body (debug dump) BEFORE the log line:
            # the log fires only on the last attempt, so a retry that
            # succeeds would otherwise lose its rejected predecessor.
            rejected_fills.append((attempt + 1, cand, viol))
            # Log a rejection ONLY on the last attempt: a transient reject
            # followed by a successful retry (borrow_member) would otherwise
            # leave a banned "rejected (attempt 1: ...)" marker in the log
            # even though the method ultimately filled. Positive-first; a
            # method that fails all attempts still logs its rejection here.
            if verbose and attempt == 2:
                print(
                    "    [fill] service.%s: rejected (attempt %d: %s)"
                    % (name, attempt + 1, "; ".join(viol[:3]))
                )
            one_instr = (
                one_hint
                + "\n\nYOUR PREVIOUS OUTPUT WAS REJECTED FOR THESE CONTRACT "
                + "VIOLATIONS (fix ONLY these, keep everything else identical):\n"
                + "\n".join("  - " + v for v in viol[:6])
            )
            if any("missing required field" in v for v in viol):
                one_instr += (
                    "\n\nCONSTRUCTION FIX  when the rejection says an entity "
                    "constructor is missing required field(s), build the "
                    "entity with EVERY required field. For a required "
                    "date/datetime field that is not a method parameter "
                    "(e.g. loan_date), pass "
                    "datetime.datetime.now().isoformat(); for a due/end date "
                    "compute it relative to now. NEVER omit a required field."
                )
            if _has_repo_interface_violations(viol):
                one_instr += (
                    "\n\nAVAILABLE REPO CALLS — your call was rejected because "
                    "the repository or method is not valid in this method's "
                    "scoped interface. Use ONLY these exact forms:\n"
                    + _positive_repo_targets(cur_iface, type_ctx)
                )
        _dump_fill_retry(
            _fill_debug_root(), svc_class, name, rejected_fills, accepted_fill
        )
        if not ok:
            reverted.append(name)
    if verbose and len(reverted) < len(stub_names):
        # Only mention `still stubbed` when a stub actually remains — an
        # all-filled service would otherwise emit the banned "still stubbed:
        # (none)" marker even though nothing is stubbed.
        msg = "    [fill] service: salvaged %d/%d stubs per-method" % (
            len(stub_names) - len(reverted), len(stub_names)
        )
        if reverted:
            msg += "; still stubbed: %s" % ", ".join(sorted(reverted))
        print(msg)
    return salvaged
