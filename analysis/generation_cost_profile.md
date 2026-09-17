# Generation cost profile — where the wall time goes, and what it consumes

Reproduction (from the repository root, with the local server up):

```bash
python3 bench.py cost --prompt hello_world --prompt cli_tool \
  --prompt multi_module --prompt library_system --prompt inventory \
  --prompt expenses --json analysis/generation_cost_profile.json
```

Every number below comes from `analysis/generation_cost_profile.json`, written
by that command. The document is a *reading* of the artifact, not a transcript
of a terminal.

## What is instrumented

The harness wraps `agentlib.llm.client._chat_completion`, the single function
every completion in the pipeline funnels through, in **every** namespace that
imported it (`_json_complete` resolves the name as a module global at call time;
`agentlib.llm.fill` and `agentlib.pipeline.generate` import it by name). No call
can bypass the counter.

Three units are recorded, because only one of them is available everywhere:

| unit | how it is obtained | coverage |
|---|---|---|
| **seconds** | timed around each call | every call |
| **chars** | `len()` of the message contents and of the returned text | every call |
| **tokens** | the `usage` block llama-server returns | 63 of 75 calls |

The 12 calls that carry no `usage` are exactly the **streamed code fills**
(`fill.py:_llm_fill`); their cost is known in seconds and chars, not tokens.
Every token total in this document is therefore printed next to the number of
calls it covers, so no total can be read as if it covered all of them.

## Headline — the six named prompts, one run

| prompt | wall (s) | LLM (s) | calls | chars in | chars out | tokens in | tokens out | source (chars / files) |
|---|---|---|---|---|---|---|---|---|
| `hello_world` | 1.9 | 1.9 | 2 | 1 193 | 142 | 291 | 43 | 87 / 1 |
| `cli_tool` | 11.4 | 11.4 | 2 | 1 655 | 1 796 | 377 | 417 | 1 764 / 1 |
| `multi_module` | 138.1 | 138.0 | 14 | 41 278 | 20 127 | 7 448 | 3 585 | 11 401 / 7 |
| `library_system` | 220.6 | 220.4 | 20 | 73 156 | 30 548 | 14 500 | 6 778 | 30 930 / 10 |
| `inventory` | 241.1 | 240.9 | 18 | 81 688 | 34 341 | 13 482 | 7 509 | 20 159 / 8 |
| `expenses` | 402.6 | 402.4 | 19 | 96 042 | 57 179 | 19 548 | 12 905 | 40 146 / 10 |
| **total** | **1 015.8** | **1 015.0** | **75** | **295 012** | **144 133** | **55 646** | **31 237** | **104 487 / 37** |

Two things to read off it directly:

* **The wall clock is the LLM.** 1 015.0 of 1 015.8 s is spent inside
  `_chat_completion`; the entire deterministic pipeline (manifest, AST rendering,
  SQLite schema, click wiring, ruff, validation) costs **0.8 s across six
  projects**. There is no hidden second cost centre.
* **A run is not bit-reproducible at the call level.** Two runs made an hour
  apart produced 22 and 20 calls for `library_system`, with 36 027 and 30 548
  output chars. The sampling is seeded (`temp=0`, `seed=42`) but the retry path
  is not (`LLM_RETRY_TEMPERATURE`), so any prompt that retries once varies. The
  artifact is the record of **one** run, and comparisons that matter (a
  regression, a phase's share) are stable across these two runs; absolute
  per-call counts are not.

## The constant

Wall time is set by **how much text the model has to write**, because decode is
sequential and dominates prefill. Throughput is essentially a constant across
prompts of very different shapes:

| prompt | ms per output char |
|---|---|
| `cli_tool` | 6.32 |
| `multi_module` | 6.86 |
| `inventory` | 7.02 |
| `expenses` | 7.04 |
| `library_system` | 7.22 |
| `hello_world` | 13.45 |
| **all six** | **7.04** |

`hello_world` is the exception that proves the rule: 142 output chars is too
little for prefill and fixed overhead (one 669-char prompt eval) to be amortised,
so its ms/char is ~2× the rest. Above ~2 000 output chars the ratio is stable
within ±7 %, which is what makes "the cost is the output volume" a usable
predictor rather than a slogan.

## Cost by phase

The four prompts that go through the manifest pipeline, phase by phase (the
immediate caller of `_chat_completion`, i.e. the pipeline phase):

| phase | `multi_module` | `library_system` | `inventory` | `expenses` | total (s) | share |
|---|---|---|---|---|---|---|
| `design.py:_design_module` | 4 calls / 34.9 | 7 / 78.8 | 6 / 82.4 | 6 / 127.9 | **324.0** | 31.9 % |
| `method_contract.py:extract_method_contracts` | 3 / 35.0 | 2 / 32.7 | 2 / 52.5 | 3 / 117.1 | **237.3** | 23.4 % |
| `intents.py:extract_intentions` | 1 / 12.6 | 1 / 23.5 | 1 / 29.0 | 1 / 50.9 | **116.0** | 11.4 % |
| `fill.py:_llm_fill` (**code fills**) | 2 / 36.5 | 3 / 22.6 | 4 / 25.6 | 3 / 24.6 | **109.3** | 10.8 % |
| `design.py:_llm_classify_repo_feasibility` | 1 / 7.3 | 4 / 32.4 | 2 / 13.0 | 3 / 32.9 | **85.6** | 8.4 % |
| `service_contract.py:extract_service_contract` | 1 / 3.5 | 1 / 17.2 | 1 / 25.4 | 1 / 34.5 | **80.6** | 7.9 % |
| `design.py:_generate_manifest` | 1 / 7.4 | 1 / 11.9 | 1 / 11.4 | 1 / 12.4 | **43.1** | 4.2 % |
| `design.py:_route_mode` | 1 / 0.7 | 1 / 1.4 | 1 / 1.7 | 1 / 2.1 | **5.9** | 0.6 % |

Add `hello_world` (1.9 s, single-pass) and `cli_tool` (11.4 s, single-pass) for
the 1 015.0 s total. **89.2 % of the bill is the design phase** — schema-bound
JSON that enumerates the domain (intents, module designs, service and method
contracts). The code fills — the part of the pipeline that writes method bodies
— are **10.8 %**.

Three observations that only the per-phase table supports:

* **The number of CLI commands in the prompt does not drive cost; the size of
  the JSON the model must emit does.** `expenses` declares more commands than
  `library_system` and costs 1.8× more, because every phase emits more
  characters for it (57 179 vs 30 548).
* **`extract_method_contracts` is the most volatile phase**: 35.0 s on
  `multi_module` and 117.1 s on `expenses`, for the same 3 calls. Its cost is
  dominated by one or two large re-emissions.
* **The cheapest phases are the ones that decide structure** (`_generate_manifest`
  4.2 %, `_route_mode` 0.6 %). The pipeline's determinism is bought cheaply; the
  money is in the domain detail.

## The one avoidable cost: a rejected contract re-emission

In `expenses`, `extract_method_contracts` was called 3× for 117.1 s and
17 096 output chars, and the detail makes the shape explicit:

| call | seconds | output chars |
|---|---|---|
| 1 | 62.6 | 9 161 |
| retry | **37.3** | **5 438** |
| retry | 17.2 | 2 497 |

The first attempt produced schema-valid JSON that `_accept_method_contracts`
rejected on *semantic* grounds, so the whole extraction was paid a second time —
a full 5 438-char re-emission, not a short corrective answer. That single retry
is **3.7 % of the six-prompt total** and a third of the phase's own cost in that
project.

This is the only place in the profile where the generator pays twice for the
same thing. A rejection that is detectable from the *prompt* (rather than from
the model's output) could be prevented before the call instead of after.

## Two levers, and which one actually matters

1. **Fewer / smaller design calls.** All of the money is here: the four
   domain-enumerating phases (`_design_module`, `extract_method_contracts`,
   `extract_intentions`, `extract_service_contract`) are **758.0 s — 74.7 %** of
   the run. Every duplicate design of the same entity is a full extra emission.
2. **Fewer fills.** The deterministic recipes in `agentlib/kernel/service/` have
   already done their job: the service-fill path never fires, and only 12 code
   fills remain across four projects. At 109.3 s and 10.8 %, driving fills to
   zero is a real but bounded win — note that the single slowest call of
   `multi_module` is nevertheless one of them (31.1 s, 5 319 chars, no `usage`).

The conclusion the phases support is the counter-intuitive one: this generator's
cost is a **design-phase** problem, not a fill problem. Optimising the part that
writes code would touch an eighth of the bill.

## Instrument defects this document depends on being fixed

A cost profile is only as good as its counter, and this one had two defects that
had to be repaired before any of the numbers above meant anything:

* a wrapper **stacked once per prompt**, multiplying every count by the prompt's
  position in the run (which is how a run first reported *more LLM seconds than
  wall-clock seconds*);
* a call chain that stopped at the client's own `_json_complete` instead of the
  pipeline phase, which would have labelled every line of the table above
  `client.py:_json_complete`.

Both, and the invariant that catches the first (`llm_seconds <= wall_seconds`),
are described in [`claude_vs_generator.md`](claude_vs_generator.md), section
"The harness that measures the cost had to be fixed too". They are recorded here
as well because the numbers in *this* file are the ones they were corrupting.

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
