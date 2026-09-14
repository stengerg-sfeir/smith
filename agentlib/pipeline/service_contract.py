"""Spec-derived INTERNAL service contract (the missing anchor).

The pipeline already extracts two structured artifacts from the prompt — the
user intentions and the CLI surface (external behaviour) — and the design
phase then invents the internal contract (service methods + bodies). Nothing
ties that internal contract back to what the prompt actually states about the
INTERNAL behaviour, so a spec method with no CLI command silently disappears
(library_system: ``renew_membership``) and a wrong name can replace a real one
(``borrow_book`` -> ``borrow_member``).

This module extracts the service methods the prompt EXPLICITLY declares and
makes them a checkable requirement. Extraction is EVIDENCE-CLOSED: every entry
must carry a verbatim span of the prompt that justifies it, and an entry whose
span is not found in the prompt is dropped. So an underspecified prompt yields
few/no required methods (never invented ones), while an explicit one yields its
declared list. Everything the design adds beyond this stays "synthesized" (its
own soft choice).
"""
from __future__ import annotations

import re

from agentlib.config import LLM_MAX_TOKENS_LONG, LLM_RETRY_TEMPERATURE
from agentlib.llm.client import _json_complete


def service_contract_schema():
    """Schema for the internal-contract extraction pass."""
    param = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    }
    method = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "params": {"type": "array", "items": param},
            "returns": {"type": "string"},
            "effect": {"type": "string"},
            "evidence": {"type": "string"},
        },
        "required": ["name", "effect", "evidence"],
        "additionalProperties": False,
    }
    obligation = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "evidence": {"type": "string"},
        },
        "required": ["text", "evidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "service_class": {"type": "string"},
            "required_methods": {"type": "array", "items": method},
            "obligations": {"type": "array", "items": obligation},
        },
        "required": ["required_methods", "obligations"],
        "additionalProperties": False,
    }


_SERVICE_CONTRACT_SYSTEM = (
    "You are an expert requirement analyst. Given a software specification, "
    "extract the INTERNAL SERVICE CONTRACT it EXPLICITLY states.\n\n"
    "The internal service contract is the set of business-logic methods the "
    "spec names or unmistakably describes (\"borrow_book(member_id, book_id): "
    "checks availability, creates loan, decrements copies\"), plus non-method "
    "obligations the spec states in prose (\"Provide CRUD operations for "
    "products and sales\", \"all monetary values stored as integer cents\").\n\n"
    "For EACH required method emit:\n"
    "- name: the method name the spec uses, snake_case. If the spec describes "
    "the behaviour without naming a method, choose the most direct snake_case "
    "name.\n"
    "- params: the parameters the spec states (name + primitive type). Omit "
    "when the spec does not state them.\n"
    "- returns: the return type/shape the spec states, or empty.\n"
    "- effect: ONE short sentence of the behaviour the spec states.\n"
    "- evidence: the EXACT substring of the specification that states this "
    "method/behaviour, copied VERBATIM. This is mandatory and is verified.\n\n"
    "For EACH obligation emit {text, evidence} the same way.\n\n"
    "HARD RULES — an unsupported entry is DISCARDED:\n"
    "- Emit ONLY what the specification states. NEVER invent a method, a "
    "parameter, or a behaviour the text does not state.\n"
    "- Do NOT emit CRUD methods for an entity unless the text states CRUD for "
    "it (in that case prefer ONE obligation, not five invented methods).\n"
    "- If the specification states no internal service behaviour, return "
    "EMPTY arrays. An empty result is a valid, expected answer.\n"
    "- evidence MUST be copied verbatim from the specification; a paraphrase "
    "is discarded.\n"
    "Read ONLY the specification — never the code."
)
def _norm_span(text):
    """Casefold + whitespace-collapse + strip surrounding quote/backtick."""
    s = (text or "").strip()
    s = s.strip("\"'` \t\n")
    s = re.sub(r"\s+", " ", s)
    return s.casefold()


_PUNCT_RE = re.compile(r"[^\w ]+")


def _evidence_ok(evidence, prompt_norm):
    """True when the (normalized) evidence appears in the prompt.

    Tolerant of case/whitespace and of surrounding quote/backtick punctuation;
    a paraphrase that genuinely is not in the text does NOT match.
    """
    ev = _norm_span(evidence)
    if len(ev) < 4:
        return False
    if ev in prompt_norm:
        return True
    ev2 = _PUNCT_RE.sub(" ", ev).strip()
    pn2 = _PUNCT_RE.sub(" ", prompt_norm).strip()
    ev2 = re.sub(r"\s+", " ", ev2)
    pn2 = re.sub(r"\s+", " ", pn2)
    return bool(ev2) and len(ev2) >= 4 and ev2 in pn2
_NAME_STRIP_RE = re.compile(r"[^a-z0-9_]+")


def _snake_name(raw):
    """Normalize a method/param name to a snake_case identifier (or "")."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip().strip("\"'`")
    s = s.split("(", 1)[0].strip()
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s).lower()
    s = s.replace("-", "_").replace(" ", "_")
    s = _NAME_STRIP_RE.sub("", s)
    s = re.sub(r"_{2,}", "_", s).strip("_")
    return s if re.fullmatch(r"[a-z_][a-z0-9_]*", s) else ""
def extract_service_contract(prompt_text, verbose=False):
    """Extract the evidence-closed internal service contract.

    Returns ``{"service_class": str, "required_methods": [...],
    "obligations": [...]}`` with every entry evidence-verified against the
    prompt. Returns an empty contract on any failure (never blocks the
    pipeline).
    """
    user = (
        "SPECIFICATION:\n%s\n\nExtract the internal service contract now."
        % prompt_text
    )
    messages = [
        {"role": "system", "content": _SERVICE_CONTRACT_SYSTEM},
        {"role": "user", "content": user},
    ]
    prompt_norm = _norm_span(prompt_text)
    empty = {"service_class": "", "required_methods": [], "obligations": []}
    for attempt in range(2):
        data = _json_complete(
            messages, schema=service_contract_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
            temperature=0.0 if attempt == 0 else LLM_RETRY_TEMPERATURE,
        )
        if isinstance(data, dict):
            return _accept_contract(data, prompt_norm, verbose)
    return empty
def _accept_contract(data, prompt_norm, verbose):
    """Evidence-verify an extracted contract; drop unsupported entries."""
    methods, obligations, dropped = [], [], 0
    for m in data.get("required_methods") or []:
        if not isinstance(m, dict):
            continue
        name = _snake_name(m.get("name"))
        if not name or not _evidence_ok(m.get("evidence"), prompt_norm):
            dropped += 1
            continue
        params = []
        for p in m.get("params") or []:
            if not isinstance(p, dict):
                continue
            pn = _snake_name(p.get("name"))
            if pn:
                params.append(
                    {"name": pn, "type": (p.get("type") or "str").strip()}
                )
        methods.append({
            "name": name,
            "params": params,
            "returns": (m.get("returns") or "").strip(),
            "effect": (m.get("effect") or "").strip(),
            "evidence": (m.get("evidence") or "").strip(),
        })
    for o in data.get("obligations") or []:
        if not isinstance(o, dict):
            continue
        text = (o.get("text") or "").strip()
        if not text or not _evidence_ok(o.get("evidence"), prompt_norm):
            dropped += 1
            continue
        obligations.append({
            "text": text,
            "evidence": (o.get("evidence") or "").strip(),
        })
    if verbose and dropped:
        print("    [contract] dropped %d unsupported entr(ies)" % dropped)
    out = {
        "service_class": (data.get("service_class") or "").strip(),
        "required_methods": methods,
        "obligations": obligations,
    }
    if verbose:
        print("    [contract] required methods: %s" % (
            ", ".join(m["name"] for m in methods) or "(none)"))
    return out
def service_contract_constraint(contract):
    """Human-readable constraint appended to every service-design call.

    Mirrors ``cli_surface_constraint`` but is anchored to the SPEC instead of
    the CLI surface. The design MUST include every listed method (compatible
    name/signature) and may add more.
    """
    if not contract:
        return ""
    methods = contract.get("required_methods") or []
    obligations = contract.get("obligations") or []
    if not methods and not obligations:
        return ""
    lines = [
        "THE SPECIFICATION DECLARES THE FOLLOWING INTERNAL SERVICE BEHAVIOUR. "
        "Your service MUST include every method below, using EXACTLY the given "
        "name and a compatible signature. You MAY add other methods the CLI "
        "surface requires.",
    ]
    for m in methods:
        sig = ", ".join(
            "%s: %s" % (p["name"], p["type"]) for p in (m.get("params") or [])
        )
        lines.append("  %s(%s) -> %s — %s"
                     % (m["name"], sig, m.get("returns") or "",
                        m.get("effect") or ""))
    if obligations:
        lines.append("MANDATORY OBLIGATIONS (from the specification):")
        for o in obligations:
            lines.append("  - %s" % o["text"])
    return "\n".join(lines)


def apply_service_contract_floors(contract, svc_design, entities_by_class):
    """Add the spec-declared methods the design omitted, when bodyable.

    ``service_contract_constraint`` TELLS the design to include every
    spec-declared method, but the 4B pass still drops some (expenses lost
    ``update_expense`` and ``delete_expense``, so two paths the
    specification authorizes raised AttributeError). This floor restores
    them deterministically — but ONLY the shapes the deterministic service
    renderer can body exactly from the designed repository API:

      * ``delete_<entity>(id)``        -> ``self.<e>_repo.delete(id)``
      * ``update_<entity>(id, ...)``   -> ``self.<e>_repo.update(id, data)``

    Any other missing method is left to ``check_service_contract``: adding
    a method with no deterministic body would ship a locked stub raising
    NotImplementedError on a spec-authorized path, which is strictly worse
    than the method's absence. Returns the sorted names actually added.
    """
    if not contract or not isinstance(svc_design, dict):
        return []
    methods = contract.get("required_methods") or []
    if not methods:
        return []
    known = {_snake_name(c) for c in (entities_by_class or ())}
    designed = {
        _snake_name(m.get("name"))
        for m in svc_design.get("methods") or []
        if isinstance(m, dict) and m.get("name")
    }
    added = []
    for m in methods:
        name = _snake_name(m.get("name"))
        if not name or name in designed:
            continue
        params = [
            p for p in (m.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        pnames = [_snake_name(p["name"]) for p in params]
        shape = None
        for verb in ("delete_", "update_"):
            if name.startswith(verb) and name[len(verb):] in known:
                rest = pnames[1:]
                if verb == "delete_" and pnames == ["id"]:
                    shape = verb
                elif verb == "update_" and rest and "id" in pnames[:1]:
                    shape = verb
                break
        if shape is None:
            continue
        svc_design.setdefault("methods", []).append({
            "name": name,
            "params": [
                {"name": pn, "type": pt or "Any"}
                for pn, pt in zip(pnames, [p.get("type") for p in params])
            ],
            "returns": m.get("returns") or "bool",
        })
        designed.add(name)
        added.append(name)
    return sorted(added)


def check_service_contract(contract, svc_design):
    """Coverage violations: required spec methods absent from the design.

    Returns a list of human-readable strings (empty = fully covered). Only
    ``required_methods`` are enforced; everything else the design adds is its
    own choice.
    """
    if not contract:
        return []
    methods = contract.get("required_methods") or []
    if not methods:
        return []
    designed = {
        _snake_name(m.get("name")): m
        for m in (svc_design or {}).get("methods") or []
        if isinstance(m, dict) and m.get("name")
    }
    violations = []
    for m in methods:
        name = _snake_name(m.get("name"))
        got = designed.get(name)
        if got is None:
            violations.append(
                "spec declares service method %r (%s) but the design omits it"
                % (name, m.get("effect") or "")
            )
            continue
        want = [p["name"] for p in (m.get("params") or [])]
        have = [
            _snake_name(p.get("name"))
            for p in (got.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        missing = [p for p in want if p not in have]
        if missing:
            violations.append(
                "spec declares %s(%s) but the design has %s(%s) — missing %s"
                % (name, ", ".join(want), name, ", ".join(have),
                   ", ".join(missing))
            )
    return violations
def apply_service_contract_params(contract, svc_design):
    """Rename designed params to the spec-declared names they fulfil.

    ``service_contract_constraint`` tells the design to use the spec's own
    parameter names, but the 4B pass paraphrases a role: the specification
    declares ``list_expenses(category_id, start_date, end_date,
    payment_method)`` and the design shipped
    ``list_expenses(category_id, from_date, to_date, payment_method)``.
    ``check_service_contract`` reported it, and nothing repaired it — so a
    caller who followed the specification got a TypeError, even though the
    CLI option (``--from-date``) was correctly bound.

    The rename is applied ONLY when it is UNAMBIGUOUS:

      * the spec method is present in the design;
      * some spec param is absent and the design carries exactly as many EXTRA
        params as there are missing ones (so a rename is a permutation, never
        a guess);
      * the two names denote the same RANGE ROLE (lower bound: ``start_``,
        ``from_``, ``after_``, ``since_``; upper bound: ``end_``, ``to_``,
        ``until_``, ``before_``) — the same role vocabulary the filter pairing
        already uses, so a ``from_date`` is exactly the ``start_date`` the
        specification named.

    Nothing is renamed when a role is absent or ambiguous; the violation is
    then still reported by ``check_service_contract``. Returns the list of
    ``<method>.<old>-><new>`` renames actually applied.
    """
    if not contract or not isinstance(svc_design, dict):
        return []
    from agentlib.kernel.service.common import _range_role

    by_name = {
        _snake_name(m.get("name")): m
        for m in svc_design.get("methods") or []
        if isinstance(m, dict) and m.get("name")
    }
    renames = []
    for spec_m in contract.get("required_methods") or []:
        if not isinstance(spec_m, dict):
            continue
        name = _snake_name(spec_m.get("name"))
        got = by_name.get(name)
        if got is None:
            continue
        want = [
            _snake_name(p.get("name")) for p in (spec_m.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        want = [w for w in want if w]
        live = [
            p for p in (got.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        have = [_snake_name(p["name"]) for p in live]
        missing = [w for w in want if w not in have]
        if not missing:
            continue
        extra = [p for p, h in zip(live, have) if h not in want]
        if len(extra) != len(missing):
            continue
        for want_name in missing:
            role = _range_role(want_name)
            if role is None:
                continue
            cand = next(
                (
                    p for p in extra
                    if _range_role(_snake_name(p["name"])) == role
                ),
                None,
            )
            if cand is None:
                continue
            old = _snake_name(cand["name"])
            cand["name"] = want_name
            extra.remove(cand)
            renames.append("%s.%s->%s" % (name, old, want_name))
    return renames
