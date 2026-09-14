"""Prompt-only METHOD CONTRACT extraction and static verification.

Why this pass exists. Only two validators filter a filled service body:
``_undefined_name_violations`` (NameError) and ``_semantic_fill_violations``
(designed types). Both are CRASH filters. A body that ignores a parameter,
skips a counter update or inverts a guard is name-correct and type-correct,
so it ships. This module supplies the missing behavioural anchor: a contract
per designed method, extracted from the SPECIFICATION, plus the deterministic
recipes that render the well-shaped parts of it and a static check of the
rest.

Anti-tautology split (the reason extraction and verification are separate
functions taking disjoint inputs):

  * ``extract_method_contracts`` reads ONLY the specification (and the
    design's own method signatures, which merely name the methods to
    describe) -- it NEVER sees a generated body.

  * ``method_contract_violations`` reads ONLY a generated body plus this
    contract -- it NEVER sees the specification.

Two independent sources: a contract that merely restates the code is
impossible by construction, and a body that satisfies the contract cannot
have been tuned to the checker.

Evidence closure. Every extracted method must carry a verbatim span of the
specification; an entry whose span is not found is dropped, so an
underspecified prompt yields no contract (never an invented one).
"""
from __future__ import annotations

import ast
import re

from agentlib.config import LLM_MAX_TOKENS_LONG, LLM_RETRY_TEMPERATURE
from agentlib.llm.client import _json_complete
from agentlib.naming import _camel, _snake
from agentlib.pipeline.service_contract import _evidence_ok, _norm_span, _snake_name

# Effect kinds the recipes can render deterministically. Kept deliberately
# small: every kind here has an exact renderer, so an extracted effect either
# becomes a deterministic body or is discarded, never half-applied.
_COUNTER_KINDS = {"counter_delta"}
_FLAG_KINDS = {"flag_toggle", "flag_set"}
_STATUS_KINDS = {"status_set"}
# A date column stamped with the CURRENT time ("sets return_date"). Distinct
# from status_set because the value is not a literal in the specification: the
# spec names the FIELD, and "now" is the only sensible reading of a workflow
# stamping a return/close/completion timestamp.
_DATE_KINDS = {"date_set"}
_CHILD_KINDS = {"create_child"}
_EFFECT_KINDS = (
    _COUNTER_KINDS | _FLAG_KINDS | _STATUS_KINDS | _DATE_KINDS | _CHILD_KINDS
)
_GUARD_KINDS = {"reject_inactive", "reject_unavailable", "reject_duplicate"}
# The PARTS a compound report's specification can name, and nothing else: the
# closed vocabulary the "requirement analyst" transcribes the spec's prose
# into ("returns total spent, per-category breakdown, budget status"). Every
# part has an exact renderer in the `report_parts` recipe, so a transcribed
# part either becomes a deterministic statement or is dropped — never
# half-applied. A part outside this list is DISCARDED, which is what keeps the
# extraction from inventing report shapes.
_REPORT_PARTS = {
    "total",            # the sum over the period
    "count",            # how many rows the period holds
    "per_category",     # the sum broken down by the grouping column
    "budget_status",    # per-group comparison of that sum to a stored limit
    "monthly_totals",   # the sum bucketed by calendar month
    "top_categories",   # the largest per-group sums, ranked
    "average_monthly",  # the mean of the monthly totals
}
_DELTA_WORDS = {
    "increment": 1, "increments": 1, "increase": 1, "increases": 1,
    "decrement": -1, "decrements": -1, "decrease": -1, "decreases": -1,
    "ajouter": 1, "ajoute": 1, "incrementer": 1, "retirer": -1,
    "decrementer": -1, "reduire": -1, "reduit": -1,
}


def method_contract_schema():
    """JSON schema for the per-method behavioural contract.

    Every field is optional except ``name`` and ``evidence``: an
    underspecified method simply carries an empty contract, which the
    verifier treats as "nothing to check" -- never as a failure.
    """
    effect = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": sorted(_EFFECT_KINDS),
            },
            "entity": {"type": "string"},
            "field": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["kind"],
        "additionalProperties": False,
    }
    guard = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": sorted(_GUARD_KINDS)},
            "entity": {"type": "string"},
            "field": {"type": "string"},
        },
        "required": ["kind"],
        "additionalProperties": False,
    }
    method = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "returns_entity": {"type": "string"},
            "filters": {"type": "array", "items": {"type": "string"}},
            "effects": {"type": "array", "items": effect},
            "guards": {"type": "array", "items": guard},
            "report_parts": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(_REPORT_PARTS)},
            },
            "report_labels": {
                "type": "object",
                "properties": {
                    "ok": {"type": "string"},
                    "warn": {"type": "string"},
                    "over": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "evidence": {"type": "string"},
        },
        "required": ["name", "evidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "methods": {"type": "array", "items": method},
        },
        "required": ["methods"],
        "additionalProperties": False,
    }


_METHOD_CONTRACT_SYSTEM = (
    "You are an expert requirement analyst. For EACH method listed below, "
    "transcribe the behaviour the SPECIFICATION states about it into a "
    "structured contract.\n\n"
    "Field by field:\n"
    "- returns_entity: the domain entity the method yields or creates, in "
    "PascalCase (Book, Loan, Member, Expense, Budget, Category, ...). Empty "
    "when the method returns a plain number/bool/aggregate.\n"
    "- filters: the parameter names that the spec says RESTRICT the result "
    "(e.g. a month/year/category/date window). A parameter the spec states "
    "only as a lookup key (the id of the row being acted on) is NOT a "
    "filter. Empty when the spec states no restricting parameter.\n"
    "- effects: the state changes the spec states, one object each:\n"
    "    * counter_delta {entity, field, value}: the method adds to or "
    "removes from a numeric field of an entity. value is \"1\" or \"-1\" "
    "(\"decrements copies\" -> value \"-1\").\n"
    "    * flag_toggle {entity, field}: the method flips a boolean field.\n"
    "    * flag_set {entity, field, value}: the method sets a boolean to a "
    "stated value (\"true\"/\"false\").\n"
    "    * status_set {entity, field, value}: the method sets a status-ish "
    "field to a stated literal (\"returned\", \"shipped\", ...). When the "
    "spec says the method UPDATES that field WITHOUT naming the value in "
    "the same sentence, STILL emit the effect and OMIT `value` — the "
    "generator resolves it from the value set the spec lists for that "
    "field.\n"
    "    * date_set {entity, field}: the method stamps a date/datetime "
    "field with the CURRENT time. Use it whenever the spec says the method "
    "\"sets <field>\" / \"records <field>\" and that field is a date or "
    "datetime (\"sets return_date\" -> date_set on return_date).\n"
    "    * create_child {entity}: the method inserts a new row of entity.\n"
    "- guards: the conditions the spec states the method REFUSES:\n"
    "    * reject_inactive {entity}: refuses an entity whose boolean "
    "active/available flag is false.\n"
    "    * reject_unavailable {entity, field}: refuses when a numeric count "
    "field is <= 0.\n"
    "    * reject_duplicate {entity, field}: refuses an existing row.\n"
    "- report_parts: ONLY for a method the spec describes as a REPORT that "
    "returns SEVERAL pieces. List each piece the spec names, using these "
    "exact names:\n"
    "    * total: the overall sum\n"
    "    * count: how many records\n"
    "    * per_category: the sum broken down per category/group\n"
    "    * budget_status: a comparison of the spend against a stored limit "
    "(states like on_track/warning/exceeded)\n"
    "    * monthly_totals: sums bucketed per month\n"
    "    * top_categories: the largest per-category sums, ranked\n"
    "    * average_monthly: the mean of the monthly sums\n"
    "  Empty when the spec does not describe the method as a multi-piece "
    "report (a method returning a single number or a single row is NOT a "
    "report and must leave this empty).\n"
    "- report_labels: ONLY when the spec STATES the status words for "
    "budget_status, copied as written: {ok, warn, over} (for "
    "\"budget status (on_track/warning/exceeded)\" -> {ok: \"on_track\", "
    "warn: \"warning\", over: \"exceeded\"}). Omit otherwise.\n"
    "- evidence: the EXACT substring of the specification stating this "
    "method's behaviour, copied VERBATIM. Mandatory and verified.\n\n"
    "HARD RULES — an unsupported entry is DISCARDED:\n"
    "- Describe ONLY what the specification states. NEVER invent an effect, "
    "a guard, a field, or a return shape the text does not state.\n"
    "- An empty effects/guards/filters list is a valid, expected answer.\n"
    "- Only describe the methods listed below, using their exact names.\n"
    "- evidence MUST be copied verbatim from the specification.\n"
    "Read ONLY the specification — never any code."
)


# Bounded refill instruction. Sent only when a previous attempt's evidence was
# NOT a verbatim span of the specification. It names the methods that failed
# and demands a SHORT literal span, which is what a 4B model can actually
# produce: a long "quote this verbatim" instruction alone yielded paraphrases
# and kept NOTHING (library_system: 0 of 28 contracts closed, "checks
# availability" rewritten as "checks book availability").
_EVIDENCE_REPAIR_TEMPLATE = (
    "Your previous answer was DISCARDED for these methods: their `evidence` "
    "was not copied verbatim from the SPECIFICATION:\n%s\n\n"
    "Describe ONLY these methods:\n%s\n\n"
    "For each, `evidence` MUST be a SHORT span of 4 to 12 words copied "
    "EXACTLY from the SPECIFICATION text above — the same words in the same "
    "order, with NO added words, NO rewording and NO type annotations. Copy "
    "the span as written, even when it is terse."
)

# Total extraction attempts (1 initial + bounded refills). The refill is
# per-run, never per-method: the whole contract set is re-requested and the
# attempts are MERGED, so an entry that closed on attempt 1 is never lost.
_MAX_CONTRACT_ATTEMPTS = 3


def _method_sig_lines(method_sigs):
    return "\n".join(
        "  %s(%s)" % (name, ", ".join(params))
        for name, params in method_sigs
    )


def extract_method_contracts(prompt_text, method_sigs, verbose=False):
    """{method_name: contract} for the given design methods, evidence-closed.

    ``method_sigs`` is ``[(name, [param names])]`` taken from the DESIGN: it
    only names the methods to describe, so the spec stays the sole source of
    the behaviour. Returns ``{}`` on any failure — the pipeline is never
    blocked by this optional pass.
    """
    if not prompt_text or not method_sigs:
        return {}
    user = (
        "SPECIFICATION:\n%s\n\nMETHODS TO DESCRIBE:\n%s\n\n"
        "Transcribe each method's behaviour now."
        % (prompt_text, _method_sig_lines(method_sigs))
    )
    messages = [
        {"role": "system", "content": _METHOD_CONTRACT_SYSTEM},
        {"role": "user", "content": user},
    ]
    prompt_norm = _norm_span(prompt_text)
    wanted = {name for name, _ in method_sigs}
    accepted = {}
    for attempt in range(_MAX_CONTRACT_ATTEMPTS):
        data = _json_complete(
            messages, schema=method_contract_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
            temperature=0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE,
        )
        if isinstance(data, dict):
            out, _rejected = _accept_method_contracts(
                data, prompt_norm, wanted, verbose, raw_prompt=prompt_text
            )
            for mname, contract in out.items():
                accepted.setdefault(mname, contract)
        missing = sorted(wanted - set(accepted))
        if not missing or attempt + 1 >= _MAX_CONTRACT_ATTEMPTS:
            break
        if verbose:
            print(
                "    [mcontract] retry %d for %d method(s) whose evidence was "
                "not verbatim" % (attempt + 2, len(missing))
            )
        messages = messages[:2] + [{
            "role": "user",
            "content": _EVIDENCE_REPAIR_TEMPLATE % (
                "\n".join("  %s" % n for n in missing),
                _method_sig_lines(
                    [s for s in method_sigs if s[0] in set(missing)]
                ),
            ),
        }]
    return accepted


def _effect_entity(entities_by_class, raw):
    """Resolve a stated entity name to a designed class name, or "".

    Design-only resolution: an invented entity (not in the design) resolves
    to "" and the effect is dropped, so a contract can never name an entity
    the design does not have.
    """
    name = _snake_name(raw)
    if not name:
        return ""
    for cls in entities_by_class or ():
        if _snake(cls) == name:
            return cls
    for cls in entities_by_class or ():
        if _snake(cls) in (name, name.rstrip("s")):
            return cls
    return ""


def _status_value_for(method_name, field, prompt_text):
    """The value the specification states for ``field`` that matches the verb.

    A model line such as ``status (active/returned/overdue)`` names the VALUE
    SET of a status column without stating which member a workflow writes.
    The method's own verb picks the member ("return_book" -> "returned"), and
    the winner is copied from the specification — never invented, and an
    unmatched verb yields "" so the effect is dropped rather than guessed.
    """
    if not prompt_text or not field:
        return ""
    values = []
    for match in re.finditer(
        r"\b%s\s*[\(:]\s*([A-Za-z0-9_\-/ |]+)" % re.escape(field), prompt_text
    ):
        for raw in re.split(r"[/|,]", match.group(1)):
            candidate = raw.strip().strip(").,;")
            if candidate and len(candidate) < 30:
                values.append(candidate)
    if not values:
        return ""
    verb = _snake_name(method_name) or ""
    for prefix in ("get_", "list_", "find_", "search_", "create_", "add_",
                   "update_"):
        if verb.startswith(prefix):
            verb = verb[len(prefix):]
            break
    token = (verb.split("_") or [""])[0]
    if not token:
        return ""
    best = ""
    best_len = 0
    for value in values:
        common = 0
        for a, b in zip(token, value.lower()):
            if a != b:
                break
            common += 1
        if common > best_len:
            best, best_len = value, common
    return best if best_len >= 4 else ""


def _accept_method_contracts(data, prompt_norm, wanted, verbose, raw_prompt=""):
    """Evidence-verify an extracted contract; drop unsupported entries.

    Returns ``(accepted, rejected_names)``. The rejected names let the caller
    drive a BOUNDED refill that re-asks the model, for those methods only,
    for a short verbatim span — without them a small model's paraphrase
    silently costs the whole pass (library_system kept 0 of 28 contracts).
    """
    out = {}
    rejected = []
    dropped = 0
    for m in data.get("methods") or []:
        if not isinstance(m, dict):
            continue
        name = _snake_name(m.get("name"))
        if name not in wanted or not _evidence_ok(m.get("evidence"), prompt_norm):
            dropped += 1
            if name in wanted:
                rejected.append(name)
            continue
        filters = []
        for f in m.get("filters") or []:
            fn = _snake_name(f)
            if fn:
                filters.append(fn)
        effects = []
        for e in m.get("effects") or []:
            if not isinstance(e, dict):
                continue
            kind = e.get("kind")
            if kind not in _EFFECT_KINDS:
                continue
            eff = {"kind": kind}
            if e.get("entity"):
                eff["entity"] = _snake_name(e["entity"])
            if e.get("field"):
                eff["field"] = _snake_name(e["field"])
            if e.get("value") is not None:
                eff["value"] = str(e["value"]).strip()
            effects.append(eff)
        guards = []
        for g in m.get("guards") or []:
            if not isinstance(g, dict) or g.get("kind") not in _GUARD_KINDS:
                continue
            gd = {"kind": g["kind"]}
            if g.get("entity"):
                gd["entity"] = _snake_name(g["entity"])
            if g.get("field"):
                gd["field"] = _snake_name(g["field"])
            guards.append(gd)
        parts = []
        for p in m.get("report_parts") or []:
            if isinstance(p, str) and p.strip() in _REPORT_PARTS:
                parts.append(p.strip())
        # The labels are the SPECIFICATION's own words ("on_track/warning/
        # exceeded"), so each one is kept only when it literally occurs in the
        # evidence span this entry is anchored to. A label the spec does not
        # use is dropped and the recipe falls back to its documented default —
        # the same evidence closure the effects already rely on.
        ev_low = (m.get("evidence") or "").lower()
        labels = {}
        raw_labels = m.get("report_labels")
        if isinstance(raw_labels, dict):
            for key in ("ok", "warn", "over"):
                val = raw_labels.get(key)
                if (isinstance(val, str) and val.strip()
                        and val.strip().lower() in ev_low):
                    labels[key] = val.strip()
        # A ``status_set`` the analyst left value-less ("updates status" — the
        # spec names the FIELD, not the literal) is resolved to the value the
        # specification lists for that field, chosen by the method's own verb.
        # Dropping it silently cost ``return_book`` its status update: the
        # workflow shipped without the state change the spec states.
        for eff in effects:
            if eff.get("kind") == "status_set" and not eff.get("value"):
                resolved = _status_value_for(
                    name, eff.get("field") or "status", raw_prompt
                )
                if resolved:
                    eff["value"] = resolved
        out[name] = {
            "name": name,
            "returns_entity": _snake_name(m.get("returns_entity")),
            "filters": filters,
            "effects": effects,
            "guards": guards,
            "report_parts": parts,
            "report_labels": labels,
            "evidence": (m.get("evidence") or "").strip(),
        }
    if verbose and dropped:
        print("    [mcontract] dropped %d unsupported entr(ies)" % dropped)
    return out, rejected


def _delta_value(raw):
    """1 / -1 from a stated delta word or a signed literal, else None."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("1", "+1"):
        return 1
    if s in ("-1", "1-"):
        return -1
    for word, val in _DELTA_WORDS.items():
        if word in s:
            return val
    return None


def contract_effects_for(contract, entities_by_class):
    """Resolved effects: entity class + field names verified against the design.

    Design-only resolution. An effect naming an entity or a field the design
    does not have is DROPPED, so the recipes below can never reference a
    column that does not exist. ``returns_entity`` is resolved to a class too.
    """
    if not contract:
        return []
    resolved = []
    for eff in contract.get("effects") or []:
        kind = eff.get("kind")
        cls = _effect_entity(entities_by_class, eff.get("entity"))
        if not cls:
            continue
        ent = (entities_by_class or {}).get(cls) or {}
        fields = {
            f.get("name"): f for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        }
        field = eff.get("field") or ""
        if kind in _COUNTER_KINDS:
            if field not in fields:
                continue
            delta = _delta_value(eff.get("value"))
            if delta is None:
                continue
            resolved.append({"kind": kind, "cls": cls, "field": field, "delta": delta})
        elif kind in _FLAG_KINDS:
            if field not in fields or fields[field].get("type") not in (None, "bool"):
                continue
            value = eff.get("value")
            if kind == "flag_set" and str(value).strip().lower() not in ("true", "false"):
                continue
            resolved.append({
                "kind": kind, "cls": cls, "field": field,
                "value": None if kind == "flag_toggle"
                else str(value).strip().lower() == "true",
            })
        elif kind in _STATUS_KINDS:
            if field not in fields or not eff.get("value"):
                continue
            resolved.append({"kind": kind, "cls": cls, "field": field,
                             "value": eff["value"]})
        elif kind in _DATE_KINDS:
            # Design-only type check: the field must BE a date/datetime column,
            # so a date_set can never stamp a string or an int.
            if field not in fields or fields[field].get("type") not in (
                "date", "datetime"
            ):
                continue
            resolved.append({"kind": kind, "cls": cls, "field": field,
                             "value": "now"})
        elif kind in _CHILD_KINDS:
            resolved.append({"kind": kind, "cls": cls})
    return resolved


def contract_guards_for(contract, entities_by_class):
    """Resolved guards: entity class + field verified against the design."""
    if not contract:
        return []
    resolved = []
    for gd in contract.get("guards") or []:
        cls = _effect_entity(entities_by_class, gd.get("entity"))
        if not cls:
            continue
        ent = (entities_by_class or {}).get(cls) or {}
        fields = {
            f.get("name"): f for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        }
        kind = gd.get("kind")
        field = gd.get("field") or ""
        if kind == "reject_unavailable" and field in fields:
            resolved.append({"kind": kind, "cls": cls, "field": field})
        elif kind in ("reject_inactive", "reject_duplicate"):
            if not field:
                field = next(
                    (f.get("name") for f in (ent.get("fields") or [])
                     if isinstance(f, dict)
                     and f.get("type") == "bool"),
                    "",
                )
            if field and field in fields:
                resolved.append({"kind": kind, "cls": cls, "field": field})
    return resolved
# ---------------------------------------------------------------------------
# Stage 3: static verification of a filled body against the contract
# ---------------------------------------------------------------------------

def method_contract_violations(tree, svc_design, contracts, entities_by_class,
                               repo_returns=None):
    """Contract violations of a filled service body ([] = accept).

    Reads ONLY the generated body and the contract — never the specification.

    Currently checks the parts that are decidable by static analysis without
    guessing at runtime values:

    (1) A contract FILTER parameter must actually be read by the body. A body
        that never loads ``month`` cannot be filtering by month — this is
        exactly the S1 defect (``get_monthly_report(month)`` summing every
        row).
    (2) A method whose contract yields an ENTITY must reach that entity's own
        repository — or delegate to a DESIGNED repository method whose
        declared return already yields it (``repo_returns`` maps
        ``(repo_attr, method) -> raw return annotation``). The delegation case
        is real: library's ``get_member_history`` belongs to
        ``member_repo.get_member_loan_history(member_id) -> List[Loan]``, so
        demanding the entity's OWN repository rejected a valid body, which
        then shipped as a stub (S13 regression). Reinforces the repo/entity
        coherence gate with the spec-derived expectation rather than the
        name-derived one.

    Effects and guards are NOT checked here: whether a counter really moved
    is a runtime property, so it is verified by the executed oracle
    (``behavior_tests``) instead of by pattern-matching the source.
    """
    violations = []
    contracts = contracts or {}
    if not contracts:
        return violations
    class_names = set(entities_by_class or ())
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        contract = contracts.get(fn.name)
        if not contract:
            continue
        loaded = {
            n.id for n in ast.walk(fn)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }
        for filt in contract.get("filters") or []:
            if filt not in loaded:
                violations.append(
                    "%s declares %r as a restricting parameter but never "
                    "reads it — the result is not filtered by %s"
                    % (fn.name, filt, filt)
                )
        want = contract.get("returns_entity") or ""
        if want:
            cls = next(
                (c for c in class_names if _snake(c) == _snake(want)), None
            )
            if cls is not None:
                want_repo = _snake(cls) + "_repo"
                touched = {
                    n.attr for n in ast.walk(fn)
                    if isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name)
                    and n.value.id == "self"
                    and n.attr.endswith("_repo")
                }
                if touched and want_repo not in touched:
                    # …unless the body DELEGATES to a designed repository
                    # method that already yields the wanted entity.
                    called = {
                        (n.func.value.attr, n.func.attr)
                        for n in ast.walk(fn)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and isinstance(n.func.value, ast.Attribute)
                        and isinstance(n.func.value.value, ast.Name)
                        and n.func.value.value.id == "self"
                        and n.func.value.attr.endswith("_repo")
                    }
                    delegates = any(
                        cls in str((repo_returns or {}).get(pair, ""))
                        for pair in called
                    )
                    if not delegates:
                        violations.append(
                            "%s must yield %s objects but never calls %s"
                            % (fn.name, cls, want_repo)
                        )
    return violations


# ---------------------------------------------------------------------------
# Stage 2: contract -> deterministic recipe impl
# ---------------------------------------------------------------------------

def _id_param_for(cls, params):
    """The parameter naming ``cls``'s own row id (``loan_id``), or ""."""
    snake = _snake(cls)
    for cand in (snake + "_id",):
        if cand in params:
            return cand
    return ""


def _effect_target(entity_cls, anchor_cls, entities_by_class):
    """How the anchor row reaches the effect entity: "self", an FK column, None.

    "self" when the effect is on the anchor entity itself; the FK column name
    (``book_id``) when the anchor declares a foreign key to it; None when
    unreachable, in which case the contract is not renderable and the method
    keeps its LLM fill.
    """
    if entity_cls == anchor_cls:
        return "self"
    ent = (entities_by_class or {}).get(anchor_cls) or {}
    for f in ent.get("fields") or []:
        if not isinstance(f, dict):
            continue
        fn = f.get("name") or ""
        if (
            fn.endswith("_id")
            and fn != "id"
            and _camel(fn[: -len("_id")]) == entity_cls
        ):
            return fn
    return None


def _contradicts_flag_effect(guard, effects):
    """True when a guard contradicts a flag effect of the SAME contract.

    "toggles is_active" and "refuses a member whose is_active is false" cannot
    both hold: the toggle IS the operation, so refusing on the very flag being
    flipped is an over-read of the specification. library_system's
    renew_membership carries exactly that pair, and honouring the guard kept
    the method on its LLM fill — whose body then refused every inactive
    member and never flipped the flag (S11).
    """
    if guard.get("kind") != "reject_inactive":
        return False
    for eff in effects or []:
        if (
            eff.get("kind") in _FLAG_KINDS
            and eff.get("cls") == guard.get("cls")
            and eff.get("field") == guard.get("field")
        ):
            return True
    return False


def _declared_pairs(ent):
    """[(param, column, op)] from an entity's declared list() filters."""
    out = []
    for spec in (ent.get("list_filters") or []):
        if (
            isinstance(spec, dict)
            and isinstance(spec.get("param"), str) and spec["param"]
            and isinstance(spec.get("column"), str) and spec["column"]
        ):
            out.append((spec["param"], spec["column"], spec.get("op", "eq")))
    return out


def _budget_binding(group_field, entities_by_class):
    """The entity holding a per-(group, period) LIMIT, or None.

    Design-only: an entity carrying a foreign key named like ``group_field``
    TOGETHER WITH exactly one numeric non-FK column (the limit) and exactly
    one str column (the period), both of which the entity declares as list()
    filter parameters — so the emitted lookup stays a plain ``list(...)`` call
    on the repository's real API. Two candidates => ambiguous => None.
    """
    if not group_field or not group_field.endswith("_id"):
        return None
    found = []
    for cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict):
            continue
        fields = [
            f for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        ]
        names = {f["name"] for f in fields}
        if group_field not in names:
            continue
        nums = [
            f["name"] for f in fields
            if f.get("type") in ("int", "float")
            and f["name"] != "id" and not f["name"].endswith("_id")
        ]
        strs = [f["name"] for f in fields if f.get("type") == "str"]
        if len(nums) != 1 or len(strs) != 1:
            continue
        pairs = _declared_pairs(ent)
        fk_param = next((p for p, c, _ in pairs if c == group_field), None)
        month_param = next((p for p, c, _ in pairs if c == strs[0]), None)
        if fk_param and month_param:
            found.append({
                "entity": _snake(cls),
                "limit_field": nums[0],
                "fk_filter_param": fk_param,
                "month_filter_param": month_param,
            })
    return found[0] if len(found) == 1 else None


def _report_impl(contract, entities_by_class, params, returns):
    """A ``report_parts`` impl for a compound report, or None.

    Fires only when the contract names at least one PART the specification
    lists AND the design pins every shape that part needs: ONE entity with a
    single date and a single numeric column (the substance being summed), a
    period parameter among the method's OWN params, and — for the breakdown
    parts — a single FK column to group by, plus (for ``budget_status``) the
    unambiguous budget entity carrying the limit. Anything less keeps the LLM
    fill. The PARTS themselves are the specification's; the SHAPES are the
    design's, so neither source can restate the other.
    """
    parts = list(contract.get("report_parts") or [])
    if not parts:
        return None
    params = list(params or [])
    ret = (returns or "").strip().lower()
    if "dict" not in ret:
        return None
    period = next(
        (
            p for p in (contract.get("filters") or [])
            if p in params and any(t in p for t in _PERIOD_TOKENS)
        ),
        None,
    )
    if period is None:
        # A report that does not read its window is the S1 defect; without a
        # period parameter there is nothing to render.
        return None
    cands = []
    for cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict):
            continue
        fields = [
            f for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name") and f["name"] != "id"
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
        if len(dates) == 1 and len(nums) == 1:
            cands.append((cls, dates[0], nums[0]))
    if len(cands) != 1:
        return None
    cls, date_field, value_field = cands[0]
    ent = entities_by_class[cls]
    fks = sorted(
        str(f["name"]) for f in (ent.get("fields") or [])
        if isinstance(f, dict) and isinstance(f.get("name"), str)
        and f["name"].endswith("_id") and f["name"] != "id"
    )
    group_field = fks[0] if len(fks) == 1 else None
    needs_group = any(
        p in ("per_category", "budget_status", "top_categories") for p in parts
    )
    if needs_group and not group_field:
        return None
    impl = {
        "kind": "report_parts",
        "entity": _snake(cls),
        "value_field": value_field,
        "date_field": date_field,
        "period_param": period,
        "period_granularity": (
            "year" if ("year" in period or "annee" in period) else "month"
        ),
        "parts": parts,
        "result_key": "total",
    }
    if group_field:
        impl["group_field"] = group_field
    if "budget_status" in parts:
        budget = _budget_binding(group_field, entities_by_class)
        if budget is None:
            return None
        impl["budget"] = budget
    labels = dict(contract.get("report_labels") or {})
    if labels:
        impl["labels"] = labels
    return impl


def _bool_return(returns):
    """'bool' when the declaration is a bool workflow, else None.

    ``Optional[bool]``/``bool | None`` are the SAME workflow: the design
    merely annotates a best-effort result.
    """
    ret = (returns or "").strip().lower()
    if ret.startswith("optional[") and ret.endswith("]"):
        ret = ret[len("optional["):-1].strip()
    elif ret.endswith("| none"):
        ret = ret[: -len("| none")].strip()
    if ret and ret not in ("bool", "boolean"):
        return None
    return "bool"


def spec_line_effects(method_name, prompt_text, entities_by_class):
    """Effects transcribed LITERALLY from the method's own specification line.

    The LLM contract extractor is the primary source, but its evidence closure
    drops a line the specification states plainly: library_system's
    ``borrow_book(member_id, book_id): checks availability, creates loan,
    decrements copies`` was rejected on all three retries ("evidence was not
    verbatim"), so the method carried NO contract at all, fell to the fill, and
    shipped as a dead ``return False`` stub — borrowing never decremented the
    book and never created the loan.

    This reader is literal and entity-closed: it reads the method's OWN line,
    and every word must resolve against the designed entities (``loan`` ->
    the Loan entity, ``copies`` -> the Book field ending in ``copies``). It
    returns ``{"effects": [...], "guards": [...]}`` in the same vocabulary the
    extractor uses, so a spec-derived contract is indistinguishable from an
    extracted one and can never invent an entity or a field.
    """
    line = ""
    for candidate in (prompt_text or "").splitlines():
        if method_name in candidate:
            line = candidate.strip()
            break
    if not line:
        return {"effects": [], "guards": []}
    low = line.lower()
    effects = []
    # "creates loan" / "inserts a loan row" -> insert a Loan row.
    for match in re.finditer(
        r"\b(?:creates?|inserts?|records?|adds?)\s+(?:an?\s+|a\s+)?"
        r"([a-z_]+)",
        low,
    ):
        cls = _effect_entity(entities_by_class, match.group(1))
        if cls and not any(
            e["kind"] == "create_child" and e["entity"] == cls for e in effects
        ):
            effects.append({"kind": "create_child", "entity": cls})
    # "decrements copies" / "increments available_copies" -> the counter on the
    # entity that carries that field (the spec word may be a suffix of the
    # column: "copies" -> available_copies).
    for match in re.finditer(
        r"\b(%s)\s+([a-z_]+)" % "|".join(sorted(_DELTA_WORDS)),
        low,
    ):
        delta = _DELTA_WORDS[match.group(1)]
        word = match.group(2)
        target = _field_owner(word, entities_by_class)
        if target is None:
            continue
        cls, field = target
        effects.append({
            "kind": "counter_delta",
            "entity": cls,
            "field": field,
            "value": str(delta),
        })
    guards = []
    # "checks availability" -> refuse the operation when the counter is empty.
    if re.search(r"\bchecks?\s+(?:the\s+)?availability", low):
        counter = next(
            (e for e in effects if e["kind"] == "counter_delta"), None
        )
        if counter is not None:
            guards.append({
                "kind": "reject_unavailable",
                "entity": counter["entity"],
                "field": counter["field"],
            })
    return {"effects": effects, "guards": guards}


def _field_owner(word, entities_by_class):
    """``(class, field)`` for a spec word naming a designed field, or None.

    Exact name first, then the bounded prefix/suffix rule the option and model
    renderers already use ("copies" -> Book.available_copies). Ambiguity
    (several entities carrying such a field) resolves to nothing, so the
    reader declines rather than guesses.
    """
    token = _snake_name(word)
    hits = []
    for cls, ent in (entities_by_class or {}).items():
        for field in (ent.get("fields") or []):
            if not isinstance(field, dict) or not field.get("name"):
                continue
            name = field["name"]
            if (
                name == token
                or name.endswith("_" + token)
                or name.startswith(token + "_")
            ):
                hits.append((cls, name))
    if len(hits) != 1:
        return None
    return hits[0]


def _create_child_impl(contract, entities_by_class, params, returns, effects):
    """A ``create_child_row`` impl for a workflow that INSERTS a row.

    The shape is a stated BUSINESS OPERATION rather than a state change on one
    existing row: "checks availability, creates loan, decrements copies". The
    anchor row is loaded by the parameter that names its id (``book_id``), the
    counter effects apply to it, and the child row is inserted with every
    required column stamped from a source that is itself exact:

      * a column named by one of the method's own parameters (``book_id``,
        ``member_id``);
      * the design's declared default (``status (active/...)`` -> 'active');
      * "now" for a date/datetime column the specification does not qualify.

    Returns None the moment a required column has no such source — the fill
    keeps the method rather than a half-stamped insert.
    """
    if _bool_return(returns) is None:
        return None
    children = [e for e in effects if e["kind"] == "create_child"]
    if len(children) != 1:
        return None
    # ``effects`` reaches here RESOLVED (``contract_effects_for`` renames the
    # stated entity to the designed class under ``cls``); accept either key so
    # the compiler works on a raw contract too.
    child_cls = _effect_entity(
        entities_by_class,
        children[0].get("cls") or children[0].get("entity"),
    )
    child = (entities_by_class or {}).get(child_cls or "")
    if not isinstance(child, dict):
        return None
    params = list(params or [])
    child_fields = []
    for field in child.get("fields") or []:
        if not isinstance(field, dict) or not field.get("name"):
            continue
        name = field["name"]
        if name == "id" or field.get("nullable"):
            continue
        if name in params:
            child_fields.append({"name": name, "param": name})
        elif name.endswith("_id") and name[: -len("_id")] in params:
            child_fields.append({"name": name, "param": name[: -len("_id")]})
        elif "default" in field and field.get("default") is not None:
            child_fields.append({"name": name, "value": field["default"]})
        elif field.get("type") in ("date", "datetime"):
            child_fields.append({"name": name, "now": True})
        else:
            return None
    prepared = []
    anchor = None
    id_param = ""
    for eff in [e for e in effects if e["kind"] != "create_child"]:
        cls = eff.get("cls") or _effect_entity(
            entities_by_class, eff.get("entity")
        )
        if not cls:
            return None
        if anchor is None:
            anchor = cls
            id_param = _id_param_for(cls, params) or ""
        target = _effect_target(cls, anchor, entities_by_class)
        if target is None:
            return None
        prepared.append(dict(eff, cls=cls, target=target))
    if anchor is None:
        # A pure insert ("records a payment"): anchor on the child's own id if
        # the method names one, else on the child itself.
        id_param = _id_param_for(child_cls, params) or ""
        if not id_param:
            return None
        anchor = child_cls
    return {
        "kind": "create_child_row",
        "entity": _snake(anchor),
        "id_param": id_param,
        "child": child_cls,
        "child_fields": child_fields,
        "effects": prepared,
        "guards": contract_guards_for(contract, entities_by_class),
    }


def compile_contract_impl(contract, entities_by_class, params=None, returns="",
                          prompt_text=""):
    """A renderable ``impl`` for this contract, or None when not exactly so.

    Deliberately narrow so a deterministic recipe can never SHADOW a body
    that already works:

      * exactly ONE parameter, naming the anchor entity's row id;
      * a ``bool`` (or unannotated) return — a workflow method, not a report;
      * at least one resolved effect, and NO ``create_child`` (inserting a
        child row needs required-field stamping that the fill already does);
      * NO guards (a guarded workflow keeps its LLM fill, which sees the
        designed exceptions);
      * every effect reachable from the anchor (its own row, or one FK hop).

    Returns ``{"kind": "contract_effects", "entity": <anchor snake>,
    "id_param": ..., "effects": [...]}``.
    """
    # A COMPOUND report comes first: when the specification names the pieces
    # the method must return, the parts decide the body — an effects/period
    # render would answer only one piece of it (S1/S2).
    report = _report_impl(contract, entities_by_class, params, returns)
    if report is not None:
        return report
    effects = contract_effects_for(contract, entities_by_class)
    if not effects and prompt_text:
        # The extractor's evidence closure can drop a line the specification
        # states plainly (borrow_book). Read the method's OWN line literally
        # and use it, so a stated workflow is rendered deterministically
        # instead of being left to a 4B fill that has already shipped it as a
        # dead stub.
        derived = spec_line_effects(
            contract.get("name") or "", prompt_text, entities_by_class
        )
        if derived.get("effects"):
            contract = dict(contract)
            contract["effects"] = derived["effects"]
            contract["guards"] = derived.get("guards") or []
            effects = contract_effects_for(contract, entities_by_class)
    # A stated INSERT workflow (a counter moved plus a child row created) is
    # served by the dedicated recipe — which renders its GUARDS too, from the
    # design's own exception classes. It is therefore decided BEFORE the guard
    # gate below: honouring that gate first kept library_system's borrow_book
    # on its LLM fill ("checks availability, creates loan, decrements
    # copies"), so whether borrowing worked at all depended on the fill's
    # luck — one run shipped it as a dead ``return False`` stub.
    if any(e["kind"] == "create_child" for e in effects):
        impl = _create_child_impl(
            contract, entities_by_class, params, returns, effects
        )
        if impl is not None:
            return impl
    if not effects:
        # No state change stated: the method is a READ whose contract is a
        # restricting parameter over a period. That shape is exactly
        # renderable as a bucketed total (the `total_in_period` recipe), and
        # it is what the monthly/yearly report methods need — the S1/S2
        # defects are a report that ignores its month/year argument.
        return _period_impl(contract, entities_by_class, params, returns)
    guards = [
        g for g in contract_guards_for(contract, entities_by_class)
        if not _contradicts_flag_effect(g, effects)
    ]
    if guards:
        return None
    if any(e["kind"] == "create_child" for e in effects):
        # Reached only when ``_create_child_impl`` DECLINED the shape (a
        # required column no parameter, default or "now" can stamp): the fill
        # keeps the method.
        return None
    ret = (returns or "").strip().lower()
    # ``Optional[bool]`` is the SAME workflow: the design merely annotates a
    # best-effort result, and the deterministic effect body returns a bool.
    # Declining it left ``return_book`` to the LLM fill, which re-introduced a
    # lateness guard the specification never states ("an overdue loan is the
    # normal case for a return") — S9 regressed to a fill-luck invariant.
    if ret.startswith("optional[") and ret.endswith("]"):
        ret = ret[len("optional["):-1].strip()
    elif ret.endswith("| none"):
        ret = ret[: -len("| none")].strip()
    if ret and ret not in ("bool", "boolean"):
        return None
    params = list(params or [])
    if len(params) != 1:
        return None
    anchors = [
        cls for cls in (entities_by_class or {})
        if _id_param_for(cls, params) == params[0]
    ]
    if len(anchors) != 1:
        # An ambiguous ``id`` param names no single entity, and a param that
        # names none at all cannot anchor a workflow.
        return None
    anchor = anchors[0]
    prepared = []
    for eff in effects:
        target = _effect_target(eff["cls"], anchor, entities_by_class)
        if target is None:
            return None
        prepared.append(dict(eff, target=target))
    return {
        "kind": "contract_effects",
        "entity": _snake(anchor),
        "id_param": params[0],
        "effects": prepared,
    }


# A parameter whose NAME carries one of these denotes a time window over the
# entity's own date column. Design-only: the token must appear in the
# parameter name the spec/design already fixed.
_PERIOD_TOKENS = ("month", "year", "period", "week", "quarter", "annee", "mois")


def _period_impl(contract, entities_by_class, params, returns):
    """A ``total_in_period`` impl for a period-scoped report, or None.

    Fires only when the contract's restricting parameters include a
    TIME-WINDOW name, the return is a Dict/number, and exactly ONE designed
    entity has a single date/datetime column plus a single numeric non-FK
    column — the shape the recipe can sum without guessing. Anything else
    keeps its LLM fill.
    """
    params = list(params or [])
    ret = (returns or "").strip().lower()
    if not any(t in ret for t in ("dict", "int", "float")):
        return None
    period = next(
        (
            p for p in (contract.get("filters") or [])
            if p in params and any(t in p for t in _PERIOD_TOKENS)
        ),
        None,
    )
    if period is None:
        return None
    cands = []
    for cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict):
            continue
        fields = [
            f for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name") and f["name"] != "id"
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
        if len(dates) == 1 and len(nums) == 1:
            cands.append((cls, dates[0], nums[0]))
    if len(cands) != 1:
        return None
    cls, date_field, value_field = cands[0]
    granularity = "year" if "year" in period or "annee" in period else "month"
    return {
        "kind": "total_in_period",
        "entity": _snake(cls),
        "value_field": value_field,
        "date_field": date_field,
        "period_param": period,
        "granularity": granularity,
        "result_key": "total",
    }
