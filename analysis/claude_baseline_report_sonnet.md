# Claude Code baseline — the same six specifications

Each prompt file was passed **verbatim** to `claude -p` (non-interactive
Claude Code), in an empty directory, with one imperative tail asking for
the full runnable implementation. The output is then subjected to the
SAME gates as the generator: `functional_failures` and
`conformity_failures` from `behavior_tests.named_prompt_suite`.

**No prompt names an entry-point file**, yet the gates invoke
`python cli.py ...` (and `hello.py` / `csv_to_json.py`) by construction.
Columns are therefore split: *raw* = gates against Claude's untouched
output; *shim* = gates after a thin dispatch `cli.py` (or runpy shim) was
added purely so the gates can run.

| prompt | wall (s) | turns | sortie | fichiers | entrée | raw fonctionnel | raw conforme | shim fonctionnel | shim conforme |
|---|---|---|---|---|---|---|---|---|---|
| `cli_tool` | 28.3 | ? | 0 | 1 | csv_to_json.py | PASS | PASS | PASS | PASS |
| `expenses` | 387.7 | ? | 0 | 13 | absent | n/a (entry file absent) | n/a (entry file absent) | PASS | PASS |
| `hello_world` | 12.2 | ? | 0 | 1 | hello.py | PASS | PASS | PASS | PASS |
| `inventory` | 172.1 | ? | 0 | 7 | cli.py | PASS | PASS | PASS | PASS |
| `library_system` | 273.3 | ? | 0 | 14 | absent | n/a (entry file absent) | n/a (entry file absent) | PASS | PASS |
| `multi_module` | 108.9 | ? | 0 | 10 | absent | n/a (entry file absent) | n/a (entry file absent) | PASS | PASS |

## `cli_tool`

- durée murale : **28.3 s**
- interne Claude : duration_ms=None, tours=None, coût=None USD, modèle=claude-sonnet (alias; exact id not captured)
- exit=0
- fichiers produits (1) : csv_to_json.py
- entrée attendue par les portes : `csv_to_json.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `expenses`

- durée murale : **387.7 s**
- interne Claude : duration_ms=None, tours=None, coût=None USD, modèle=claude-sonnet (alias; exact id not captured)
- exit=0
- fichiers produits (13) : expense_tracker/__init__.py, expense_tracker/__main__.py, expense_tracker/cli.py, expense_tracker/db.py, expense_tracker/exceptions.py, expense_tracker/models.py, expense_tracker/repositories/__init__.py, expense_tracker/repositories/budget_repository.py, expense_tracker/repositories/category_repository.py, expense_tracker/repositories/expense_repository.py, expense_tracker/services/__init__.py, expense_tracker/services/expense_service.py, expense_tracker/utils.py
- entrée attendue par les portes : `cli.py` — **absente**
- shim : dispatch expense_tracker.cli.cli
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `hello_world`

- durée murale : **12.2 s**
- interne Claude : duration_ms=None, tours=None, coût=None USD, modèle=claude-sonnet (alias; exact id not captured)
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

- durée murale : **172.1 s**
- interne Claude : duration_ms=None, tours=None, coût=None USD, modèle=claude-sonnet (alias; exact id not captured)
- exit=0
- fichiers produits (7) : category_repository.py, cli.py, db.py, exceptions.py, inventory_service.py, models.py, product_repository.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `library_system`

- durée murale : **273.3 s**
- interne Claude : duration_ms=None, tours=None, coût=None USD, modèle=claude-sonnet (alias; exact id not captured)
- exit=0
- fichiers produits (14) : library_system/__init__.py, library_system/cli.py, library_system/database.py, library_system/enums.py, library_system/exceptions.py, library_system/models.py, library_system/repositories/__init__.py, library_system/repositories/author_repository.py, library_system/repositories/book_repository.py, library_system/repositories/loan_repository.py, library_system/repositories/member_repository.py, library_system/services/__init__.py, library_system/services/library_service.py, main.py
- entrée attendue par les portes : `cli.py` — **absente**
- shim : dispatch library_system.cli.library
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `multi_module`

- durée murale : **108.9 s**
- interne Claude : duration_ms=None, tours=None, coût=None USD, modèle=claude-sonnet (alias; exact id not captured)
- exit=0
- fichiers produits (10) : main.py, task_manager/__init__.py, task_manager/cli/__init__.py, task_manager/cli/main.py, task_manager/models/__init__.py, task_manager/models/task.py, task_manager/repository/__init__.py, task_manager/repository/task_repository.py, task_manager/services/__init__.py, task_manager/services/task_service.py
- entrée attendue par les portes : `cli.py` — **absente**
- shim : dispatch task_manager.cli.main.cli
- marqueurs de stub (proxy) : aucun
- compile : OK
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS
