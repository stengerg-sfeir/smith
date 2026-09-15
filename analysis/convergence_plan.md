# Plan de convergence — 100 % sur `library_system` et `expenses`

> **État de ce document — 14/09/2026, 17:5x.** C'est l'état de ce que nous voulons faire
> **aujourd'hui**, après la réévaluation de la régénération fraîche du commit `33ea49ee`.
> Le périmètre est **strictement** `prompts/prompt_library_system.txt` et
> `prompts/prompt_expenses.txt`. Aucun autre prompt n'est touché dans ce chantier.
> Le contrat de méthode est : **corriger le générateur (`agentlib/`), jamais le code généré**.

---

## 1. Objectif et condition d'arrêt

Objectif : ces deux prompts produisent un projet **100 % fonctionnel** et **100 % conforme
au prompt**, où « 100 % » est défini par les six conditions ci-dessous, tenues
**simultanément sur régénération fraîche** :

1. **Conformité bidirectionnelle** prompt↔surface CLI : 0 violation
   (`run_cli_conformity.py`) — dans les deux sens : rien de manquant, rien en trop.
2. **Inventaire** : 0 option `DROPPED`, 0 exception déclarée non levée, 0 méthode morte,
   0 incohérence d'annotation, 0 `DEFAULT`/nullabilité incohérents entre modèle et DDL.
3. **Balayage exhaustif de la surface** : chaque commande exécutée avec {options requises
   seules} ∪ {toutes les options} ; 0 trace, 0 crash, **et** assertion d'effet en base pour
   chaque option (une option sans effet est un échec).
4. **Assertions de valeur** : montants rendus en décimal, énumérations du prompt rejetées
   hors vocabulaire, sorties de rapport exactes.
5. **Déterminisme** : K = 10 régénérations identiques octet-pour-octet, ou différences
   expliquées une par une.
6. **Mutation sémantique** : 100 % des mutants tués (`run_semantic_oracle.py`).

Tant que les six ne tiennent pas sur une **régénération fraîche**, la tâche n'est pas finie.

## 2. Méthode imposée (boucle par loi, pas par bug)

On ne corrige **pas** des instances : on corrige des **lois**. Pour chaque loi :

```
   (1) INVENTAIRE      mesurer exhaustivement la loi sur les 2 projets (données, pas sondage)
   (2) LOI             formuler la règle manquante dans le générateur (1 seule à la fois)
   (3) CORRECTION      l'implémenter dans agentlib/ (+ test négatif qui échouait AVANT)
   (4) PREUVE 2 PROMPTS régénérer les 2 projets, rejouer inventaire + portes + assertions
   (5) NON-RÉGRESSION  rejouer le balayage exhaustif et vérifier qu'aucune assertion
                       auparavant verte ne rougit
   (6) RÉÉVALUATION    audit indépendant de mes propres scripts (voir §4) : on ne fait pas
                       confiance au script qui vient de passer, on re-mesure par un autre chemin
   --> on ne passe à la loi suivante QUE si (4)(5)(6) sont vertes.
```

**Interdit** : élargir un validateur, ajouter un `try/except` ou assouplir une porte pour
faire passer la loi. Toute correction doit être accompagnée d'un **test négatif** qui
échouait sur l'état antérieur (sinon on « cache » au lieu de corriger).

## 3. Les lois à corriger (état au 14/09 après réévaluation)

Les neuf défauts relevés se rangent en **4 lois**. Les lois sont indépendantes entre elles ;
à l'intérieur d'une loi, corriger une instance ne corrige pas forcément ses sœurs.

### Loi A — Traversée de valeur `option CLI → paramètre de service → champ de modèle → colonne`
Aucune table de correspondance unique, aucune règle `None` aux frontières, drop silencieux
des paramètres non reconnus.

| Instance | Statut |
|---|---|
| `expense add` sans `--expense-date` → crash `NOT NULL` (défaut d'origine 1) | **corrigé** (repli `date.today()`) — reste à prouver au titre de la loi |
| **N1** `budget update` sans `--amount` → `decimal.InvalidOperation`, trace exposée | **corrigé, prouvé** (§5ter) |
| **N2** `library book add --copies N` silencieusement ignoré (`available_copies` reste 1) | **corrigé, prouvé** (§5quater) |
| défaut d'origine 1 (repli bool `is_recurring`) | corrigé, même loi |
| défauts d'origine 2/3/4 (surface, noms/groupes/options) | corrigés, hors loi (surface) |

Risque connu : un alias option→champ par radical est **ambigu** sur `expenses`
(`--amount` peut viser `amount_cents` ou `amount_limit_cents`) ⇒ règle : **alias unique
sinon refus explicite** (jamais de drop muet).

### Loi B — Garde applicative déclarée mais non générée
Toute exception déclarée par le design doit être levée sur un chemin atteignable, avec un
message exploitable ; sinon elle est trompeuse.

| Instance | Statut |
|---|---|
| **N3** `library return --loan-id L` non idempotent : `available_copies` 1→2→3, `LoanAlreadyReturnedError` déclarée jamais levée | **ouvert** |
| **N7** messages vides (`Error: 99`, `Error: 2`) et erreur sqlite brute qui fuit (`FOREIGN KEY constraint failed` sur membre inexistant) | **ouvert** |
| `MemberNotActiveError`, `InvalidMemberIdError`, `DuplicateEmailError`, `ValidationError`… non levées | à mesurer par l'inventaire |

### Loi C — Convention de valeur non propagée jusqu'au rendu
Money, énumérations, booléens tri-état, défauts DDL : la convention est connue du design
mais ne va pas jusqu'au code rendu ou jusqu'à la base.

| Instance | Statut |
|---|---|
| **N4** montants non convertis en décimal dans les rapports (`total: 103400`, `average_monthly_spend: 36466.666666666664`), `category list` affiche `monthly_budget=50000` | **ouvert** — contredit « convert to/from decimal for display » |
| **N5** `payment_method (cash/card/transfer)` non validé (`--method bitcoin` accepté) | **ouvert** |
| **N6** `--no-recurring` exposé en plus de `[--recurring]` | **ouvert** |
| **N9** `available_copies NOT NULL` sans `DEFAULT 1`, `is_active BOOLEAN NOT NULL` sans `DEFAULT 1` (le modèle, lui, a les défauts) | **ouvert** |

### Loi D — Inventaire mort / non utilisé
Rien ne déduit qu'un élément déclaré n'est jamais utilisé ; du code incohérent survit.

| Instance | Statut |
|---|---|
| méthodes jamais appelées (`loan_repository.get_overdue_loans_count` — compte tous les prêts ; `author_repository.list_authors_with_books` — requête écrasée, `include_inactive` ignoré) | **ouvert** |
| `expense_repository.export_to_csv` — crasherait avec des `str` (appelle `.isoformat()`) | **ouvert** |
| ~12 méthodes mortes supplémentaires (cf. rapport de réévaluation) | **ouvert** |
| annotations nommant un **module** et non un type (`Optional[datetime]`) | **ouvert** |

---

## 4. Preuve exigée par loi + réévaluation indépendante

Pour chaque loi, **avant** de passer à la suivante :

| Preuve | Outil | Critère |
|---|---|---|
| Inventaire de la loi | détecteur statique (AST sur le code généré, sans LLM) | la section de la loi est **vide** |
| Balayage de surface | exécution de **chaque** commande, {requises seules} ∪ {toutes options} + assertions d'effet en base | 0 trace, 0 crash, 0 no-op |
| Conformité | `python3 run_cli_conformity.py` | 0 violation (2 sens) |
| Invariants + mutation | `python3 run_semantic_oracle.py` | 100 % invariants, 100 % mutants tués |
| Façade | `python3 run_facade_execution.py --prompt library_system --prompt expenses` | tout `pass`, 0 unmapped |
| Compilation | `python3 -m compileall -q agentlib` | aucune erreur |

**Réévaluation indépendante (obligatoire).** Mes scripts de test ont déjà menti deux fois
dans ce chantier (`/tmp/ev_lib_test2.py` a conclu « pas de bug de retour » parce que le
membre n'existait pas ; `/tmp/ev_api_test.py` est mort sur une collision de `sys.path` en
donnant l'illusion d'un échec). Donc, pour chaque loi :

- la preuve est refaite par un **second chemin** qui n'utilise ni le même script, ni la même
  API (ex. CLI subprocess **et** appel service direct ; lecture SQL directe **et** assertion
  sur la sortie console) ;
- chaque assertion porte sur un **état observable** (ligne en base, sortie exacte), jamais
  sur un code de retour seul ;
- le test négatif (reproduction du bug d'origine) doit **échouer** sur l'état antérieur —
  sinon la preuve ne vaut rien.

## 5. Journal de progression

| Date | Étape | Loi | Statut | Preuve |
|---|---|---|---|---|
| 14/09 | Réévaluation fraîche post-`33ea49ee` | — | fait | rapport complet (défauts 1-4 traités ; N1-N9 ouverts) |
| 14/09 | Cadrage du chantier (ce document) | — | fait | `analysis/convergence_plan.md` |
| 14/09 | Inventaire exhaustif (statique) | A-D | **fait** | §8 : chiffres mesurés sur les 2 projets |
| 14/09 | Balayage exhaustif de surface | — | **fait** | §8 : library 0 trace / expenses 1 trace (N1) |
| 14/09 | **Loi A / A1** conversion monétaire None-préservante | A | **corrigé, prouvé** | §5ter |
| 15/09 | Loi A / A2 paramètre sans champ (`copies`) | A | **corrigé, prouvé** | §5quater |
| — | Loi B : gardes déclarées | B | ouvert | — |
| — | Loi C : conventions de valeur | C | ouvert | — |
| — | Loi D : inventaire mort | D | ouvert | — |
| — | Stabilisation K = 10 régénérations | — | à faire | identité octet-pour-octet |

## 5bis. Phase 0 — résultats mesurés (14/09)

Détecteur : `/tmp/inv.py` (AST sur le code généré, **sans LLM**).
Balayage : `/tmp/sweep.py` (chaque commande × {requises seules} ∪ {toutes options},
via `click.testing.CliRunner` ; toute exception ≠ `SystemExit` = échec).

### Inventaire statique

| Section | `library_system` | `expenses` |
|---|---|---|
| 1. option CLI non transmise à un paramètre | 0 | 0 |
| 1bis. nom d'option en trop sur une option existante | 0 | 1 (`--no-recurring`, N6) |
| 2. paramètre de service jamais utilisé dans son corps | **1** (`add_book: copies`, N2) | 0 |
| 3. champ de modèle que le create ne peut pas alimenter | 2 (`available_copies`, `membership_date`) | 0 |
| 4. exception déclarée JAMAIS levée | **8** | 0 |
| 4bis. exception sans message | **11** | 3 |
| 5. méthode jamais appelée hors de son fichier | 18 (dont 5 exigées par le prompt) | 13 (dont 4 exigées) |
| 6. `DEFAULT` du modèle absent de la DDL | 3 (`available_copies`, `is_active`, `status`) | 2 (`payment_method`, `is_recurring`) |
| 7. annotation nommant un **module** au lieu d'un type | **4** (`Loan.due_date`, `Loan.loan_date`, `Loan.return_date`, `Member.membership_date`) | 0 |
| 8. énumération du prompt non validée | `status` (active/returned/overdue) | `payment_method` (cash/card/transfer) |

Lecture de ces chiffres (c'est la matière des lois) :
- **N2 confirmé mécaniquement** : `LibraryService.add_book` reçoit `copies` et ne l'utilise
  **nulle part** — c'est le seul paramètre « muet » des deux projets. Le champ
  `available_copies` n'est jamais alimenté → la ligne prend le défaut du dataclass (1).
- **N6 confirmé** : `expense add` déclare `--recurring/--no-recurring`, soit un second nom
  d'option que le prompt n'a pas demandé.
- **Loi B quantifiée** : 8 exceptions jamais levées et 11 classes sans message côté library,
  3 sans message côté expenses — l'un (N3, `LoanAlreadyReturnedError`) est en outre la
  garde manquante du double retour.
- **Loi D quantifiée** : 31 méthodes jamais appelées au total ; **9 d'entre elles sont
  pourtant exigées par les prompts** (« CRUD + find … »), donc leur statut « non appelée »
  est normal — ce sont les **autres** qui sont du code mort à traiter.
- **Loi C quantifiée** : 5 incohérences de `DEFAULT` (dont 2 explicitement décrites par les
  prompts : `available_copies (default 1)`, `is_active (default True)`) et 2 énumérations
  non validées (également explicites dans les prompts).

### Balayage exhaustif de surface (23 commandes × 2 variantes = 46 exécutions)

- `library_system` : **0 trace**. Toutes les variantes « requises seules » passent.
- `expenses` : **1 trace**, et c'est exactement N1 :
  `budget update --category-id 1 --month 2024-03` → `decimal.InvalidOperation`
  (`from_decimal(None)`), alors que `--amount` est optionnel dans le prompt.
  La variante « toutes options » (`--amount 1.50`) passe — ce qui explique que les quatre
  portes automatiques restaient vertes.

Ces deux détecteurs sont désormais les **instruments de preuve** des lois : ils doivent
afficher les mêmes compteurs, à zéro, sur les deux projets avant de passer à la loi suivante.

## 5ter. Loi A / A1 — conversion monétaire None-préservante (corrigé, prouvé)

**Règle ajoutée** (`agentlib/generation/cli_render.py`) : une conversion de valeur au
passage de frontière (`from_decimal`) **formate** une valeur fournie, elle ne **valide**
jamais une valeur absente. Une option *optionnelle* non fournie arrive à `None` ; la
conversion devient `None if x is None else from_decimal(x)`. L'optionalité est décidée par
`_optional_cli_option` : option non `required` **ou** champ portant un défaut de spec (le
renderer retire alors `required=True`). Les options requises gardent la conversion simple,
donc aucun changement de comportement par ailleurs.

**Preuve 1 — la ligne générée** (régénération fraîche d'`expenses`) :
```
111: add_budget      ... amount_limit_cents=from_decimal(amount)                              (requis, inchangé)
126: update_budget   ... amount_limit_cents=None if amount is None else from_decimal(amount)  (optionnel, protégé)
158: add_expense     ... amount_cents=from_decimal(amount)                                    (requis, inchangé)
```

**Preuve 2 — balayage exhaustif** (`/tmp/sweep.py`, 23 commandes × 2 variantes) :
`expenses` passe de **1 trace** (`decimal.InvalidOperation`) à **0** ; `library_system`
reste à **0**.

**Preuve 3 — réévaluation indépendante** (`/tmp/a1_check.py`, chemin CLI + lecture SQL
directe, pas le même script que le balayage) :
```
budget add --amount 500.00                         → 50000 en base
budget update --category-id 1 --month 2024-03     → exit 0, aucune trace,
                                                     base INCHANGÉE (50000) : une omission
                                                     n'écrase plus la valeur
budget update ... --amount 20.00                   → 2000
budget update --category-id 99 ... (sans/avec --amount) → exit 1 « Error: 99 », sans trace
```

**Non-régression** : `compileall` OK ; conformité 0 violation sur les 3 prompts énumérés
(expenses 14, library 9, inventory 11) ; oracle `library 15/15` + `expenses 16/16` avec
**tous les mutants tués** ; façade `expenses 14/14`, `library_system 9/9`, 0 unmapped.

## 5quater. Loi A / A2 — un paramètre de create sans champ n'est plus perdu en silence (corrigé, prouvé)

**Règle ajoutée** (`agentlib/generation/service_render.py`) : la branche `add_<entité>` ne
garde plus seulement les paramètres qui **épellent** un champ (`if p in fields`). Chaque
paramètre est lié au champ qu'il désigne, par `_create_field_binding` :

- correspondance **exacte** d'abord ;
- sinon **variante morphologique unique** (`<champ>_<param>` ou `<param>_<champ>`) :
  `copies` → `available_copies` — le mot de l'appelant pour UNE colonne ;
- sinon **refus explicite** : plusieurs candidats (une paramètre `amount` face à
  `amount_cents` ET `amount_limit_cents`) ou aucun (« names no field of this entity »).
  Dans les deux cas le corps déterministe n'est PAS rendu (`return None`), et
  `_report_create_refusal` l'inscrit dans le journal du run. Une valeur fournie par
  l'appelant n'est donc jamais jetée en silence et jamais écrite dans la mauvaise colonne.

Le même liage est propagé aux trois autres usages de la branche : `covered` (colonnes
réellement alimentées), les replis de date/bool (classés sur le **champ**, émis sur le
**paramètre**), la validation de clé étrangère, et la branche data-dict (un paramètre non
porté par le dict refuse aussi le corps).

**Preuve 1 — test unitaire du renderer** (`/tmp/a2_unit.py`, appel direct de
`_generic_service_delegation`, sans LLM) :
```
alias      → book = Book(title=title, isbn=isbn, available_copies=(copies if copies is not None else 1))
ambigu     → None (refus)   + message « ambiguous - could be amount_cents or amount_limit_cents »
aucun champ→ None (refus)   + message « names no field of this entity »
exact      → x = X(amount_cents=amount_cents)   (comportement inchangé)
```

**Preuve 2 — ligne générée** (régénération fraîche, `generated/library_system/library_service.py:64`) :
`Book(..., available_copies=(copies if copies is not None else 1))`.

**Preuve 3 — réévaluation indépendante de bout en bout** (`/tmp/a2_e2e.py` : vrai
sous-processus CLI + lecture SQLite directe, chemin différent du test unitaire) :
```
library book add --title T --isbn IS1 --author-id 1 --published-year 2000 --copies 5 → exit 0, base [(5,)]
library book add --title T2 --isbn IS2 --author-id 1 --published-year 2001 --copies 1 → exit 0, base [(1,)]
RESULT: PASS
```
(Avant la correction, les deux lignes valaient 1 : le paramètre était ignoré.)

**Portée mesurée** (les 60 projets de `generated/`, `/tmp/a2_all.py`) : **une seule**
méthode de create non résolue sur tout le corpus — `generated/59.add_discount`, dont les
paramètres `discount_type`/`min_order_total` ne nomment aucun champ de `Discount`
(les colonnes sont `type` et `min_order_amount`). Elle était déjà rendue par le fill LLM
avant la loi ; la loi la rend simplement **visible** au lieu de la laisser produire un
corps qui passe des kwargs inexistants. Aucune autre régression de rendu.

**Non-régression** : `compileall` OK ; `run_cli_conformity.py --prompt library_system` →
**9 commandes du prompt, 0 violation** ; aucun marqueur interdit dans le journal de run
(`grep -nE "reject|dropped …|still stubbed|reverted|sanitized|dropped infeasible|law A/2"`
= aucun résultat).

## 6. Risques de régression croisée (à vérifier à chaque loi)

| Correction | Peut casser | Vérification imposée |
|---|---|---|
| Loi A — garde `None` sur la conversion monétaire | rien d'observé a priori (chemin aujourd'hui en trace) | rejouer tous les `*_cents` avec et sans option |
| Loi A — alias option→champ | peut lier le **mauvais** champ (`--amount` → `amount_cents` vs `amount_limit_cents`) | exiger alias **unique**, sinon refus explicite ; test négatif de l'ambiguïté |
| Loi B — idempotence de `return_book` | le texte du prompt ne demande pas l'idempotence : c'est un **choix de comportement** | valider le choix explicite (double retour = erreur) et vérifier que le 1er retour reste conforme |
| Loi C — affichage décimal | `money.py` est partagé : `budget list` (déjà conforme) ne doit pas changer | comparer sortie avant/après, caractère par caractère |
| Loi C — validation d'énum | peut rejeter des valeurs utilisées par les tests de façade existants | rejouer `run_facade_execution.py` sur les 2 prompts |
| Loi C — `DEFAULT` en DDL | peut changer la nullabilité effective d'une colonne écrite par le code | rejouer tout le balayage (créations sans option) |
| Loi D — suppression/câblage du code mort | supprimer une méthode utilisée indirectement | vérifier par AST qu'aucun appel (même dynamique via `getattr`) ne subsiste |

## 7. Périmètre et limites honnêtes

- **Dans le périmètre** : `library_system`, `expenses`, leurs deux prompts, le générateur
  (`agentlib/`) et les portes (`run_*.py`, `behavior_tests/`).
- **Hors périmètre** : `inventory`, `cli_tool`, `multi_module`, les 60 prompts de
  `prompts/`. Ils servent seulement de **non-régression** (`run_facade_execution.py` les
  inclut) : une loi corrigée ne doit pas les casser, mais on ne les audite pas.
- **Limite de la notion de « 100 % »** : elle est relative à (a) la surface CLI **déclarée
  par le prompt**, (b) les exigences **énumérées** par le prompt. Un usage imprévu par
  l'utilisateur final (valeur absurde, concurrence, très gros volume) n'est couvert que si
  le prompt l'exige. Cette limite est explicite, pas cachée.
- **Variance du fill LLM** : tant que la condition 5 (K = 10 régénérations) n'est pas tenue,
  « corrigé » peut être un coup de chance. C'est la raison d'être de l'étape de stabilisation.

## Annexe — Mesures de la réévaluation du 14/09 (baseline avant ce chantier)

Surface CLI (verbatim, `--help`) :
- `library` → `book, borrow, member, overdue, return` ; `library book` → `add, list, search` ;
  `library member` → `add, history, list` (**9/9** commandes du prompt, 0 en trop).
- `budget` → `add, delete, list, update` ; `expense` → `add, category, export, list,
  recurring, report` ; `expense category` → `add, delete, list, update` ;
  `expense report` → `monthly, yearly` ; `expense recurring` → `detect`
  (**14/14** commandes du prompt, 0 en trop).

Portes (arbre propre `33ea49ee`, régénérations du 14/09) :
- `compileall` : OK.
- `run_cli_conformity.py` : expenses 14 commandes / 0 violation ; library 9 / 0 ; inventory 11 / 0.
- `run_semantic_oracle.py` : library 15/15 + mutation pass ; expenses 16/16 + mutation pass.
- `run_facade_execution.py` : cli_tool 5/5 ; inventory 12/12 ; expenses 14/14 ; library 9/9.

Contre-exemples mesurés malgré ces portes vertes :
- `budget update --category-id 1 --month 2024-03` → trace `decimal.InvalidOperation` (N1).
- `library book add … --copies 5` → `available_copies = 1` (N2), y compris via
  `svc.add_book(copies=5)`.
- `library return --loan-id 1` trois fois → `available_copies` 1 → 2 → 3 (N3).
- `expense report monthly --month 2024-03` → `total: 103400`, `per_category {1: 103400}`,
  `average_monthly_spend: 36466.666666666664` (N4).
- `expense add … --method bitcoin` → accepté (N5).
- `expense add --help` → `--recurring / --no-recurring` (N6).
