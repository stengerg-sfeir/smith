# D'où vient le manque de commandes sur 41–60 : LLM ou déterministe ?

Réponse courte : **la cause proche est côté LLM** (l'extraction d'intentions
omet des méthodes de création), **et la cause profonde est déterministe** — le
filet qui rattrape exactement ce cas est *conditionné à un mot littéral*.

## 1. La perte se produit dans le DESIGN, pas dans le rendu

Génération de 42 avec `NEUROSYM_DUMP_DESIGNS=/tmp/d42`, puis lecture du design
réellement produit (`analysis/state_41_60.py` mesure ensuite le CLI livré) :

    === entités conçues ===            ['Customer', 'Purchase']
    === méthodes conçues ===
    repositories  ['get_customer_report', 'search_customer']
    repositories  ['get_purchase_total', 'list_purchases']
    services      ['add_customer', 'get_customer_report', 'get_purchase_total',
                   'list_purchase', 'search_customer']

Le design contient `add_customer` (et la CLI livre bien `customer add`) mais
**aucune méthode de création d'achat** — alors que le prompt dit « manage
customers and their purchases ». L'entité *Purchase* est reconnue (dépôt,
service), elle est seulement conçue **en lecture seule**. Le rendu déterministe
est donc fidèle : il n'a rien à rendre.

## 2. Le filet déterministe existe, mais il est gaté sur le mot « CRUD »

`agentlib/pipeline/cli_surface.py:681` :

```python
def _crud_floor(commands, prompt_text, entities_by_class):
    """... Intent extraction is LLM-based and may miss a verb ... but the word
    CRUD is a deterministic contract. For every designed entity the prompt
    actually names, ensure add/list/update/delete all exist ..."""
    low = (prompt_text or "").lower()
    if not re.search(r"\bcrud\b", low):
        return commands          # <-- rien ne se passe sans le mot
```

Le même design, le même texte de prompt, seule différence l'ajout d'une phrase :

| entrée | commandes ajoutées par le filet |
|--------|----------------------------------|
| texte réel de 42 | **0** |
| texte de 42 + « Provide CRUD operations. » | **8** — dont `purchase add`, `purchase list`, `purchase update`, `purchase delete` |

(reproduit par `/tmp/test_crud_gate.py` sur le dump ci-dessus)

C'est la cause profonde : **la garantie déterministe qui empêche une commande de
création de disparaître est déclenchée par un seul mot du prompt.**

## 3. Pourquoi 01–40 passent quand même (sans le mot CRUD)

Corrélation mesurée sur les 60 prompts :

- **41–60 : 0 sur 19** contient le mot « CRUD » → le filet ne se déclenche pour
  aucun d'eux.
- **01–40 : 23 sur 40** le contiennent → filet actif.
- Les 17 autres prompts de 01–40, sans « CRUD », **énoncent leurs opérations** :
  `add`, `update`, `delete`, `search`, `filter`, `list` figurent dans le texte
  (ex. 05, 07, 11, 14, 24…), donc l'extraction LLM les trouve.

À l'inverse, côté 41–60 :

    verbes d'opération énoncés
    41: AUCUN   42: —      43: AUCUN   44: —      45: AUCUN
    46: —       47: AUCUN  48: add    49: AUCUN  50: —
    51: —       52: —      53: —      54: —      55: —
    56: —       57: —      58: —      60: search

**Cinq prompts (41, 43, 45, 47, 49) n'énoncent aucune opération du tout** : ils
décrivent un domaine et des comportements. Tout ce qui doit exister est alors
*inféré* par le LLM, et rien ne rattrape les oublis.

## 4. Conclusion

1. **Cause proche : le LLM.** L'extraction d'intentions conçoit les entités
   « principales » en lecture/écriture (customer, product, book, booking) mais
   laisse en lecture seule les entités **enfant / transaction / personnes**
   (purchase, sale, task, employee, person, lignes de commande). Preuve : le
   design de 42 ci-dessus.
2. **Cause profonde : le déterministe.** Le seul filet général est conditionné
   au token « CRUD ». Il fonctionne (8 commandes ajoutées en le déclenchant) ;
   il ne se déclenche jamais sur ces prompts.
3. **« Overfitté » ? Pas au sens de connaissance en dur du domaine.** Les
   littéraux `book/member/loan` vivent dans `agentlib/bench/*` — les suites de
   test des prompts nommés — pas dans le générateur. Le couplage réel du
   générateur à ces corpus est **un mot** (« CRUD ») plus quelques filets de
   forme. Ce qui a été « surappris », c'est de la **formulation** : le corpus
   01–40 énonce ses opérations, ce qui masque la faiblesse du LLM à les
   *inférer*. 41–60 est le premier lot qui exige l'inférence — et c'est là que ça
   casse.

## 5. Le correctif (appliqué)

`_managed_ops_floor` (`agentlib/pipeline/cli_surface.py`) : pour une spécification
qui **n'énumère pas** sa ligne de commande (le lecteur de la porte
`cli-conformity` sert de garde), **chaque entité que le prompt nomme** gagne
`add` et `list` dès que le prompt **gère** (`manage`, `administer`, `maintain`,
`keep track of`, `track`, `record`) ou **contient** (`contain(s|ing)`,
`including`, `consist of`) quelque chose. `add`/`list` **seulement** :
`update`/`delete` ne sont jamais synthétisés ici — le mot `CRUD` littéral
continue de les produire via `_crud_floor`. Deux corrections de reconnaissance au
passage : la correspondance d'entité est **bornée au mot** (une sous-chaîne
donnait des commandes à des entités jamais nommées) et comprend les **pluriels
irréguliers** (47 écrit « people » pour `Person`).

Empreinte mesurée sur les arbres existants : `add`/`list` uniquement, aucun
`update`/`delete` ajouté nulle part.

### Effet bout-en-bout (prompts régénérés)

| prompt | avant | après | ce qui a changé |
|--------|-------|-------|-----------------|
| 42 | 2/4 | 3/4 | groupe `purchase` : `list,total` → **`add,list,total`** |
| 43 | 2/3 | **3/3** | `task add` apparaît |
| 47 | 1/3 | **3/3** | `person add`, `task add` (+ **fix de nommage**, §5bis) |
| 49 | 1/3 | **3/3** | `employee add` fonctionne |

### 5bis. Défaut de générateur trouvé en vérifiant 47

`task add` échouait avec `sqlite3.OperationalError: no such table:
main.assigned_to_users`. Cause : **deux dérivations divergentes du nom de table**.
La DDL construisait la table depuis le **nom de classe** (`AssignedToUser` →
`assignedtousers`) tandis que la clause `FOREIGN KEY` la déduisait du **nom de
colonne** (`_pluralize_table_name("assigned_to_user")` → `assigned_to_users`).
SQLite accepte une référence pendante à la création et échoue au premier INSERT
de l'enfant. Corrigé dans `agentlib/naming.py` et
`agentlib/generation/model_render.py` (on camelise d'abord la racine, donc
`project_id` → `Project` → `projects` reste inchangé).

### Ce que le correctif NE couvre pas (classes de défauts distinctes, mesurées)

- **42** : l'agrégat « combien a dépensé le client ». Le groupe `purchase` est
  créé et l'historique s'affiche, mais `customer report --id` renvoie le client
  **et la liste** de ses achats **sans le total** (`get_customer_report` ne somme
  pas). C'est du **service**, pas de la surface.
- **53, 55, 56, 60** : lignes de commande + mouvement de stock (ni `order add`
  avec produit/quantité, ni `order_item add`).
- **54** : `appointment add` n'expose aucune heure de début/fin.
- **60** : `category add` plante (`Incorrect number of bindings supplied`).
- **50** : `registration add` → `FOREIGN KEY constraint failed`.
- **57** : `document add` → `NOT NULL constraint failed: documents.file_path`.

## 6. Ce que cela implique pour l'ordre des correctifs

Le correctif n'est pas « meilleur prompt LLM » en premier : c'est **généraliser
le filet** (retirer la dépendance au mot CRUD ; pour chaque entité que le prompt
nomme, garantir les opérations que ses *comportements* exigent — création
comprise, et l'entité enfant doit être créable si le prompt dit qu'elle est
contenue). Le LLM reste la source des intentions, mais une omission ne doit plus
pouvoir atteindre le CLI.

Vérification du correctif : rejouer **42, 43, 47, 49** (celles dont l'entité
enfant n'est pas créable) plus **46, 48, 51** comme témoins conformes, puis les
6 nommés.
