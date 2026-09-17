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
| `cli_tool` | 27.9 | 8 | 0 | 1 | csv_to_json.py | PASS | PASS | PASS | PASS |
| `expenses` | 94.0 | 15 | 0 | 8 | cli.py | FAIL (3) | FAIL (6) | FAIL (3) | FAIL (6) |
| `hello_world` | 9.2 | 3 | 0 | 1 | hello.py | PASS | PASS | PASS | PASS |
| `inventory` | 181.3 | 11 | 0 | 7 | cli.py | FAIL (1) | FAIL (8) | FAIL (1) | FAIL (8) |
| `library_system` | 119.1 | 12 | 0 | 7 | cli.py | FAIL (13) | FAIL (2) | FAIL (13) | FAIL (2) |
| `multi_module` | 52.0 | 14 | 0 | 9 | absent | n/a (entry file absent) | n/a (entry file absent) | FAIL (1) | FAIL (1) |

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
| `cli_tool` | 647 | 3950 | 1 | 66 | 3383 | 180303 | 11183 | 194935 | 0.0585 |
| `expenses` | 3505 | 40003 | 8 | 122 | 15929 | 462792 | 25238 | 504081 | 0.1784 |
| `hello_world` | 416 | 111 | 1 | 26 | 595 | 61328 | 4423 | 66372 | 0.0190 |
| `inventory` | 2517 | 19648 | 7 | 90 | 20612 | 390256 | 29211 | 440169 | 0.2022 |
| `library_system` | 2171 | 31752 | 7 | 98 | 13733 | 338227 | 22412 | 374470 | 0.1489 |
| `multi_module` | 763 | 10078 | 9 | 42 | 5795 | 116586 | 14043 | 136466 | 0.0699 |
| **total** | 10019 | 105542 | 33 | 444 | 60047 | 1549492 | 106510 | 1716493 | 0.6769 |

## `cli_tool`

- durée murale : **27.9 s**
- interne Claude : duration_ms=26757, tours=8, coût=0.0585 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- consommation Claude : 647 chars de prompt -> 3950 chars de source Python en 1 fichiers (projet complet : 3 fichiers, 5101 chars)
- tokens Claude : entrée=66, sortie=3383, cache lu=180303, cache écrit=11183, total=194935
- fichiers produits (1) : csv_to_json.py
- entrée attendue par les portes : `csv_to_json.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1091, sortie=3396, cache lu=180303, cache écrit=11183, coût=0.0585 USD
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `expenses`

- durée murale : **94.0 s**
- interne Claude : duration_ms=92905, tours=15, coût=0.1784 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- consommation Claude : 3505 chars de prompt -> 40003 chars de source Python en 8 fichiers (projet complet : 10 fichiers, 47275 chars)
- tokens Claude : entrée=122, sortie=15929, cache lu=462792, cache écrit=25238, total=504081
- fichiers produits (8) : __init__.py, cli.py, database.py, exceptions.py, main.py, models.py, repository.py, service.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1923, sortie=15944, cache lu=462792, cache écrit=25238, coût=0.1784 USD
- **raw** fonctionnel : FAIL (3)
    - expense category add --name food --description meals -> exit=2 (want 0) ["Error: No such command 'category'."]
    - expense add --amount 12.34 --description lunch --category 1 -> exit=2 (want 0) ["Error: Invalid value for '--amount': '12.34' is not a valid integer."]
    - expense list -> output does not contain 'lunch'
- **raw** conformité : FAIL (6)
    - prompt requires command 'expense category add' but the CLI does not expose it
    - prompt requires command 'expense category list' but the CLI does not expose it
    - prompt requires command 'expense category update' but the CLI does not expose it
    - prompt requires command 'expense category delete' but the CLI does not expose it
    - prompt requires command 'budget list' but the CLI does not expose it
- **avec shim** fonctionnel : FAIL (3)
    - expense category add --name food --description meals -> exit=2 (want 0) ["Error: No such command 'category'."]
    - expense add --amount 12.34 --description lunch --category 1 -> exit=2 (want 0) ["Error: Invalid value for '--amount': '12.34' is not a valid integer."]
    - expense list -> output does not contain 'lunch'
- **avec shim** conformité : FAIL (6)
    - prompt requires command 'expense category add' but the CLI does not expose it
    - prompt requires command 'expense category list' but the CLI does not expose it
    - prompt requires command 'expense category update' but the CLI does not expose it
    - prompt requires command 'expense category delete' but the CLI does not expose it
    - prompt requires command 'budget list' but the CLI does not expose it

## `hello_world`

- durée murale : **9.2 s**
- interne Claude : duration_ms=8326, tours=3, coût=0.0190 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- consommation Claude : 416 chars de prompt -> 111 chars de source Python en 1 fichiers (projet complet : 1 fichiers, 111 chars)
- tokens Claude : entrée=26, sortie=595, cache lu=61328, cache écrit=4423, total=66372
- fichiers produits (1) : hello.py
- entrée attendue par les portes : `hello.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1008, sortie=607, cache lu=61328, cache écrit=4423, coût=0.0190 USD
- **raw** fonctionnel : PASS
- **raw** conformité : PASS
- **avec shim** fonctionnel : PASS
- **avec shim** conformité : PASS

## `inventory`

- durée murale : **181.3 s**
- interne Claude : duration_ms=180428, tours=11, coût=0.2022 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- consommation Claude : 2517 chars de prompt -> 19648 chars de source Python en 7 fichiers (projet complet : 9 fichiers, 19908 chars)
- tokens Claude : entrée=90, sortie=20612, cache lu=390256, cache écrit=29211, total=440169
- fichiers produits (7) : cli.py, database.py, exceptions.py, inventory_service.py, main.py, models.py, repositories.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1628, sortie=20627, cache lu=390256, cache écrit=29211, coût=0.2022 USD
- **raw** fonctionnel : FAIL (1)
    - product list -> output does not contain 'hammer'
- **raw** conformité : FAIL (8)
    - prompt requires command 'category add' but the CLI does not expose it
    - prompt requires command 'category list' but the CLI does not expose it
    - prompt requires command 'category update' but the CLI does not expose it
    - prompt requires command 'category delete' but the CLI does not expose it
    - CLI exposes command 'category add-category' that the prompt does not request
- **avec shim** fonctionnel : FAIL (1)
    - product list -> output does not contain 'hammer'
- **avec shim** conformité : FAIL (8)
    - prompt requires command 'category add' but the CLI does not expose it
    - prompt requires command 'category list' but the CLI does not expose it
    - prompt requires command 'category update' but the CLI does not expose it
    - prompt requires command 'category delete' but the CLI does not expose it
    - CLI exposes command 'category add-category' that the prompt does not request

## `library_system`

- durée murale : **119.1 s**
- interne Claude : duration_ms=118325, tours=12, coût=0.1489 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- consommation Claude : 2171 chars de prompt -> 31752 chars de source Python en 7 fichiers (projet complet : 9 fichiers, 37793 chars)
- tokens Claude : entrée=98, sortie=13733, cache lu=338227, cache écrit=22412, total=374470
- fichiers produits (7) : __main__.py, cli.py, database.py, example.py, models.py, repositories.py, service.py
- entrée attendue par les portes : `cli.py` — présente
- shim : none needed (already present)
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1563, sortie=13748, cache lu=338227, cache écrit=22412, coût=0.1489 USD
- **raw** fonctionnel : FAIL (13)
    - library book list <no option> -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library book search --query x -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library member add --name x --email x -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library member list <no option> -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library member list --active-only -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
- **raw** conformité : FAIL (2)
    - CLI exposes command 'author add' that the prompt does not request
    - CLI exposes command 'author list' that the prompt does not request
- **avec shim** fonctionnel : FAIL (13)
    - library book list <no option> -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library book search --query x -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library member add --name x --email x -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library member list <no option> -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
    - library member list --active-only -> traceback: sqlite3.ProgrammingError: Cannot operate on a closed database.
- **avec shim** conformité : FAIL (2)
    - CLI exposes command 'author add' that the prompt does not request
    - CLI exposes command 'author list' that the prompt does not request

## `multi_module`

- durée murale : **52.0 s**
- interne Claude : duration_ms=51057, tours=14, coût=0.0699 USD, modèle=claude-haiku-4-5-20251001
- exit=0
- consommation Claude : 763 chars de prompt -> 10078 chars de source Python en 9 fichiers (projet complet : 11 fichiers, 13052 chars)
- tokens Claude : entrée=42, sortie=5795, cache lu=116586, cache écrit=14043, total=136466
- fichiers produits (9) : cli/__init__.py, cli/main.py, main.py, models/__init__.py, models/task.py, repository/__init__.py, repository/task_repository.py, service/__init__.py, service/task_service.py
- entrée attendue par les portes : `cli.py` — **absente**
- shim : dispatch cli.main.cli
- marqueurs de stub (proxy) : aucun
- compile : OK
- tokens par modèle (`claude-haiku-4-5-20251001`) : entrée=1100, sortie=5806, cache lu=116586, cache écrit=14043, coût=0.0699 USD
- **raw** : non applicable (fichier d'entrée absent)
- **avec shim** fonctionnel : FAIL (1)
    - delete 1 -> exit=124 (want 0) ['TIMEOUT']
- **avec shim** conformité : FAIL (1)
    - task_repository.py.read_all merely extends read() with a scalar qualifier
