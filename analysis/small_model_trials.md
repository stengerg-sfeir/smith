# Essai de modèles locaux plus petits que la référence 4B

Trois modèles ont été passés au générateur **sans aucune correction de celui-ci**
(consigne explicite). Le seul levier utilisé est la variable d'environnement
`LLM_BASE_URL`, documentée dans `agentlib/config.py` :

```python
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
```

Un second serveur llama.cpp a donc été lancé sur le **port 8001**, avec
strictement les mêmes drapeaux que `server.sh` (seuls `-m` et `--port`
changent), et le générateur y a été pointé par l'environnement. `server.sh` et
le modèle 4B n'ont pas été modifiés.

## 0. Résumé

| modèle | `expenses` | `library_system` | objectif « code fonctionnel » | objectif « conformité prompt » |
|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507** (référence) | **succès**, 10 fichiers, 0 échec | **succès**, 0 échec | atteint | atteint |
| **Qwen3-1.7B-Q4_K_M** (serving par défaut) | non mesuré | échec : 0 fichier | **non atteint** | non évaluable |
| **Qwen3-1.7B-Q4_K_M** (thinking désactivé) | non mesuré | échec : 0 fichier | **non atteint** | partiellement atteint au design |
| **qwen2.5-coder-1.5b-instruct** | échec : 0 fichier | échec : 0 fichier (crash) | **non atteint** | bon au design, non évaluable en sortie |
| **qwen2.5-coder-3b-instruct** | **succès**, 12 fichiers ; conformité 0 échec, 4 échecs fonctionnels | échec : 0 fichier | **partiel** (12/16 chemins passent) | **atteint** sur `expenses` (0 échec) |

**Conclusion courte** : les deux plus petits modèles (1.7B, 1.5B) ne produisent
rien d'exploitable ; le **3B produit un projet conforme et exécutable sur
`expenses`** (conformité 0 échec), avec 4 échecs fonctionnels seulement. La
cause des échecs n'est pas le montage — le contrôle 4B réussit sur les deux
prompts dans exactement la même configuration — mais des **décisions de
convention** du modèle, plus **trois manques du générateur** que ces modèles ont
rendus visibles.

## 1. Contrôle de référence : le montage est bon

Avant toute conclusion, la même chaîne a été exécutée avec le modèle de
référence, sur le port 8000, **sans aucune surcharge d'environnement** :

```
$ python3 agent.py --prompt expenses
  ...
  Project written to generated/expenses/
Done -- 1 succeeded, 0 failed out of 1 prompt(s).

$ python3 agent.py --prompt library_system
  ...
  Project written to generated/library_system/
Done -- 1 succeeded, 0 failed out of 1 prompt(s).
```

puis les deux objectifs :

```
=== expenses ===
  gen=418.4s markers=0 compile=0 functional=0 conforme=0 facade=pass
=== library_system ===
  gen=223.3s markers=0 compile=0 functional=0 conforme=0 facade=pass
[named-prompts] 6/6 prompt(s) clean
```

`markers=0` = aucun marqueur de dégradation silencieuse ; `functional=0` et
`conforme=0` = aucun échec sur les deux axes. **Le générateur, le runner, le
port et l'environnement sont donc hors de cause** : tout échec décrit ci-dessous
est imputable à ce que le modèle a produit.

## 2. Qwen3-1.7B-Q4_K_M

Ce fichier (`Qwen_Qwen3-1.7B-Q4_K_M.gguf`) n'est **pas** un modèle « instruct
non-thinking » : son gabarit de conversation active le raisonnement. Le serveur
l'annonce lui-même au chargement :

```
init: chat template, thinking = 1
```

### 2.1 Serving par défaut (thinking activé) — échec total

Mesure directe contre le serveur, sans passer par le pipeline :

```
$ curl .../chat/completions -d '{"messages":[{"role":"user","content":"Reply with the single word: ok"}], ...}'
{"choices":[{"finish_reason":"length",
  "message":{"role":"assistant",
             "content":"",
             "reasoning_content":"Okay, the user wants me to reply with the single word \"ok\". Let me think about why ..."}}]}
```

`content` est **vide** : tout le raisonnement part dans `reasoning_content`,
champ que `agentlib/llm/client.py` ne lit pas (`choice["message"]["content"]`).

Avec un schéma JSON imposé, le raisonnement consomme le budget de tokens et le
JSON est coupé en plein milieu :

```
$ curl .../chat/completions -d '{..., "response_format":{"type":"json_object","schema":{...}}}'
{"choices":[{"finish_reason":"length","message":{"content":"{\"x\": \"hello","reasoning_content":"..."}}]}
```

Résultat dans le pipeline (log complet conservé) :

```
[warn] completion hit max_tokens=2048 — output truncated   (x4)
JSON parse failed (attempt 1): ''
JSON parse failed (attempt 2): ''
Manifest failed; generation aborted (no fallback)
RuntimeError: manifest-first pipeline failed for this prompt
Done -- 0 succeeded, 1 failed out of 1 prompt(s).
```

**0 fichier.** La toute première étape (le manifeste d'architecture) ne peut pas
aboutir.

### 2.2 Thinking désactivé au serving — échec plus loin

Comme le drapeau est un réglage *serveur* et non une modification du
générateur, l'essai a été refait avec le raisonnement coupé
(`--chat-template-kwargs '{"enable_thinking": false}'`, que ce build signale
comme déprécié au profit de `--reasoning off`). Vérification préalable :

```
plain  -> {"content":"ok","finish_reason":"stop"}            (2 tokens)
schéma -> {"content":"{\n  \"x\": \"hello\"\n}","finish_reason":"stop"} (14 tokens)
```

Cette fois le pipeline va jusqu'au design des *repositories*, puis échoue — le
modèle y traite les options CLI comme des **paramètres de méthode** :

```
[design] book_repository.py invalid: book_repository.py.list_book: bad param '--author';
         book_repository.py.list_book: bad param '--available-only';
         book_repository.py.search_books: bad param '--query' (attempt 1)
[design] author_repository.py invalid: author_repository.py.list_authors: bad param '--active-only';
         author_repository.py.search_authors: bad param '--query' (attempt 1)
[design] author_repository.py invalid: author_repository.py.search_authors: bad param '--query' (attempt 2)
Done -- 0 succeeded, 1 failed out of 1 prompt(s).
```

**0 fichier** à nouveau.

### 2.3 Décisions de convention du 1.7B

| # | ce que le modèle fait | ce que le pipeline attend | conséquence |
|---|---|---|---|
| C1 | produit son texte dans `reasoning_content` | `message.content` | tout est vide → manifeste impossible |
| C2 | met les options CLI en paramètres de méthode (`list_book(author)` pour `--author`) | les options sont portées par la **surface CLI**, pas par les méthodes | `bad param '--author'`, design rejeté |
| C3 | invente une recherche d'auteur (`search_authors`) et recopie des options d'une entité sur une autre (`list_authors` avec `--active-only`, qui est l'option des *membres*) | chaque entité porte les capacités de sa puce du prompt | design rejeté |
| C4 | duplique les champs de l'entité dans la classe `*Repository` (`BookRepository(id, title, isbn, ...)`) | une classe `*Repository` est un magasin, pas un second modèle | accepté par le générateur, mais sémantiquement faux |
| C5 | `list_book` au singulier | pas de contrainte du prompt sur ce point | sans effet |

Aucune de ces divergences n'est « acceptable » au sens des deux objectifs : C1
et C2 interdisent toute sortie, C3 introduit des commandes que le prompt ne
demande pas (violation de conformité si le run allait au bout), C4 est une
erreur de modèle sans impact fonctionnel immédiat.

## 3. qwen2.5-coder-1.5b-instruct-q4_k_m

Ce modèle est bien non-thinking : le serveur annonce `thinking = 0`, et une
requête simple renvoie directement `content`, sans raisonnement :

```
plain  -> {"content":"ok","finish_reason":"stop"}
schéma -> {"content":"{\n  \"x\": \"hello\"\n}","finish_reason":"stop"}
```

Le problème C1 du 1.7B disparaît donc entièrement. Les deux prompts ont été
régénérés.

### 3.1 `expenses` — la surface CLI est parfaite, la suite non

Le prompt énumère **14** commandes. Le design du modèle en câble **exactement
14**, avec les bons chemins et la bonne imbrication :

```
[design] cli.py reconcile: 14 command(s) from LLM design
[design] cli.py wired: expense/category/add -> add_category
[design] cli.py wired: expense/category/list -> list_category
[design] cli.py wired: expense/category/update -> update_category
[design] cli.py wired: expense/category/delete -> delete_category
[design] cli.py wired: budget/list -> list_budget
[design] cli.py wired: budget/add -> add_budget
[design] cli.py wired: budget/update -> update_budget
[design] cli.py wired: budget/delete -> delete_budget
[design] cli.py wired: expense/add -> add_expense
[design] cli.py wired: expense/list -> list_expense
[design] cli.py wired: expense/report/monthly -> get_monthly_report
[design] cli.py wired: expense/report/yearly -> get_yearly_summary
[design] cli.py wired: expense/export -> export_to_csv
[design] cli.py wired: expense/recurring/detect -> detect_recurring
```

C'est **14/14**, sans commande en trop ni manquante — là où la référence 4B
avait eu besoin de `cli_surface.py` pour être recadrée. Nuance importante : la
surface est de toute façon dérivée du **texte du prompt**
(`agentlib/pipeline/cli_spec.py` / `cli_surface.py`) puis réconciliée avec le
design ; ce bon résultat est donc surtout un acquis du générateur, pas un mérite
propre du modèle. Les **options** n'ont pas pu être vérifiées en sortie, puisque
le run n'a écrit aucun fichier.

Le design des *repositories* révèle en revanche une divergence lourde : le
modèle recopie **la même liste de dix méthodes dans les trois repositories**
(Expense, Category, Budget), au lieu de répartir les capacités des puces 4/5/6
du prompt :

```
expense_repository_repository.py  [repositories] list_expenses(...); get_expense_by_id(...);
   add_expense(...); update_expense(...); delete_expense(...); get_monthly_report(...);
   get_yearly_summary(...); get_category_spending(...); export_to_csv(...); detect_recurring()
category_repository_repository.py [repositories] list_expenses(...); get_expense_by_id(...);
   add_expense(...); update_expense(...); delete_expense(...); get_monthly_report(...);
   get_yearly_summary(...); get_category_spending(...); export_to_csv(...); detect_recurring()
budget_repository_repository.py   [repositories] list_expenses(...); get_expense_by_id(...);
   add_expense(...); update_expense(...); delete_expense(...); get_monthly_report(...);
   get_yearly_summary(...); get_category_spending(...); export_to_csv(...); detect_recurring()
```

Le remplissage (`fill`) échoue ensuite en cascade :

```
[fill] repository: kept 0/3 customs; reverted detect_recurring, export_to_csv, get_yearly_summary
    - detect_recurring: calls self._get_date_range() which does not exist on this repository
      — never invent helper methods
    - export_to_csv: calls self._get_date_range() which does not exist on this repository
    - get_yearly_summary: calls self._get_date_range() which does not exist on this repository
[fill] service: output runaway — stream aborted (attempt 1)
[fill] service.export_to_csv: rejected (attempt 3: expense.category: unknown field 'category'
      on Expense (declared: amount_cents, category_id, description, expense_date, id,
      is_recurring, payment_method))
[fill] service: salvaged 6/7 stubs per-method; still stubbed: export_to_csv
```

et le pipeline meurt à la validation, après trois réparations infructueuses :

```
Validation: 10 issue(s)
  - cli.py: nonexistent module 'exceptions'
  - expense_repository_repository.py: nonexistent module 'exceptions'
  - category_repository_repository.py: nonexistent module 'exceptions'
  - budget_repository_repository.py: nonexistent module 'exceptions'
  ...
After repair: 17 remaining
RuntimeError: unresolved import-level errors after repair: ...
Done -- 0 succeeded, 1 failed out of 1 prompt(s).
```

**0 fichier écrit** (les fichiers présents dans `generated/expenses/` datent du
run 4B de contrôle, horodatés 11:57).

### 3.2 `library_system` — un défaut latent du générateur est déclenché

Même schéma, mais le run ne se termine pas proprement : il **casse le
générateur** sur une exception Python non gérée.

```
TypeError: compile() arg 1 must be a string, bytes or AST object
  File "agentlib/pipeline/manifest.py", line 1361, in _manifest_first_blocks
    body = _render_service_file(...)
  File "agentlib/generation/service_render.py", line 4893, in _render_service_file
    cand = _strip_import_enum_validation(cand)
  File "agentlib/generation/service_render.py", line 4064, in _strip_import_enum_validation
    tree = ast.parse(text)
```

`_strip_import_enum_validation` reçoit `None` et appelle `ast.parse(None)`. Le
paramètre `cand` vaut `None` parce que l'étape précédente n'a pas produit de
corps exploitable — précisément parce que le modèle a fourni un design que le
générateur n'a pas su remplir. Autrement dit : **le petit modèle ne provoque pas
seulement un échec propre, il atteint un chemin où une garde manque**. Ce
n'est pas une décision de convention du modèle — c'est un défaut du générateur,
latent avec le 4B, que ce modèle a rendu atteignable.

Le design du modèle porte par ailleurs des noms que le générateur recopie
littéralement en doublant le suffixe :

```
- book_repository_repository.py   [repositories] create_book(...); get_book_by_id(...);
    list_books(author:Optional[str], available_only:bool) -> List[Book]; update_book(...); delete_book(...)
- author_repository_repository.py [repositories] find_books_by_author(...); create_author(...); ...
- member_repository_repository.py [repositories] find_active_members(); find_inactive_members(); ...
- loan_repository_repository.py   [repositories] create_loan(...); list_active_loans(); list_overdue_loans(); ...
- library_service_service.py      [services] add_book(...); list_book(author:str, available_only:bool);
    search_books(query:str); add_member(...); list_member(active_only:bool); borrow(member_id:int, book_id:int);
    return(loan_id:int); get_overdue_loans(); renew_membership(member_id:int); search_books(query:str)
```

On y retrouve, comme chez le 1.7B, les options CLI promues en paramètres de
méthode (`list_book(author, available_only)`, `search_books(query)`), plus :
- `search_books` déclaré **deux fois** dans le même service ;
- des méthodes de service nommées `borrow` / `return` là où le prompt exige
  `borrow_book` / `return_book` :

```
[contract] VIOLATION: spec declares service method 'borrow_book' (Checks availability,
           creates loan, decrements copies) but the design omits it
[contract] VIOLATION: spec declares service method 'return_book' (Sets return_date,
           updates status, increments copies) but the design omits it
```

### 3.3 Décisions de convention du coder 1.5B

| # | ce que le modèle fait | ce que le pipeline attend | conséquence |
|---|---|---|---|
| C6 | double le suffixe des classes : `BookRepository` → fichier `book_repository_repository.py`, `LibraryService` → `library_service_service.py` | un fichier par classe, suffixe une seule fois | noms de fichiers absurdes ; le générateur les recopie tels quels |
| C7 | recopie la **même** liste de méthodes dans les trois repositories (`expenses`) | chaque repository porte les capacités de sa puce du prompt | frontière des couches effacée ; remplissage divergant |
| C8 | met les options CLI en paramètres de méthode (`list_books(author, available_only)`) | les options appartiennent à la surface CLI | sémantique fausse, remplissage dégradé |
| C9 | invente des méthodes internes (`self._get_date_range()`) | n'appeler que ce qui existe | 3 méthodes de repository révoquées |
| C10 | nomme `borrow` / `return` au lieu de `borrow_book` / `return_book` | les noms de méthode que le prompt énonce | 2 violations de contrat |
| C11 | déclare `search_books` deux fois | unicité des méthodes | doublon silencieux |
| C12 | nomme les méthodes de service d'après le vocabulaire CLI (`add_budget`, `list_expense`) plutôt que d'après le prompt | — | sans gravité, mais écarte le design du contrat |
| C13 | ne place pas `get_expense_by_id` / `update_expense` / `delete_expense` dans le **service** (`expenses`) | le prompt les énonce comme méthodes de service | 3 violations de contrat |
| C14 | référence un module `exceptions` qui n'est jamais émis sous ce nom | l'import doit résoudre | 4 erreurs d'import non réparables → arrêt |

Verdict d'acceptabilité pour ce modèle : **non acceptable** sur les deux
objectifs. Sur la conformité, la surface CLI est exacte (14/14 et 9/9) mais
seulement au stade du design, et elle provient du prompt plus que du modèle ;
les violations de contrat (C10, C13) et les noms hors prompt (C6) sont bien des
écarts au prompt. Sur le fonctionnel, il n'y a **rien à exécuter** : 0 fichier.

## 4. qwen2.5-coder-3b-instruct-q4_k_m — le premier petit modèle qui aboutit

Serveur dédié sur 8001, `thinking = 0`, smoke tests propres, exactement les
mêmes conditions que les deux précédents.

### 4.1 `expenses` — SUCCÈS, et conformité parfaite

```
Done -- 1 succeeded, 0 failed out of 1 prompt(s).
  wrote generated/expenses/exceptions.py
  wrote generated/expenses/models.py
  wrote generated/expenses/cli.py
  wrote generated/expenses/money.py
  wrote generated/expenses/expense_repository.py
  wrote generated/expenses/category_repository.py
  wrote generated/expenses/budget_repository.py
  wrote generated/expenses/expense_service.py
  wrote generated/expenses/category_service.py
  wrote generated/expenses/budget_service.py
  wrote generated/expenses/database.py
  wrote generated/expenses/main.py
```

**12 fichiers écrits**, dont trois services séparés (`expense_service.py`,
`category_service.py`, `budget_service.py`) — une décomposition différente de
celle du 4B (un seul service). Vérification des deux objectifs :

```
=== expenses ===
  markers=0 compile=0 functional=4 conforme=0 facade=fail (12/14)
```

**Conformité : 0 échec.** La surface CLI est exactement celle du prompt, et
cette fois les **options** sont vérifiables *en sortie* puisqu'une CLI a été
écrite : `budget list [--category] [--month]`, `expense add --amount …`,
`expense report monthly --month`, etc. C'est le premier petit modèle à passer
cette barre. Aucun marqueur de dégradation silencieuse, compilation propre.

**Fonctionnel : 4 échecs, 3 bugs distincts** — et deux d'entre eux ne sont pas
imputables au modèle.

| # | symptôme | cause | responsable |
|---|---|---|---|
| B1 | `budget list` (sans option) → `UnboundLocalError: cannot access local variable 'category_id'` | variable locale liée seulement dans un `if`, utilisée ensuite. La surface est bonne (`--category`, `--month`) ; c'est le **corps du service** qui est faux | modèle |
| B2 | `expense export … --output x` → `AttributeError: 'ExpenseRepository' object has no attribute 'export_to_csv'` | le générateur **retire** la méthode du repository (`[fill] repository: kept 1/2 customs; reverted export_to_csv (SQL outside designed schema)`) mais `expense_service.py:125` continue de l'appeler (`self.expense_repo.export_to_csv(...)`). **L'élagage n'est pas propagé aux appelants** | **générateur** |
| B3 | `expense recurring detect` → `sqlite3.OperationalError: no such column: e2.expense_id` (×2) | le SQL auto-joint `expenses e2` sur `e2.expense_id` alors que la clé primaire est `id`. Le contrôle « SQL outside designed schema » du générateur attrape exactement cette classe ailleurs (`find_books_by_author: WHERE clause uses unknown column 'author_id'`) mais **laisse passer ici** : un alias (`e2.`) dans un `COUNT(...)` / `IS NOT NULL` échappe à la validation | **générateur** |

### 4.2 `library_system` — ÉCHEC, sur une ambiguïté du prompt

```
[contract] VIOLATION: spec declares service method 'borrow_book' … but the design omits it
[contract] VIOLATION: spec declares service method 'return_book' … but the design omits it
[law A/2] add_book: deterministic create refused - author_id names no field of this entity
[fill] service.borrow: rejected (attempt 3: Loan() missing required field(s) member_id …;
        member.loan_history: unknown field 'loan_history' on Member;
        undefined name 'BookNotFoundException')
[fill] service: output rejected (all 2 attempts)
Done -- 0 succeeded, 1 failed out of 1 prompt(s).
```

La cause première est nette. Le modèle conçoit :

```
Book(id:int*?, title:str, isbn:str*, published_year:int, available_copies:int)
```

**sans `author_id`**, alors que la CLI du prompt impose `library book add
--author-id`. Le 4B, lui, ajoute le champ (`author_id: Optional[int] = None`
dans son `models.py`). Le prompt est ici **ambigu** : la puce « Book model » ne
liste pas `author_id`, mais la ligne de commande l'exige. Le 4B résout
l'ambiguïté, le 3B non — et l'échec est franc (`0 succeeded`).

S'y ajoutent des erreurs de remplissage propres au modèle (`member.loan_history`
inventé, `BookNotFoundException` non défini, `Loan()` construit sans
`member_id`) et les deux violations de contrat déjà vues chez le 1.5B
(`borrow` / `return` au lieu de `borrow_book` / `return_book`).

### 4.3 Verdict pour le 3B

- **Conformité au prompt** : **atteinte** sur `expenses` (0 échec, options
  vérifiées en sortie). Sur `library_system`, non mesurable faute de sortie, et
  le design viole le contrat sur deux noms de méthode.
- **Code fonctionnel** : **partiellement atteint** — 12 des 16 chemins testés
  passent. Les 3 bugs se répartissent en **1 décision du modèle** et **2
  manques du générateur**.

C'est le premier petit modèle à franchir la barre de la conformité et à laisser
un projet exécutable ; c'est aussi lui qui a révélé les deux manques du
générateur décrits en B2 et B3.

## 5. Annexe — le message « completion hit max_tokens »

Ce message apparaît dans les logs des trois petits modèles et mérite une
explication exacte, car il est facile de le lire de travers.

### 5.1 D'où il vient

`agentlib/llm/client.py` l'émet sur `finish_reason == "length"`, en
non-streaming (ligne 74) comme en streaming (ligne 108) :

```python
if choice.get("finish_reason") == "length":
    print("    [warn] completion hit max_tokens=%d — output truncated" % max_tokens,
          file=sys.stderr)
```

Le `4096` ne vient pas des remplissages de fichiers (qui utilisent
`LLM_MAX_TOKENS_LONG`, 8192 par défaut) mais des **deux appels de design** :

```
agentlib/pipeline/design.py:283   messages, schema=schema, max_tokens=4096
agentlib/pipeline/design.py:669   messages, schema=schema, max_tokens=4096
```

### 5.2 Ce n'est pas un faux positif — et le log serveur le prouve

Le log llama.cpp d'une des requêtes fautives :

```
slot print_timing: id  0 | task 5818 |        eval time = 52443.43 ms /  4096 tokens
slot print_timing: id  0 | task 5818 |       total time = 52455.23 ms /  4097 tokens
slot      release: id  0 | task 5818 | stop processing: n_tokens = 4652, truncated = 0
```

- `eval time = 4096 tokens` : le serveur a **réellement généré 4096 tokens**,
  soit exactement le plafond. La génération a bien été coupée au cap.
- `n_tokens = 4652` = **556 (prompt) + 4096 (sortie)**.
- `truncated = 0` porte sur le **prompt d'entrée** (il tenait dans les 8192),
  pas sur la sortie. Les deux champs mesurent deux choses différentes ; c'est
  cette homonymie qui fait croire à un faux positif.

### 5.3 Le warning déclenche-t-il un retry ?

Pas directement : c'est un `print`, il ne lève rien. Ce qui déclenche le retry,
c'est l'échec d'extraction JSON en aval. Dans le run `library_system` du modèle
coder, les compteurs concordent exactement — **6 warnings, 6 échecs de parse**,
et le JSON coupé en plein objet :

```
JSON parse failed (attempt 1): '{\n  "exceptions": [\n    "BookNotFoundError", ...   <- coupé
[design] models.py: no JSON (attempt 1)
```

Structure d'essais : `_json_complete(..., attempts=2)` (température 0 puis 0,7)
imbriqué dans le `for attempt in (0, 1)` de `design.py`
(`design.py:282` et `design.py:668`), soit **jusqu'à 4 décodages par design**.
Coût mesuré ici : 6 × 4096 tokens à ~78 tok/s ≈ **5 minutes** brûlées pour un
design qui échoue quand même.

**Nuance honnête** : le warning signifie « le serveur s'est arrêté au plafond »,
ce qui n'implique pas *en soi* que la charge utile soit inutilisable — si le
JSON s'était refermé avant le cap, l'extraction aurait réussi et le warning
n'aurait rien coûté. C'est un diagnostic, pas un verdict. Mais dans les runs
observés, aucun des 6 n'était dans ce cas : les 6 étaient bien coupés en plein
objet, donc les 6 étaient bien perdus.

## 6. Verdict par rapport aux deux objectifs

**Objectif 1 — code fonctionnel.**

| modèle | `expenses` | `library_system` |
|---|---|---|
| 4B (référence) | atteint (0 échec) | atteint (0 échec) |
| 1.7B | non mesuré | **non atteint** — 0 fichier |
| 1.5B | **non atteint** — 0 fichier | **non atteint** — 0 fichier + crash |
| **3B** | **partiel** — 12/16 chemins, 3 bugs (dont **2 du générateur**) | **non atteint** — 0 fichier |

**Objectif 2 — conformité au prompt.**

| dimension | 1.7B | 1.5B | 3B |
|---|---|---|---|
| chemins de commandes conformes | non atteint | oui au design (9/9, 14/14) | **oui en sortie** (14/14) |
| options conformes | non atteint | non vérifiable (aucune CLI) | **oui** |
| noms de méthodes exigés par le prompt | non atteint (`list_book`…) | non (`borrow` au lieu de `borrow_book`) | non sur `library_system` |
| méthodes demandées présentes | non atteint | non (3 omissions) | conforme sur `expenses` |
| noms de fichiers/classes | non conforme (C4) | non conforme (`*_repository_repository.py`) | conforme |
| commandes non demandées | oui (`search_authors`) | non observé | aucune |

Le **3B est donc le premier petit modèle à satisfaire l'objectif de conformité**
— sur `expenses`, et **en sortie** (l'ancienne mesure ne portait que sur le
design). Sur `library_system` il ne produit rien, et son design viole encore le
contrat (`borrow` / `return`).

**Trois défauts du générateur ont été mis au jour** par ces modèles. Tous sont
indépendants du choix de modèle et sont ici seulement **signalés** : aucune
correction n'a été appliquée.

1. **Garde manquante** — `agentlib/generation/service_render.py:4064` appelle
   `ast.parse(text)` sans vérifier `text is not None`. Le 1.5B déclenche un
   `TypeError` nu au lieu d'un échec propre.
2. **Élagage non propagé** — quand le générateur retire une méthode de
   repository (ici `export_to_csv`, SQL invalide), les appelants ne sont pas
   mis à jour : `expense_service.py:125` continue d'appeler
   `self.expense_repo.export_to_csv(...)` → `AttributeError` à l'exécution
   (bug B2 du 3B).
3. **Validation SQL incomplète** — le contrôle « SQL outside designed schema »
   attrape `WHERE … unknown column 'author_id'` mais laisse passer un alias
   (`e2.expense_id`) dans un `COUNT(...)` / `IS NOT NULL` (bug B3 du 3B).

## 7. Reproductibilité

```bash
# 1. serveur dédié (mêmes drapeaux que server.sh ; seuls -m et --port changent)
cat > /tmp/server_coder15.sh <<'EOF'
rm -f /tmp/llama_coder15.log
caffeinate /opt/homebrew/bin/llama-server -t 4 --ctx-checkpoints 0 -ngl 99 \
  -m /Users/gillesstenger/Documents/my-ide/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf \
  --port 8001 --host localhost --parallel 1 --cache-ram 0 -c 8192 -b 2048 -ub 2048 \
  -sps 0.0 --log-file /tmp/llama_coder15.log
EOF
bash /tmp/server_coder15.sh

# 2. génération, sans rien modifier du dépôt
cat > /tmp/run_coder.sh <<'EOF'
#!/bin/bash
export LLM_BASE_URL=http://localhost:8001/v1
cd /Users/gillesstenger/Documents/neurosymbolic || exit 1
exec python3 agent.py --prompt "$1"
EOF
bash /tmp/run_coder.sh expenses
bash /tmp/run_coder.sh library_system

# 2bis. idem pour le 3B : même script serveur, -m pointe sur la racine du dépôt
cat > /tmp/server_coder3b.sh <<'EOF'
rm -f /tmp/llama_coder3b.log
caffeinate /opt/homebrew/bin/llama-server -t 4 --ctx-checkpoints 0 -ngl 99 \
  -m /Users/gillesstenger/Documents/neurosymbolic/qwen2.5-coder-3b-instruct-q4_k_m.gguf \
  --port 8001 --host localhost --parallel 1 --cache-ram 0 -c 8192 -b 2048 -ub 2048 \
  -sps 0.0 --log-file /tmp/llama_coder3b.log
EOF
bash /tmp/server_coder3b.sh
bash /tmp/run_coder3b.sh expenses        # même surcharge LLM_BASE_URL, port 8001
bash /tmp/run_coder3b.sh library_system

# 3. référence (4B, port 8000, aucune surcharge)
bash server.sh
python3 agent.py --prompt expenses
python3 agent.py --prompt library_system
python3 run_named_prompts.py --only expenses --skip-generate
python3 run_named_prompts.py --only library_system --skip-generate
```

Logs conservés : `/tmp/gen17_evidence_thinking_on.log`,
`/tmp/gen17_evidence_library_nothink_off.log`, `/tmp/gen_coder_library.log`,
`/tmp/gen_coder_expenses.log`, `/tmp/gen_coder3b_library.log`,
`/tmp/gen_coder3b_expenses.log`, `/tmp/gen_4b_library.log`,
`/tmp/gen_4b_expenses.log`, `/tmp/llama_coder15.log`, `/tmp/llama_coder3b.log`.

## 8. Ce que ces essais apprennent

1. **L'erreur de convention la plus répétée** (les modèles 1.7B et 1.5B, sur
   les deux prompts) est de traiter les **options CLI comme des paramètres de
   méthode**. C'est le premier obstacle qui bloque ces deux modèles.
2. **Le contrat de nommage n'est pas négociable** dans le pipeline : `borrow`
   au lieu de `borrow_book` suffit à produire une violation, et un suffixe
   doublé (`*_repository_repository.py`) est recopié tel quel. Le 3B le viole
   encore sur `library_system`.
3. **Le palier est entre 1.5B et 3B.** À 3B, `expenses` aboutit : surface
   conforme **en sortie**, projet exécutable. En dessous, aucun des deux
   modèles n'écrit le moindre fichier.
4. **Trois défauts du générateur** ont été révélés par ces modèles (détaillés
   en § 6) : une garde manquante (`ast.parse(None)`), un élagage non propagé
   aux appelants, et une validation SQL incomplète sur les alias.
5. **Le prompt `library_system` est ambigu** sur `author_id` : la puce « Book
   model » ne le liste pas, la ligne de commande `library book add
   --author-id` l'exige. Le 4B et le 3B divergent sur cette seule décision, et
   l'un aboutit, l'autre non.
6. **Le diagnostic de troncature est exact mais ambigu** : `truncated = 0` dans
   le log serveur concerne l'entrée, pas la sortie, et le message du client ne
   dit pas si le JSON était récupérable ou non.

Aucune de ces observations n'a donné lieu à une correction : la consigne était
de mesurer et de rapporter, pas de réparer.
