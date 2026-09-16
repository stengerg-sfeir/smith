# Claude Code baseline — the same six specifications

Each prompt file was passed **verbatim** to `claude -p` (non-interactive
Claude Code), in an empty directory, with one imperative tail asking for
the full runnable implementation. The output is then subjected to the
SAME gates as the generator: `functional_failures` and
`conformity_failures` from `agentlib.bench.named_prompt_suite` (run by
`python3 bench.py claude`).

**No prompt names an entry-point file**, yet the gates invoke
`python cli.py ...` (and `hello.py` / `csv_to_json.py`) by construction.
Columns are therefore split: *raw* = gates against Claude's untouched
output; *shim* = gates after a thin dispatch `cli.py` (or runpy shim) was
added purely so the gates can run.

| prompt | wall (s) | turns | sortie | fichiers | entrée | raw fonctionnel | raw conforme | shim fonctionnel | shim conforme |
|---|---|---|---|---|---|---|---|---|---|
| `cli_tool` | 38.9 | 9 | 0 | 2 | csv_to_json.py | PASS | PASS | PASS | PASS |
| `expenses` | 269.0 | 20 | 0 | 8 | cli.py | FAIL (4) | FAIL (15) | FAIL (4) | FAIL (15) |
| `hello_world` | 11.2 | 3 | 0 | 1 | hello.py | PASS | PASS | PASS | PASS |
| `inventory` | 95.3 | 14 | 0 | 7 | cli.py | PASS | PASS | PASS | PASS |
| `library_system` | 81.8 | 16 | 0 | 7 | cli.py | PASS | FAIL (2) | PASS | FAIL (2) |
| `multi_module` | 200.3 | 29 | 0 | 7 | cli.py | FAIL (1) | PASS | FAIL (1) | PASS |

## `cli_tool`

- durée murale : **38.9 s**
- interne Claude : duration_ms=37113, tours=9, coût=0.0724357 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- fichiers produits (2) : csv_to_json.py, test_csv_to_json.py
- entrée attendue par les portes : `csv_to_json.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `expenses`

- durée murale : **269.0 s**
- interne Claude : duration_ms=267542, tours=20, coût=0.31652940000000007 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- fichiers produits (8) : cli.py, database.py, exceptions.py, main.py, models.py, repositories.py, services.py, test_system.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : FAIL (4)
    - budget delete --category-id 1 --month 1 -> exit=124 (no traceback, but not 0/1/2)
    - expense category add --name food --description meals -> exit=2 (want 0) ["Error: No such command 'category'."]
    - expense add --amount 12.34 --description lunch --category 1 -> exit=1 (want 0) ["✗ Category '1' not found"]
    - expense list -> output does not contain 'lunch'
- **raw** conformité : FAIL (15)
    - prompt requires command 'expense category add' but the CLI does not expose it
    - prompt requires command 'expense category list' but the CLI does not expose it
    - prompt requires command 'expense category update' but the CLI does not expose it
    - prompt requires command 'expense category delete' but the CLI does not expose it
    - prompt requires command 'expense report monthly' but the CLI does not expose it
- **avec shim** fonctionnel : FAIL (4)
    - budget delete --category-id 1 --month 1 -> exit=124 (no traceback, but not 0/1/2)
    - expense category add --name food --description meals -> exit=2 (want 0) ["Error: No such command 'category'."]
    - expense add --amount 12.34 --description lunch --category 1 -> exit=1 (want 0) ["✗ Category '1' not found"]
    - expense list -> output does not contain 'lunch'
- **avec shim** conformité : FAIL (15)
    - prompt requires command 'expense category add' but the CLI does not expose it
    - prompt requires command 'expense category list' but the CLI does not expose it
    - prompt requires command 'expense category update' but the CLI does not expose it
    - prompt requires command 'expense category delete' but the CLI does not expose it
    - prompt requires command 'expense report monthly' but the CLI does not expose it

## `hello_world`

- durée murale : **11.2 s**
- interne Claude : duration_ms=8621, tours=3, coût=0.0137311 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- fichiers produits (1) : hello.py
- entrée attendue par les portes : `hello.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `inventory`

- durée murale : **95.3 s**
- interne Claude : duration_ms=94304, tours=14, coût=0.1826784 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- fichiers produits (7) : cli.py, database.py, exceptions.py, main.py, models.py, repositories.py, service.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `library_system`

- durée murale : **81.8 s**
- interne Claude : duration_ms=80735, tours=16, coût=0.1713999 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- fichiers produits (7) : __init__.py, cli.py, database.py, main.py, models.py, repositories.py, service.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : PASS
- **raw** conformité : FAIL (2)
    - CLI exposes command 'author add' that the prompt does not request
    - CLI exposes command 'author list' that the prompt does not request
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : FAIL (2)
    - CLI exposes command 'author add' that the prompt does not request
    - CLI exposes command 'author list' that the prompt does not request

## `multi_module`

- durée murale : **200.3 s**
- interne Claude : duration_ms=199368, tours=29, coût=0.2578888 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- fichiers produits (7) : cli.py, database.py, example_usage.py, main.py, models.py, repository.py, service.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : FAIL (1)
    - delete 1 -> exit=124 (want 0) ['TIMEOUT']
- **raw** conformité : PASS
- **avec shim** fonctionnel : FAIL (1)
    - delete 1 -> exit=124 (want 0) ['TIMEOUT']
- **avec shim** conformité : PASS
