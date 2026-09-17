# The generator vs Claude Code, on the same six specifications

Harness: `python3 bench.py claude` (external reference) and
`python3 bench.py cost --json analysis/generation_cost_profile.json` (this
generator). Each `prompts/prompt_<ident>.txt` is passed **verbatim** to
non-interactive Claude Code (`claude -p`, `--output-format json`, empty working
directory, no session persistence), plus one imperative tail asking for the full
runnable implementation. The result is then subjected to the **same** gates as
the generator: `functional_failures`, `conformity_failures` and `conformity`'s
prompt→surface check, from `agentlib.bench.named_prompt_suite`.

Runs behind this document, all on 2026-09-17:

| run | command | wall | kept in |
|---|---|---|---|
| generator | `bench.py cost --json analysis/generation_cost_profile.json` | 1 015.8 s | `analysis/generation_cost_profile.json` |
| Claude Haiku 4.5 | `bench.py claude` | 483.5 s | `baseline/…` + `analysis/claude_baseline_report.json` |
| Claude Sonnet 5 | `bench.py claude --label sonnet` | 1 108.5 s | `baseline/sonnet/…` + `analysis/claude_baseline_report_sonnet.json` |

## What is measured, and what each unit is worth

Nothing below is quoted from a terminal session. Three artifacts carry every
number, and each has a machine-readable twin next to it:

| artifact | what it holds |
|---|---|
| `analysis/generation_cost_profile.json` | the generator: per call and per phase — seconds, chars in/out, tokens the local server reported, and the size of the project written |
| `analysis/claude_baseline_report.json` | Haiku: per project — wall, turns, cost, tokens (from the CLI payload), prompt chars, source chars, verdicts |
| `analysis/claude_baseline_report_sonnet.json` | the same for Sonnet |

The units are deliberately kept apart, because two of the three are not the
same claim:

* **`source (chars)`** is the deliverable, read back off disk. It is now
  **the same measurement on both sides**: the generator's `_source_metrics` and
  the Claude harness both count `**/*.py` and nothing else. (Until this pass the
  Claude side also counted README and `requirements.txt`, which would have
  credited it with prose the generator never writes — the comparison table
  would have been 18 % fiction. The full project size is reported per prompt in
  the baseline report, for context, and never compared.)
* **tokens** are each API's own accounting. Claude's `input_tokens` *excludes*
  what it re-read from its cache (`cache_read_input_tokens`, printed
  separately); the generator's `prompt_tokens` is the prefill of one
  schema-constrained call. A Claude run is an agentic loop over a whole
  repository; a generator run is 75 narrow calls. No "tokens" column below is
  presented as a like-for-like ratio.

## Consommation des six projets

`chars` = Python source only, both sides. `tokens` = each side's own accounting;
for the generator they cover **63 of its 75 calls** (the streamed code fills
report no `usage`), for Claude they are the CLI's own `usage` block.

| prompt | générateur source (chars / fichiers) | générateur tokens in / out | Haiku source (chars / fichiers) | Haiku tokens in / out | Sonnet source (chars / fichiers) | Sonnet tokens in / out |
|---|---|---|---|---|---|---|
| `cli_tool` | 1 764 / 1 | 377 / 417 | 3 950 / 1 | 66 / 3 383 | 3 086 / 1 | 20 / 3 754 |
| `expenses` | 40 146 / 10 | 19 548 / 12 905 | 40 003 / 8 | 122 / 15 929 | 42 206 / 9 | 60 / 48 703 |
| `hello_world` | 87 / 1 | 291 / 43 | 111 / 1 | 26 / 595 | 87 / 1 | 4 / 249 |
| `inventory` | 20 159 / 8 | 13 482 / 7 509 | 19 648 / 7 | 90 / 20 612 | 21 537 / 8 | 30 / 18 603 |
| `library_system` | 30 930 / 10 | 14 500 / 6 778 | 31 752 / 7 | 98 / 13 733 | 32 121 / 16 | 2 / 477 |
| `multi_module` | 11 401 / 7 | 7 448 / 3 585 | 10 078 / 9 | 42 / 5 795 | 11 178 / 6 | 40 / 7 642 |
| **total** | **104 487 / 37** | **55 646 / 31 237** | **105 542 / 33** | **444 / 60 047** | **110 215 / 41** | **156 / 79 428** |

The cache read is where most of a Claude run's traffic goes, and a cache figure
without the number of turns it was spread over is not interpretable: the same
1.9 M tokens mean "one enormous context" or "thirty small ones". So the turns are
in the table, and the average is given next to the total — it is the column a
reader would otherwise have to compute by hand.

| prompt | tours | Haiku cache lu (moy. / tour) | Haiku cache écrit | Haiku coût | tours | Sonnet cache lu (moy. / tour) | Sonnet cache écrit | Sonnet coût |
|---|---|---|---|---|---|---|---|---|
| `cli_tool` | 8 | 180 303 (22 538) | 11 183 | 0.0585 | 11 | 308 018 (28 002) | 15 293 | 0.1614 |
| `expenses` | 15 | 462 792 (30 853) | 25 238 | 0.1784 | 30 | 1 966 309 (65 544) | 69 378 | 1.1598 |
| `hello_world` | 3 | 61 328 (20 443) | 4 423 | 0.0190 | 2 | 48 790 (24 395) | 11 424 | 0.0590 |
| `inventory` | 11 | 390 256 (35 478) | 29 211 | 0.2022 | 15 | 632 054 (42 137) | 31 576 | 0.4404 |
| `library_system` | 12 | 338 227 (28 186) | 22 412 | 0.1489 | 1 | 68 996 (68 996) | 2 534 | 1.1833 |
| `multi_module` | 14 | 116 586 (8 328) | 14 043 | 0.0699 | 20 | 687 524 (34 376) | 21 583 | 0.3015 |
| **total** | **63** | **1 549 492 (24 595)** | **106 510** | **0.6769** | **79** | **3 711 691 (46 983)** | **151 788** | **3.3054** |

(The `library_system` Sonnet row is the run whose two accounting blocks disagree
— see the caveat below. One turn cannot have read 69 k tokens of context that
the same block says were never written; its per-model figure is 2 445 011.)

What the two tables actually say:

* **The three produce source of the same order of magnitude — and that is the
  only thing that is the same.** 104 487 chars of Python (generator), 105 542
  (Haiku), 110 215 (Sonnet): within 5 % of each other, on the same six
  specifications. The *deliverables* are not equivalent — they are three
  different programs, and the gates score them 6/6, 2/6 and 4/6 on the
  functional axis. What the table establishes is a comparable **volume** of
  source, measured with the same ruler on a fresh run of all three; it does not
  establish that they produce the same thing, and the verdict table below says
  so.
* **The bill is not the same, and it is not the output that dominates it.**
  Sonnet emits 79 428 output tokens for 110 215 chars of source — about the same
  ratio as the generator's 31 237 tokens for 104 487 chars — but it re-reads
  **3.7 million** cached tokens to do it. The cache column, not the output
  column, is where an agentic loop spends; it is also why Sonnet's six projects
  cost **3.3054 USD** against Haiku's **0.6769** for a comparable deliverable.
* **Far more *cumulative* tokens buy about the same volume of code.** The six
  projects cost **55 646 input tokens** on the generator against **1 716 493**
  (Haiku) and **3 943 063** (Sonnet) counting all four buckets — input, output,
  cache read, cache write. The gap is not in tokens *written*: Sonnet emits
  79 428 output tokens against the generator's 31 237, a factor of 2.5. It is in
  tokens *re-sent*, and that is what the cache column below isolates. The local
  4B model is not writing less because it is cheap; it is writing a comparable
  volume without re-reading anything, and the chequebook stays shut.

### « Le même code pour tous les modèles, mais pas les mêmes tokens ? »

Non : **le code n'est pas le même**, et il ne pourrait pas l'être. Ce qui se
ressemble, c'est son **volume** — et ce volume est une propriété de la
spécification, pas une signature du modèle.

Les chiffres le montrent dès la première ligne du tableau : pour `cli_tool`, le
générateur écrit 1 764 chars dans **1** fichier, Haiku 3 950 dans 1, Sonnet 3 086
dans 1 — trois programmes différents, qui échouent différemment. Pour `expenses`,
Haiku produit 8 fichiers et Sonnet 9. Pour `library_system`, le générateur en
produit 10, Haiku 7, Sonnet 16. Les listes d'échecs ne se recoupent pas : base
fermée trop tôt chez l'un, groupe `category` chez l'autre, en-tête CSV pris pour
une donnée chez le troisième. Si le code était le même, ces listes seraient les
mêmes.

Ce qui est stable, **sur ce corpus**, c'est l'ordre de grandeur : ~105 000 chars
pour six spécifications. Un prompt qui décrit `expense`, `budget`, `category` et
leurs options en a demandé environ 40 000 de Python — ici, aux trois auteurs.
Cela **suggère** que, sur ce banc, la taille du problème contraint davantage le
volume produit que le choix du modèle. Ce n'est pas démontré : six
spécifications et trois implémentations ne suffisent pas, et un développeur
humain comme un modèle peut opter pour une architecture bien plus verbeuse ou
bien plus compacte. C'est une hypothèse à tester sur un corpus plus large, pas
une loi. Le volume mesure la **taille du problème** ; il ne dit rien de sa
résolution.

Les tokens, eux, ne mesurent pas le code : ils mesurent le **processus** qui y
mène. Deux livrables identiques peuvent coûter 5 appels ou 30, et c'est le
nombre d'appels multiplié par le contexte renvoyé à chacun qui fait la facture —
pas la taille du résultat.

* **Le générateur fait 75 appels courts, sans conversation persistante
  commune.** Les phases du pipeline dépendent bien les unes des autres (design →
  contrats → remplissage), mais **aucun appel ne transporte l'historique des
  précédents** : c'est cette absence, et non l'indépendance des étapes, qui le
  distingue d'une boucle d'agent. Chaque appel renvoie exactement le contexte
  dont il a besoin (un prompt de 1 200 à 3 500 chars, plus ce que la phase
  exige). Total des entrées : 295 012 chars, **55 646 tokens sur 63 des 75
  appels**, soit ≈ 880 tokens d'entrée par appel. Il n'a **aucune ligne de
  cache** : il n'y a rien à mettre en cache, parce qu'il n'y a pas de
  conversation qui s'allonge.
* **Un run Claude est une boucle qui se relit.** Haiku : 63 tours, 1 549 492
  tokens de contexte relus, soit **24 595 par tour**. Sonnet : 79 tours,
  3 711 691 relus, **46 983 par tour**. Le nombre de tours n'est pas fixé par la
  spécification : `expenses` en demande 15 à Haiku et 30 à Sonnet, pour le même
  résultat en chars.

D'où le chiffre qui intrigue. Les **3,7 M** (et non 3,9 M : c'est la somme des
deux colonnes Claude, dont 1,5 M pour Haiku) ne sont pas du texte nouveau : c'est
le même contexte, renvoyé trente fois. La comparaison qui rend cela tangible :
**l'entrée totale du générateur pour les six projets, 55 646 tokens, représente
environ ce qu'une boucle Claude relit en deux tours.**

Deux conséquences pratiques, et c'est l'intérêt de la mesure :

1. Pour réduire la facture d'une boucle d'agent, le levier n'est pas d'écrire
   moins (la sortie est le plus petit poste) mais de **faire moins de tours** —
   ou de faire porter à chaque tour un contexte plus petit.
2. Un pipeline qui n'a pas de conversation à relire n'a pas cette ligne du tout.
   C'est structurellement la même raison qui met le générateur à 0 USD.

### One caveat, stated rather than smoothed

For a single run — `library_system` under Sonnet — the CLI's two accounting
blocks disagree: the top-level `usage` reports 477 output tokens while
`modelUsage` reports **38 257** for `claude-sonnet-5`, and it is the per-model
block that adds up to the billed `total_cost_usd` (1.1833 USD). The table above
uses the top-level block, like the rest of the report, so that row is a **floor,
not a total**. The per-model lines in
[`claude_baseline_report_sonnet.md`](claude_baseline_report_sonnet.md) carry the
figure that reconciles with the invoice. The discrepancy is the CLI's, and it is
recorded instead of averaged away.

A second, smaller detail worth knowing before reading the totals: a Sonnet run
also bills a small amount of **Haiku** (≈1 000–1 800 input tokens, 12–15 output
tokens per prompt) for the CLI's own side calls. Those tokens are inside the
Sonnet columns above, because the run really did spend them; the per-model
breakdown in the report separates them.

## Wall time and cost

| prompt | générateur (s) | Haiku (s) | Sonnet (s) |
|---|---|---|---|
| `hello_world` | 1.9 | 9.2 | 6.3 |
| `cli_tool` | 11.4 | 27.9 | 52.6 |
| `multi_module` | 138.1 | 52.0 | 104.8 |
| `library_system` | 220.6 | 119.1 | 387.3 |
| `inventory` | 241.1 | 181.3 | 148.7 |
| `expenses` | 402.6 | 94.0 | 408.8 |
| **total** | **1 015.8** | **483.5** | **1 108.5** |

The generator is now **2.1× slower than Haiku** and `1.1×` *faster* than Sonnet,
for the same deliverable — a 4B model on a laptop GPU inside the range of two
hosted frontier services, at 0 USD against 0.6769 and 3.3054. Per prompt the
ordering changes completely (`expenses`: 402.6 s here, 94.0 s for Haiku, 408.8 s
for Sonnet), so the total is the only number worth quoting.

## Verdicts (fresh runs, all three on 2026-09-17)

`PASS / FAIL(n)` = functional gate / conformity gate. For Claude, `raw` is the
untouched output and `shim` is the same output with a thin dispatch entry file
added when the prompt's own wording did not name one (see below); the generator
needs no shim.

| prompt | this generator | Claude Haiku 4.5 | Claude Sonnet 5 |
|---|---|---|---|
| `cli_tool` | PASS / PASS | PASS / PASS | PASS / **FAIL (1)** |
| `expenses` | PASS / PASS | **FAIL (3)** / **FAIL (6)** | **FAIL (3)** / PASS |
| `hello_world` | PASS / PASS | PASS / PASS | PASS / **FAIL (2)** |
| `inventory` | PASS / PASS | **FAIL (1)** / **FAIL (8)** | PASS / PASS |
| `library_system` | PASS / PASS | **FAIL (13)** / **FAIL (2)** | PASS / **FAIL (2)** |
| `multi_module` | PASS / PASS | **FAIL (1)** / **FAIL (1)** | **FAIL (5)** / PASS |
| **total** | **6/6 — 6/6** | **2/6 — 2/6** | **4/6 — 3/6** |

Both Claude columns are the **shim** gate for the four projects where Claude
shipped a package rather than a `cli.py` (`multi_module` for both models, plus
`cli_tool`, `hello_world` and `library_system` for Sonnet); `raw` is lower still,
because the gate suite invokes `python cli.py` by construction while no prompt
names an entry file. That asymmetry is introduced by the harness, and it is why
both readings are printed in every baseline report rather than only the
flattering one.

## What Claude actually got wrong

The failures below are copied from the fresh reports. Where the harness itself
introduces an asymmetry (the entry-file convention, the depth at which a click
group is looked for), it is called out separately — one such case turned out to
be a harness defect and was fixed rather than counted as Claude's. Two defect
classes dominate what is left: **state that does not persist**, and **a surface
that does not match the prompt** — both of which this project's pipeline exists
to make impossible.

**Haiku, `library_system`: 13 functional failures, all the same bug.**
Every command that touches the database dies with
`sqlite3.ProgrammingError: Cannot operate on a closed database.` The CLI answers
`--help` perfectly and cannot answer anything else. This is not an edge case: it
is the whole project.

**Haiku, `expenses`: the spec's own commands are missing or refuse the spec's own
values.** `expense category add --name food --description meals` →
`Error: No such command 'category'.` — the `category` group the prompt nests
under `expense` was never created, nor `budget list` (6 conformity failures).
And `expense add --amount 12.34 …` → `Error: Invalid value for '--amount':
'12.34' is not a valid integer.`: the amount is in cents, so the value the
specification writes is rejected by the tool that claims to implement it.

**Haiku, `inventory`: 8 conformity failures, one invented command.**
`category add/list/update/delete` are absent, and the CLI exposes
`category add-category`, which the prompt does not request. The gate counts both
directions — nothing missing, nothing extra — which is what makes this visible.

**Both models, `multi_module`: the entry point is a package, not a file.**
Haiku shipped `cli/main.py`, Sonnet `cli/commands.py`; neither created the
`cli.py` the gate invokes, so raw verdicts are *not applicable* and the shim
decides. Sonnet's version then fails 5 functional checks —
`add --title` is not an option it has, and `show/update/delete 1` all answer
`Error: Task with id 1 was not found`, i.e. the row it just added is not there.
Haiku's version hangs: `delete 1` never returns (90 s timeout, exit 124).

**Sonnet: two defects that are its own, and one that was ours.**
`hello_world` fails both conformity checks — no `main()`, no `__main__` guard:
it wrote a module where the prompt describes a script. `cli_tool` fails one —
"the header row is not read (no `DictReader`/`fieldnames`)": it parses CSV by
column index, so the header is data. Its `library_system` first appeared to fail
because "no click CLI was discovered"; that was the harness looking for a click
group one directory above where this project keeps it
(`library_system/cli/main.py`), and it was fixed (defect 5 below). Re-measured,
the same project fails conformity for a **real** reason — it exposes `author add`
and `author list`, which the specification never asks for: exactly the
over-generation Haiku is marked down for on the same prompt. `inventory` is
Sonnet's one clean project, on both gates.

**What neither model did wrong.** No stub markers in any of the twelve projects,
and every project compiled. The failure modes are design failure modes — closing
the database, forgetting a command group, mistaking cents for a unit, shipping a
package where a script was described — not syntax.

## What this says

* **What makes the comparison meaningful is the gate, not the generation.** The
  same six specifications, the same three implementations, graded by the same
  code: **6/6** for the generator, **2/6** for Haiku, **4/6 functional / 3/6
  conformity** for Sonnet. Without a grid that distinguishes a *working*
  implementation from a merely *plausible* one, all three would look alike —
  they all compile, and none leaves a stub marker. The generator ties neither
  model on polish (packaging, documentation, defensive style); it wins on the
  two questions the suite actually asks, at 4B parameters and zero API cost.
* **6/6 means exactly this: the generator passes the six specifications *and the
  checks the harness currently defines*.** Not "the generator implements the six
  applications correctly". The suite is a fixed, published, executable contract,
  and it is weaker than a human review: it grades a CLI surface and a handful of
  scenarios, not the behaviour of every command under every input. The honest
  formulation is the narrow one, and the same reserve applies to the Claude
  columns above: they are 2/6 and 4/6 *on this grid*.
* **A comparable volume of source, three budgets.** 104 487 / 105 542 / 110 215
  chars of Python for **0 / 0.6769 / 3.3054 USD**. What the local model buys is
  not speed — it is `2.1×` slower than Haiku — but that the number exists at
  all: it can be paid unconditionally, on hardware that is already owned.
* **A single pass is a measurement, not a verdict on a model.** The previous
  pass of this same harness, hours earlier, graded these models differently
  (Haiku failed fewer projects, Sonnet failed none). Nothing in the harness
  changed in between except its bookkeeping; the models did. Any claim of the
  form "Haiku cannot do X" is therefore worth exactly one run, which is why
  every run here is kept as an artifact that a later pass can re-render
  (`bench.py claude --reuse`) instead of being paraphrased.
* **The cache column is the story of agentic cost.** Sonnet's output tokens are
  within 4× of the generator's for the same deliverable; its *cached input* is
  3.7 M, re-read at **46 983 tokens per turn** over 79 turns (Haiku: 24 595 over
  63). Billing follows the re-read, not the writing: a pipeline that never
  re-reads a repository does not have that line item at all.
* **The specification is still the weakest link.** Some of the residue is a
  contract problem, not an implementation one: no prompt names its entry file,
  though the gates invoke `python cli.py` by construction, and one gate message
  is literally about whether a click group could be *discovered*. Where the
  prompt is ambiguous (cents vs units, program name vs first token), a fair
  grader must say so — and this document tries to, rather than banking the
  difference as a win.

## The instruments had to be fixed first — five times

A comparison is only as trustworthy as the two harnesses producing it, and this
pass found five defects in them. All five were silent, all five were repaired,
and each is recorded because the numbers above depend on the repair:

1. **A counter that counted twice.** `bench.py cost` wrapped
   `agentlib.llm.client._chat_completion` in every namespace that imported it —
   and did so again at every prompt, so the sixth prompt was counted six times.
   It announced itself the only way a bookkeeping bug can: the profile reported
   *more LLM seconds than wall-clock seconds* (`expenses`: 2 339.8 s of LLM
   inside 390.2 s of wall). The invariant that catches it is one line,
   `llm_seconds <= wall_seconds`, and the corrected counts land back on the
   counts this repository had already published (19 calls for `expenses`). One
   wrapper now, around the one true function.
2. **A phase table that lied about phases.** The caller chain stopped at the
   client's own frame, so every line was attributed to `client.py` rather than
   to `design.py` or `fill.py`. The comparison of design-phase cost against
   fill-phase cost in
   [`generation_cost_profile.md`](generation_cost_profile.md) only became
   meaningful after skipping that frame.
3. **A failed run that looked like a measurement.** A `claude -p` whose session
   has expired still exits with a JSON payload — `is_error`, an empty
   `modelUsage`, **zeros in every token field**. The harness would have copied an
   empty directory over a real baseline and published `0/0` as a measurement. It
   now aborts before writing anything, quoting the CLI's own error, and keeps
   the raw payload of every successful run so no metric has to be paid for
   twice.
4. **A label that did not select a model.** `--label sonnet` named a directory;
   it did not pass `--model`, so the first "Sonnet" run of this pass was a second
   Haiku run filed under `baseline/sonnet/` — visible only in a model id buried
   in the report. The label **is** the model selector now, and the model is
   verified twice: by a **preflight** before any work (one throwaway call, in a
   throwaway directory) and against each run's own payload afterwards. A model
   that does not exist stops the harness with the CLI's own message instead of
   filling a directory with someone else's output:

   ```text
   refusing to run: --model 'modele-inexistant' failed the preflight: There's an
   issue with the selected model (modele-inexistant). It may not exist or you may
   not have access to it.
   ```

5. **A conformity gate that could not see what it was grading.** The
   prompt→surface check asked the *executor's* discovery — which answers "how do
   I RUN this project", and for a package needs a module entry — instead of
   asking what commands the code *declares*. A click group one directory deeper
   than the executor's package scan (`library_system/cli/main.py`) was therefore
   reported as "no click CLI was discovered", while the same harness's own shim
   had just imported and dispatched that exact group one step earlier in the
   same run. The two questions are now separate (`declared_surface` for the
   verdict, `discover_facade` for execution), and the fix has a measurable
   signature: re-measured, Sonnet's `library_system` still fails conformity, but
   for a **real** reason (two unrequested commands) instead of a false one. A
   gate that reports a defect where there is none is worse than no gate: it
   teaches its reader to discount the ones that are real.

A sixth repair did not require re-running anything: the two harnesses were not
counting the same thing. The generator measured `**/*.py`; the Claude harness
measured every file it found, so Claude's side included `README.md` and
`requirements.txt`. The corrected figures are in the tables above — and the
honest note is that the error flattered Claude by about 18 % on
`multi_module`, the one project where it wrote documentation.

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
