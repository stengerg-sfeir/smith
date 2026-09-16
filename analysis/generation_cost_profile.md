# Generation cost profile — where the wall time actually goes

Reproduction: `python3 bench.py cost --prompt library_system --prompt expenses`

The harness wraps `agentlib.llm.client._chat_completion`, the single function
every completion in the pipeline funnels through, in **every** namespace that
imported it (`_json_complete` resolves the name as a module global at call
time; `agentlib.llm.fill` and `agentlib.pipeline.generate` import it by name).
No call can bypass the counter. Each call is timed and attributed to its
immediate caller, which identifies the pipeline phase.

> **Correction.** A first version of this document claimed that `expenses` was
> slow because its three code *fills* re-emit large files. The per-caller
> attribution below **falsifies that**: the fill phase costs 23–25 s in both
> projects. The cost lives in the schema-constrained JSON design phase. The
> wrong claim is recorded here rather than quietly deleted because the
> inference looked sound and was only caught by measuring the caller.

## Headline

| metric | `library_system` | `expenses` | exp / lib |
|---|---|---|---|
| wall time (s) | 222.6 | 380.5 | 1.71 |
| total LLM time (s) | 222.3 | 380.0 | 1.71 |
| calls, total | 21 | 19 | 0.90 |
| calls, **code fills** | 3 | 3 | 1.00 |
| calls, schema JSON (design) | 18 | 16 | 0.89 |
| output chars, total | 31 207 | 54 866 | 1.76 |
| input chars, total | 79 474 | 95 514 | 1.20 |
| ms per output char | 7.12 | 6.93 | 0.97 |

`expenses` makes **fewer** calls than `library_system` (19 vs 21) and the
**same** number of code fills (3 vs 3). The number of CLI commands in the
prompt has no bearing on the cost.

## Cost by phase

| phase (immediate caller of `_chat_completion`) | lib calls | lib s | lib out | exp calls | exp s | exp out | Δ s |
|---|---|---|---|---|---|---|---|
| `method_contract.py:extract_method_contracts` | 3 | 33.6 | 4 730 | 3 | **98.4** | 14 791 | **+64.8** |
| `design.py:_design_module` | 7 | 78.4 | 10 160 | 6 | **124.9** | 16 192 | **+46.5** |
| `intents.py:extract_intentions` | 1 | 24.5 | 3 366 | 1 | **51.5** | 7 668 | **+27.0** |
| `service_contract.py:extract_service_contract` | 1 | 16.8 | 2 480 | 1 | **33.9** | 5 316 | **+17.1** |
| `fill.py:_llm_fill` (**code fills**) | 3 | 23.3 | 3 439 | 3 | 24.7 | 3 983 | +1.4 |
| `design.py:_llm_classify_repo_feasibility` | 4 | 32.2 | 5 272 | 3 | 31.9 | 5 312 | −0.3 |
| `design.py:_generate_manifest` | 1 | 11.8 | 1 743 | 1 | 12.4 | 1 587 | +0.6 |
| `design.py:_route_mode` | 1 | 1.8 | 17 | 1 | 2.2 | 17 | +0.4 |
| **total** | **21** | **222.3** | **31 207** | **19** | **380.0** | **54 866** | **+157.7** |

Three phases account for **+138 s of the +158 s** difference: method-contract
extraction, per-module design, and intent extraction. The code fills are
`+1.4 s` — a rounding error.

## The constant

Wall time is set by **how much text the model has to write**, because decode is
sequential and dominates prefill. Throughput is essentially a constant across
both projects *and* both phases:

| phase | library ms/char | expenses ms/char |
|---|---|---|
| schema JSON (`_json_complete`) | 7.17 | 6.98 |
| code fill (`_llm_fill`, streamed) | 6.78 | 6.20 |
| **overall** | **7.12** | **6.93** |

The time ratio between the projects (1.71) tracks the output-char ratio (1.76)
almost exactly. Nothing in the cost profile is explained by command count,
entity count, or file count — only by emitted characters.

## The one avoidable cost: a rejected contract re-emission

`extract_method_contracts` was called 3× in each project, but the shape
differs:

| | library_system | expenses |
|---|---|---|
| call 1 | 29.3 s, 4 153 chars | 60.2 s, 9 161 chars |
| retry 1 | 2.4 s, 303 chars | **35.7 s, 5 290 chars** |
| retry 2 | 1.9 s, 274 chars | 2.5 s, 340 chars |

`library_system`'s retries collapsed to ~300 chars — the model gave up cheaply.
`expenses`' first retry re-emitted a **full** 5 290-char contract document:
the first attempt produced schema-valid JSON that
`_accept_method_contracts` rejected on semantic grounds, so the whole
extraction was paid a second time. That single retry is ~23 % of the total
delta between the two projects.

This is the only place in the profile where the generator pays twice for the
same thing. A rejection that is detectable from the *prompt* (rather than from
the model's output) could be prevented before the call instead of after.

## Two levers, and which one actually matters

1. **Fewer / smaller design calls.** All the money is here. The three
   expensive phases enumerate the whole domain as JSON: intents, module
   designs, service contract, method contracts. Every duplicate design of the
   same entity is a full extra emission.
2. **Fewer fills.** The deterministic recipes in `agentlib/kernel/service/`
   have already done their job: in both projects the service-fill path never
   fired, and only 3 repository fills remain (`repo_render.py`). At 23–25 s
   and ~6 % of wall time, driving fills to zero would be a marginal win.

The earlier (wrong) conclusion inverted these two priorities. Measured, the
generator's cost is a **design-phase** problem, not a fill problem.
---

**Nomenclature (commit `296211d`).** Les scripts `run_*.py` cités dans ce
document sont regroupés dans `agentlib/bench/` derrière l'unique point d'entrée
`bench.py` (`agent.py` reste le générateur) ; le paquet `behavior_tests/` est
devenu `agentlib/bench/`. Traduction, suites et options inchangées :
`run_named_prompts.py`→`bench.py named`, `run_cli_conformity.py`→`bench.py
cli-conformity`, `run_repo_conformity.py`→`bench.py repo-conformity`,
`run_semantic_oracle.py`→`bench.py semantic`, `run_cli_behavior.py`→`bench.py
cli-behavior`, `run_facade_execution.py`→`bench.py facade-exec`,
`run_facade_intents.py`→`bench.py facade-intents`, `run_facade_all.py`→`bench.py
facade-all`, `run_surface_smoke.py`→`bench.py surface`, `run_cost_profile.py`→
`bench.py cost`, `run_generation_floors_unit.py`→`bench.py floors`,
`run_repo_pruner_unit.py`→`bench.py pruners`, `run_claude_baseline.py`→`bench.py
claude`, `run_behavior_tests.py`→`bench.py behavior`.
