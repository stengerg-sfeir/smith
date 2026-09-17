# Claude Code baseline — the same six specifications

Each prompt file was passed **verbatim** to `claude -p` (non-interactive
Claude Code), in an empty directory, with one imperative tail asking for
the full runnable implementation. The output is then subjected to the
SAME gates as the generator: `functional_failures` and
`conformity_failures` from `agentlib.bench.named_prompt_suite`.

**No prompt names an entry-point file**, yet the gates invoke
`python cli.py ...` (and `hello.py` / `csv_to_json.py`) by construction.
Columns are therefore split: *raw* = gates against Claude's untouched
output; *shim* = gates after a thin dispatch `cli.py` (or runpy shim) was
added purely so the gates can run.

| prompt | wall (s) | turns | sortie | fichiers | entrée | raw fonctionnel | raw conforme | shim fonctionnel | shim conforme |
|---|---|---|---|---|---|---|---|---|---|
| `cli_tool` | 52.6 | 11 | 0 | 1 | absent | n/a (entry file absent) | n/a (entry file absent) | PASS | FAIL (1) |
| `expenses` | 408.8 | 30 | 0 | 9 | cli.py | FAIL (3) | PASS | FAIL (3) | PASS |
| `hello_world` | 6.3 | 2 | 0 | 1 | absent | n/a (entry file absent) | n/a (entry file absent) | PASS | FAIL (2) |
| `inventory` | 148.7 | 15 | 0 | 8 | cli.py | PASS | PASS | PASS | PASS |
| `library_system` | 387.3 | 1 | 0 | 16 | absent | n/a (entry file absent) | n/a (entry file absent) | PASS | FAIL (2) |
| `multi_module` | 104.8 | 20 | 0 | 6 | absent | n/a (entry file absent) | n/a (entry file absent) | FAIL (5) | PASS |

## Consommation

`prompt (chars)` : ce qui a été envoyé (fichier de prompt + consigne
finale). `source (chars)` : le projet écrit, relu sur le disque après le
run, **en ne comptant que les `.py`** — c'est l'unité du profil du
générateur, donc la seule comparable ; le projet complet (README,
`requirements.txt`) est donné dans le détail par prompt. Les colonnes
`tokens` viennent de la comptabilité du CLI lui-même
(`usage` du payload) : `entrée` EXCLUT le cache, et `cache lu` est le
contexte relu à chaque tour — c'est là que passe le trafic d'une boucle
d'agent, donc la colonne est conservée au lieu d'être fondue dans le
total.

| prompt | prompt (chars) | source (chars) | fichiers | tokens entrée | tokens sortie | cache lu | cache écrit | tokens total | coût (USD) |
|---|---|---|---|---|---|---|---|---|---|
| `cli_tool` | 647 | 3086 | 1 | 20 | 3754 | 308018 | 15293 | 327085 | 0.1614 |
| `expenses` | 3505 | 42206 | 9 | 60 | 48703 | 1966309 | 69378 | 2084450 | 1.1598 |
| `hello_world` | 416 | 87 | 1 | 4 | 249 | 48790 | 11424 | 60467 | 0.0590 |
| `inventory` | 2517 | 21537 | 8 | 30 | 18603 | 632054 | 31576 | 682263 | 0.4404 |
| `library_system` | 2171 | 32121 | 16 | 2 | 477 | 68996 | 2534 | 72009 | 1.1833 |
| `multi_module` | 763 | 11178 | 6 | 40 | 7642 | 687524 | 21583 | 716789 | 0.3015 |
| **total** | 10019 | 110215 | 41 | 156 | 79428 | 3711691 | 151788 | 3943063 | 3.3054 |

## `cli_tool`

- durée murale : **52.6 s**
- interne Claude : duration_ms=51797, tours=11, coût=0.1614 USD, modèle=claude-haiku-4-5-20251001, claude-sonnet-5
- exit=0
- consommation Claude : 647 chars de prompt -> 3086 chars de source Python en 1 fichiers (projet complet : 2 fichiers, 3117 chars)
- tokens Claude : entrée=20, sortie=3754, cache lu=308018, cache écrit=15293, total=327085
- fichiers produits (1) : csv2json.py
- entrée attendue par les portes : `csv_to_json.py` — **absente**
- shim : runpy -> csv2json.py
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1025, sortie=13, cache lu=0, cache écrit=0, coût=0.0011 USD
- tokens par modèle (`claude-sonnet-5`) : entrée=20, sortie=3754, cache lu=308018, cache écrit=15293, coût=0.1604 USD
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : FAIL (1)
    - cli_tool: the header row is not read (no DictReader/fieldnames)

## `expenses`

- durée murale : **408.8 s**
- interne Claude : duration_ms=408071, tours=30, coût=1.1598 USD, modèle=claude-haiku-4-5-20251001, claude-sonnet-5
- exit=0
- consommation Claude : 3505 chars de prompt -> 42206 chars de source Python en 9 fichiers (projet complet : 10 fichiers, 42217 chars)
- tokens Claude : entrée=60, sortie=48703, cache lu=1966309, cache écrit=69378, total=2084450
- fichiers produits (9) : budget_repository.py, category_repository.py, cli.py, database.py, exceptions.py, expense_repository.py, expense_service.py, models.py, money.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1801, sortie=15, cache lu=0, cache écrit=0, coût=0.0019 USD
- tokens par modèle (`claude-sonnet-5`) : entrée=60, sortie=48703, cache lu=1966309, cache écrit=69378, coût=1.1579 USD
- **raw** fonctionnel : FAIL (3)
    - expense category add --name x --description x --budget x --icon x -> traceback: decimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]
    - expense add --amount 12.34 --description lunch --category 1 -> exit=1 (want 0) ["Error: Category '1' not found"]
    - expense list -> output does not contain 'lunch'
- **raw** conformité : PASS
- **avec shim** fonctionnel : FAIL (3)
    - expense category add --name x --description x --budget x --icon x -> traceback: decimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]
    - expense add --amount 12.34 --description lunch --category 1 -> exit=1 (want 0) ["Error: Category '1' not found"]
    - expense list -> output does not contain 'lunch'
- **avec shim** conformité : PASS

## `hello_world`

- durée murale : **6.3 s**
- interne Claude : duration_ms=5445, tours=2, coût=0.0590 USD, modèle=claude-haiku-4-5-20251001, claude-sonnet-5
- exit=0
- consommation Claude : 416 chars de prompt -> 87 chars de source Python en 1 fichiers (projet complet : 1 fichiers, 87 chars)
- tokens Claude : entrée=4, sortie=249, cache lu=48790, cache écrit=11424, total=60467
- fichiers produits (1) : hello_world.py
- entrée attendue par les portes : `hello.py` — **absente**
- shim : runpy -> hello_world.py
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=982, sortie=12, cache lu=0, cache écrit=0, coût=0.0010 USD
- tokens par modèle (`claude-sonnet-5`) : entrée=4, sortie=249, cache lu=48790, cache écrit=11424, coût=0.0580 USD
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : FAIL (2)
    - hello_world: the __main__ guard is absent
    - hello_world: no main() function

## `inventory`

- durée murale : **148.7 s**
- interne Claude : duration_ms=147975, tours=15, coût=0.4404 USD, modèle=claude-haiku-4-5-20251001, claude-sonnet-5
- exit=0
- consommation Claude : 2517 chars de prompt -> 21537 chars de source Python en 8 fichiers (projet complet : 9 fichiers, 21548 chars)
- tokens Claude : entrée=30, sortie=18603, cache lu=632054, cache écrit=31576, total=682263
- fichiers produits (8) : category_repository.py, cli.py, db.py, exceptions.py, inventory_service.py, mapping.py, models.py, product_repository.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1538, sortie=14, cache lu=0, cache écrit=0, coût=0.0016 USD
- tokens par modèle (`claude-sonnet-5`) : entrée=30, sortie=18603, cache lu=632054, cache écrit=31576, coût=0.4388 USD
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `library_system`

- durée murale : **387.3 s**
- interne Claude : duration_ms=6464, tours=1, coût=1.1833 USD, modèle=claude-haiku-4-5-20251001, claude-sonnet-5
- exit=0
- consommation Claude : 2171 chars de prompt -> 32121 chars de source Python en 16 fichiers (projet complet : 18 fichiers, 32519 chars)
- tokens Claude : entrée=2, sortie=477, cache lu=68996, cache écrit=2534, total=72009
- fichiers produits (16) : library_system/__init__.py, library_system/cli/__init__.py, library_system/cli/main.py, library_system/models/__init__.py, library_system/models/author.py, library_system/models/book.py, library_system/models/loan.py, library_system/models/member.py, library_system/repositories/__init__.py, library_system/repositories/author_repository.py, library_system/repositories/book_repository.py, library_system/repositories/database.py, library_system/repositories/loan_repository.py, library_system/repositories/member_repository.py, library_system/services/__init__.py, library_system/services/library_service.py
- entrée attendue par les portes : `cli.py` — **absente**
- shim : dispatch library_system.cli.main.cli
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1465, sortie=12, cache lu=0, cache écrit=0, coût=0.0015 USD
- tokens par modèle (`claude-sonnet-5`) : entrée=114, sortie=38257, cache lu=2445011, cache écrit=92454, coût=1.1817 USD
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : FAIL (2)
    - CLI exposes command 'author add' that the prompt does not request
    - CLI exposes command 'author list' that the prompt does not request

## `multi_module`

- durée murale : **104.8 s**
- interne Claude : duration_ms=103970, tours=20, coût=0.3015 USD, modèle=claude-haiku-4-5-20251001, claude-sonnet-5
- exit=0
- consommation Claude : 763 chars de prompt -> 11178 chars de source Python en 6 fichiers (projet complet : 8 fichiers, 11573 chars)
- tokens Claude : entrée=40, sortie=7642, cache lu=687524, cache écrit=21583, total=716789
- fichiers produits (6) : main.py, task_manager/__init__.py, task_manager/cli.py, task_manager/models.py, task_manager/repository.py, task_manager/services.py
- entrée attendue par les portes : `cli.py` — **absente**
- shim : dispatch task_manager.cli.cli
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1058, sortie=14, cache lu=0, cache écrit=0, coût=0.0011 USD
- tokens par modèle (`claude-sonnet-5`) : entrée=40, sortie=7642, cache lu=687524, cache écrit=21583, coût=0.3003 USD
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : FAIL (5)
    - add --title write tests --description d -> exit=2 (want 0) ["Error: No such option '--title'."]
    - list -> output lacks 'write tests'
    - show 1 -> exit=1 (want 0) ['Error: Task with id 1 was not found']
    - update 1 --status done -> exit=1 (want 0) ['Error: Task with id 1 was not found']
    - delete 1 -> exit=1 (want 0) ['Error: Task with id 1 was not found']
- **avec shim** conformité : PASS
