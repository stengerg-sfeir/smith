# Journal de progression — corrections du générateur

Critère : un correctif n'est « acquis » que lorsque (a) le(s) prompt(s) visé(s) passent
en exécution manuelle, et (b) le protocole nommés donne 6/6 clean sans marqueur interdit.
Baseline sauvegardée : `analysis/baseline_fixes/named_prompts_report.pre_R1.{md,json}`.

## R1 — garder `ast.parse` contre un remplissage nul — code ✅

- **Fichier** : `agentlib/generation/service_render.py`
  - `_strip_import_enum_validation` : retourne l'entrée INCHANGÉE si ce n'est pas une
    `str` (`ast.parse(None)` lève `TypeError`, pas `SyntaxError`).
  - boucle de remplissage par méthode : un `_llm_fill(...)` qui rend `None` est une
    **tentative échouée** (`continue`), plus jamais transmis aux réécritures de texte.
- **Mesure prompt 18** : génération OK (259 s, 0 erreur, 17 appels). Exécution manuelle :
  - `contact add` ×2 → `contact list` → 2 contacts ;
  - `contact export --filename …` → CSV complet ;
  - `contact import` d'un CSV {1 ligne valide, 1 ligne invalide} → la valide est ajoutée
    (3 contacts), l'invalide est **rejetée avec message**
    (`Missing required field: first_name or last_name…`), les données existantes intactes.

  → **fonctionnel et conforme**.

## R2 — isolation d'un prompt défaillant — code ✅

- **Fichier** : `agentlib/bench/cmd_cost_profile.py`
  - `main()` : boucle `for ident in args.prompt` avec `try/except` par prompt ;
  - `_failed_profile(ident, exc)` : enregistrement de forme identique (toutes les clés lues
    par le résumé et le JSON), `failed: true`, `failure: "TypeError: …"`.
- **Pourquoi ici** : c'est le harnais de lot (`python3 bench.py cost --prompt …`) qui lançait
  une compréhension de liste nue (`[profile_prompt(i) for i in args.prompt]`) : un seul prompt
  en échec annulait les suivants et **aucun JSON n'était écrit**. `agentlib/pipeline/run.py:main`
  isolait déjà chaque prompt.

## R3 — dépôt orphelin (entité jamais conçue) — code ✅ (à mesurer)

- **Fichier** : `agentlib/pipeline/manifest.py` — nouvelle `_drop_orphan_repositories`
  appelée juste après `_synthesize_cli_repos`, avant le recalcul de `repo_paths`.
- **Mécanisme** : l'entité d'un dépôt est résolue depuis le nom de fichier exactement comme
  le renderer (`customer_repository` → `Customer`). Si la classe est absente de
  `entities_by_class`, le dépôt est de la sur-génération : design et entrée de manifeste
  supprimés, donc aucun fichier rendu, donc aucun import non résolu et **aucun**
  `self.customer_repo` câblé (l'en-tête de service est alimenté par les dépôts survivants).
- **Non-régression visée** : un dépôt dont l'entité EST conçue (tous les nommés) est
  intouché. Un dépôt légitimement requis par une option `--<entité>_id` a vu son modèle
  synthétisé par `_synthesize_cli_repos` **avant** → conservé.

## D1 — câblage option click ↔ paramètre — code ✅

- **Nouveau module** : `agentlib/generation/cli_wiring.py` (`fix_click_option_params`),
  appelé dans `process_prompt` (couvre single-pass **et** manifest-first).
- **Loi** : click lie les paramètres du callback **par nom** (`dest` de l'option). Une option
  `--list` exige un paramètre `list` ; le modèle écrit `list_flag` → `TypeError: cli() got an
  unexpected keyword argument 'list'` (prompt 03, single-pass).
- **Réparation** : renommage textuel précis (spans `ast.arg` + `ast.Name`, sans `ast.unparse`),
  uniquement quand l'écart est **non ambigu et de même taille** ; refus si le nom est un
  mot-clé, un `keyword.arg` ou un attribut. Vérifié : prompt 03 corrigé (`list_flag` → `list`),
  fichier toujours compilable ; no-op sur `generated/18/cli.py`.

## D2 — point d'entrée de paquet `__main__.py` — code ✅

- **Fichier** : `agentlib/generation/entrypoint.py` — `_add_package_mains` appelée en fin de
  `ensure_entry_point`.
- **Loi** : `python -m <pkg>` exécute `<pkg>/__main__.py` ; absent → « No module named
  <pkg>.__main__ » même quand `main()` est dans `__init__.py` (prompt 01).
- **Émission** : launcher à import ABSOLU (`from hello import main`) pour chaque paquet de
  premier niveau qui possède une commande click ou un `main`, sans `__main__.py` propre.
  Vérifié : `hello/__main__.py` produit ; paquet de simples helpers intouché.

## Protocole nommés — R1 (et R1+D1+D2+R3 groupés)

Le harnais `bench.py named` régénère chaque prompt dans un **sous-processus**
`agent.py --prompt <nom>` : il lit donc le code sur disque au moment où il tourne.
Les correctifs ci-dessus étant indépendants (R1 : garde nulle ; D1 : renommage de paramètre
non câblé ; D2 : ajout de `__main__.py` de paquet ; R3 : suppression de dépôt orphelin), la
passe nommés valide l'ensemble ; tout axe qui régresserait sera ré-imputé et re-mesuré seul.
## R3 — CORRECTION : la vraie cause racine (dedup du manifeste) ✅ mesuré

Le premier correctif (`_drop_orphan_repositories`) ne mordait pas, et pour une bonne raison :
`Customer` **était** conçu. Le vidage des designs (`NEUROSYM_DUMP_DESIGNS`) a donné la preuve :

```
manifest : models.py  models  order
           models.py  models  order_line          <-- LE MÊME FICHIER DEUX FOIS
           ...
           customer_repository.py  repository  customer
entity -> module modèle :
  models.py -> ['Order', 'OrderLine', 'Customer']  <-- 1er design (avec Customer)
  models.py -> ['Order', 'OrderLine']              <-- 2e design (sans Customer) ÉCRASE le 1er
```

**Cause racine** : le manifeste LLM liste `models.py` **une fois par entité** qu'il contient. Or
`model_paths` en dérive, donc `models.py` est **conçu deux fois** et **rendu deux fois** — et le
**second rendu écrase le premier**, qui portait le `Customer` rétro-propagé par
`_synthesize_cli_repos._ensure_entity`. D'où `from models import Customer` irrésoluble et
`RuntimeError: unresolved import-level errors after repair`.

**Correctif** : nouvelle `_dedupe_manifest_files(manifest)`, appelée juste après
`_validate_manifest` : une entrée par fichier (la première gagne), invariant que tout le reste du
pipeline suppose (« un fichier, une entrée »). Elle évite au passage un double appel LLM de design.

**Mesure prompt 34** : génération **OK** (112,7 s, 16 appels, 8 fichiers, 13 532 car.) —
`models.py`, `database.py`, `cli.py`, `exceptions.py`, `customer_repository.py`, `main.py`,
`order_repository.py`, `order_service.py`. Vérifié : `class Customer` rendue (models.py:43) et
table `customers` créée ; `python3 cli.py order add --customer-id 1` échoue proprement en
**`Error: FOREIGN KEY constraint failed`** (clé étrangère respectée), plus aucun crash générateur.

**Reste (hors R3)** : comme le prompt 22, l'application n'expose **aucune commande** pour créer un
client ni des lignes de commande — la règle d'atomicité « créer la commande ET ses lignes, sinon
rien » n'est donc pas exerçable. C'est un manque de **capacité métier** (palier 2/3), pas le crash
que R3 devait supprimer.

## D1 — mesure prompt 03 ✅ (crash corrigé) + défaut résiduel identifié

- `generated/03/todo_app.py` : `def cli(add: Optional[str], list, complete: Optional[int], delete: Optional[int])`
  — le paramètre est désormais le `dest` de l'option, et `list_flag` a **disparu** du fichier.
- **Défaut résiduel (nouveau, distinct du crash)** : l'option est déclarée
  `@click.option('--add', '-a', prompt='Task to add', …)`. Click **réclame donc une saisie
  interactive dès que `--add` est omis**, même pour `python3 todo_app.py --list` : la commande
  `list` devient inutilisable en mode non interactif. C'est du code LLM single-pass ; à traiter
  comme une micro-loi séparée (retirer `prompt=` d'une option dont le corps tolère `None`), avec
  protocole nommés complet.

## D2 — mesure prompt 01 ✅

- `generated/01/hello/__main__.py` est émis, et `python3 -m hello` (depuis `generated/01`)
  imprime **`Hello, World!`**. Le prompt 01 passe désormais de « ~ » (échec `python -m`) à
  fonctionnel.
## W2 — pagination jusqu'au dépôt ✅ mesuré (prompt 16)

**Défaut de baseline** : `--page`/`--page-size` acceptés mais **sans effet** (page 1 et
page 2 renvoyaient tout), et **aucun total** — donc pas de nombre de pages. Le corps du
service était en plus un remplissage LLM absurde (`with open(page_size, "w")` : il ouvrait
un CSV **nommé d'après `page_size`**) et ne retournait rien.

**Cause racine, en deux moitiés :**

1. **Dépôt** — le `list()` déterministe n'acceptait QUE les `list_filters` déclarés :
   `page`/`page_size` n'y figuraient pas, donc aucune pagination SQL n'était possible.
2. **Service** — `list_customer` portait un `impl` de forme *export*, et
   `_service_method_body` dispatchait l'`impl` **avant** la délégation de listing : la
   méthode ne parvenait jamais à la branche `list_<entity>`.

**Correctif (3 pièces, toutes déterministes) :**

- `service_render._apply_pagination_floors` (nouveau, appelé depuis `manifest.py` juste
  après `_apply_filter_floors`) : un `list_<entité>(..., page, page_size)` **conçu** marque
  son entité (`ent["page_filters"]`) — la marque est **par entité**, résolue sur le nom de
  méthode, jamais étalée à toutes les entités.
- `repo_render` : `list()` reçoit `page`/`page_size` (`Optional[int] = None`) et pagine sa
  SQL — `LIMIT ? OFFSET ?` **après** le `ORDER BY` (l'ordre est obligatoire : un `LIMIT`
  placé avant `ORDER BY` est invalide).
- `service_render` : branche `list_<entité>` → enveloppe `{items, page, page_size, total,
  total_pages}` ; le `total` est lu sur le `list()` **non paginé** de la conception (aucune
  requête inventée). Une **priorité explicite** fait passer une liste paginée avant tout
  `impl` (forme exacte : `list_` + un paramètre de numéro de page + un de taille de page).

**Mesure prompt 16** (régénéré, 177,9 s) :
- `customer_repository.list(...)` expose `page`/`page_size` et émet `LIMIT ? OFFSET ?` ;
- `customer_service.list_customer(...)` retourne l'enveloppe ;
- exécution : 5 clients ajoutés, puis
  `list --page-size 2` → **C1, C2** (`page: 1`, `total: 5`, `total_pages: 3`) ;
  `list --page-size 2 --page 2` → **C3, C4** ;
  `list --page-size 2 --page 3` → **C5** seul.
  → « renvoie les éléments demandés ET de quoi déterminer le nombre total de pages » :
  **satisfait**.
## W3 — recherche et filtre de domaine ✅ mesuré (prompts 07 et 12)

### 07 — « search » : `impl` export acceptée à tort (garde par sous-chaîne)

`search_book(term)` était rendu en **export CSV** : `open(term, "w")` — il ouvrait un fichier
**nommé d'après le terme cherché**, ignorait la requête `search_book(term)` du dépôt et ne
retournait rien. Le vidage des designs a donné l'`impl` exact que la conception avait posé :

```
services  search_book  impl={'kind': 'export_csv', 'entity': 'book', 'file_param': 'term'}
                       params=['term']  ret=List[Dict[str, Any]]
```

**Cause racine** : la garde qui doit refuser un export sur une méthode NON-export testait
`"str" not in returns`. Or `returns = "List[Dict[str, Any]]"` **contient la sous-chaîne
`str`** — dans l'argument de `Dict[str, ...]` ! Le test était donc toujours satisfait pour
n'importe quel conteneur d'éléments `str`, et l'export était accepté. Le corps exportait un
CSV dont le nom de fichier était le terme de recherche.

**Correctif** (`agentlib/kernel/service/common.py:_impl_bindings_ok`) : normaliser
l'annotation (`"".join(returns.split()).lower()`) puis juger la forme EXTÉRIEURE — un retour
conteneur (`list/dict/tuple/set`) n'est **jamais** un export ; sinon il doit nommer `str` ou
`path`. L'export légitime (retour `None`) est intouché.

**Mesure** : `search_book(term)` rend `return self.book_repo.search_book(term)` ; ajout de
« The Ring » (Tolkien) puis `book search --term Ring` → la ligne est retournée (avant : crash
+ CSV parasite).

### 12 — filtre `--email-domain` en ÉGALITÉ au lieu d'un LIKE

`email_domain` était déclaré `op: eq` sur la colonne `email` **par la conception elle-même** :
la clause rendue était `AND email = ?` — comparer une adresse entière à un domaine ne
correspond jamais, donc le filtre renvoyait toujours vide.

**Correctif (2 pièces)** :
- `service_render._apply_filter_floors` : toute spec dont le **paramètre** finit par
  `_domain` et dont la **colonne de base** est un champ `str` de l'entité est **réécrite en
  place** (`column = base`, `op = "like_domain"`) — qu'elle ait été déclarée par la conception
  ou seulement présente dans une signature de méthode. La vérification porte sur le champ réel,
  donc un `domain` sans rapport n'est jamais capturé.
- `repo_render` : nouvel op `like_domain` → fragment ` AND <col> LIKE ?`, avec une **expression
  de liaison** dédiée (`"%" + str(<param>)`) : un domaine correspond à la FIN de la valeur, ni
  l'égalité (jamais de correspondance) ni un LIKE non ancré (correspondance au milieu d'un
  domaine plus long).

**Mesure** : `email_domain` rend ` AND email LIKE ?` lié à `"%" + str(email_domain)`.
Exécution : 3 clients (`example.com` ×2, `other.org` ×1) puis
`list --email-domain example.com` → **Alice + Bob** ; `--email-domain other.org` → **Carol** ;
`customer search --term Alice` → **Alice**. Filtre discriminant et recherche fonctionnelle.
## W1 — tri paramétré, bout en bout ✅ mesuré (prompt 15)

**Défaut de baseline** : « pas de tri : options `--name/--price/--quantity` = filtres, `ORDER BY id`
toujours ». Le design avait pris les colonnes de tri pour des **filtres d'égalité** et inventé une
commande `sort_product(id)` absurde : aucun `sort_by`/`order` n'existait nulle part.

**Correctif — 4 pièces, chacune traversant une couche :**

1. **Surface CLI** (`pipeline/cli_surface.py`) : un spéc qui demande un listage ORDONNÉ est détecté
   de façon déterministe, par deux signaux seulement — un verbe de tri (« sorted by » / « order by »)
   ou un mot de DIRECTION (« ascending/descending », qui ne se dit que d'un ordre). La commande
   `list` de l'entité gagne alors `--sort-by` et `--order` (`_prompt_sort_fields` propose les
   colonnes que le prompt NOMME, intersectées avec les champs scalaires réels de l'entité, sinon
   tous — une commande de tri sans colonne étant exactement le défaut).
2. **Service** (`generation/service_render.py`) : `_apply_sort_floors` marque l'entité
   (`sort_params`, `sort_fields`) quand une méthode conçue `list_<entité>` porte un sélecteur de
   colonne ET un sélecteur de direction — la marque est par entité, résolue sur le NOM de la méthode.
   La branche de listing retire ces deux paramètres de l'appariement des filtres (sinon ils
   redevenaient des égalités) et les transmet à `list()` comme arguments nommés.
3. **Dépôt** (`generation/repo_render.py`) : `list()` accepte les deux paramètres et construit
   `ORDER BY <colonne> <direction>` — la colonne est **résolue par liste blanche** issue des champs
   scalaires de l'entité (`sortable.get(sort_by, 'id')`), donc une colonne fournie par l'appelant ne
   peut jamais atteindre le texte SQL, et `LIMIT/OFFSET` (pagination) reste APRÈS l'`ORDER BY`.
4. **Câblage** (`pipeline/manifest.py`) : `_apply_sort_floors` est appelé juste après
   `_apply_pagination_floors`, sur le même passage qui applique les planchers.

**Mesure prompt 15** (régénéré, 139,7 s) — le flux complet est correct :
- CLI : `product_list(name, price, quantity, sort_by, order)` → `svc.list_product(..., sort_by=…, order=…)` ;
- service : `list_product(..., sort_by, order)` → `self.product_repo.list(..., sort_by=…, order=…)` ;
- dépôt : `sortable = {'name','price','quantity'}`, `column = sortable.get(sort_by, 'id')`,
  `order = ' ORDER BY ' + column + ' ' + ('DESC' if … else 'ASC')` ;
- exécution (Zebra 30 / Apple 10 / Mango 20) :
  `--sort-by price --order asc` → **Apple, Mango, Zebra** ;
  `--sort-by price --order desc` → **Zebra, Mango, Apple**.
  → « lister les produits triés par nom, prix ou quantité, en ordre croissant ou décroissant » :
  **satisfait**.
## A2 (Palier 2) — le rapport porte aussi le NOMBRE ✅ mesuré (prompt 20)

**Défaut de baseline** : « rapport = montant par produit (`{1: 50.0}`) ; **le nombre de ventes
n'apparaît pas** ». Le spéc demande « un rapport montrant le montant total des ventes **et le
nombre** de ventes par produit » : un scalaire par groupe ne peut répondre qu'à une des deux
moitiés.

**Correctif (2 pièces) :**

1. `generation/service_render._apply_report_count_floors` (nouveau, appelé depuis `manifest.py`
   avec `prompt_text`) : détecte la demande par **clause** — une phrase qui porte à la fois un mot
   de somme (`total`/`sum`/`amount`) et un mot de compte (`number of`/`count of`/`how many`/
   `how often`). Un total ici et un inventaire là ne forment PAS ce contrat, d'où le balayage
   strictement phrase par phrase. Quand la clause matche, la marque `also_count` est posée sur
   l'`impl` **`sum_by_group`** que la conception a déjà produite : la recette qui le rend s'étend
   **en place**, rien n'est inventé et aucun rapport purement sommant n'est touché.
2. `kernel/service/sum_by_group._h_sum_by_group` : sous `also_count`, chaque groupe devient une
   **paire** — `{"total": <somme>, "count": <nombre de lignes agrégées>}`. Le compte est le nombre
   de lignes que le regroupement a repliées, **jamais une colonne stockée** lue pour l'occasion.

**Mesure prompt 20** (régénéré, 197,6 s) :
- `get_sale_report` rend `entry = {"total": 0, "count": 0}` puis `entry["total"] += row.total_amount`
  et `entry["count"] += 1` ;
- exécution : produits A/B, ventes (P1 ×2 = 20+30, P2 ×1 = 20) →
  `sale report --id 1` → **`{1: {'total': 50.0, 'count': 2}, 2: {'total': 20.0, 'count': 1}}`**
  — le montant ET le nombre, par produit.
  → « montant total des ventes **et** nombre de ventes par produit » : **satisfait**.

**Défaut résiduel (hors A2)** : `sale report` exige un `--id` sans objet (« `sale/report --id
[required]` ») et le corps l'ignore — la même classe de défaut que le `sort_product(id)` du
prompt 15 : un paramètre **inventé** sur une méthode sans clé. À traiter comme loi séparée
(paramètre d'entrée non dérivable ⇒ ne pas l'exiger).
## A1 (Palier 2) — un total DÉRIVÉ des lignes n'est pas une entrée ✅ mesuré (prompts 22 et 28)

**Défaut de baseline** : l'application **réclame** un total qu'elle est censée calculer —
`invoice add --total-amount TEXT [required]` (28) ; et la capacité de calcul elle-même était
**inatteignable** : la recette `sum_children` existait dans le noyau mais **rien ne générait son
`impl`**, donc aucune méthode ne calculait jamais le total.

**Loi (deux moitiés, toutes deux pilotées par la conception) :**

1. **Interdire l'entrée** — `service_render._apply_derived_total_floors` DÉTECTE qu'un total est
   dérivable, en structure : l'entité E porte **un** champ dont le NOM dit « total »
   (`total`/`subtotal` — le TYPE est délibérément ignoré, la conception type un montant `str`
   aussi souvent que `float`), et il existe **une** entité de lignes C qui la référence par FK et
   porte soit **deux** numériques (quantité + prix — `OrderItem.quantity/unit_price`, prompt 22),
   soit **un** numérique (la quantité) plus une FK vers une entité qui porte le prix
   (`InvoiceLine.quantity` → `Product.price`, prompt 28). La demande est par ailleurs
   **conditionnée au texte** : le spéc doit dire que le total est
   *calculé/dérivé/computé* (`_DERIVED_TOTAL_RE`) — un dépôt qui se contente de STOCKER un total
   (la valeur de stock d'inventory) n'est jamais capturé.
   → `derived_fields` posé sur l'entité ; `derive_cli_surface._derive_options` l'omet pour
   add/update ; **et** `manifest._apply_derived_total_surface` filtre la surface FINALE, car un
   spéc qui ÉNUMÈRE sa CLI (`build_prompt_cli_surface`) ne passe jamais par le chemin dérivé —
   c'est précisément ce qui laissait 28 exiger `--total-amount` après le premier correctif.

2. **Rendre le calcul atteignable** — `_ensure_derived_total_methods` pose (ou réutilise en place)
   `calculate_<entité>_total(<pk>)` avec un `impl` `sum_children` ; la recette
   (`kernel/service/sum_children`) somme `quantité × prix` des lignes, et — quand le prix vit sur
   l'entité référencée — le lit par SA propre `get_by_id` (`price_via`), une ligne absente
   contribuant 0 plutôt que d'interrompre le total.

**Mesures** (les deux régénérées) :

- **22** — `order add` n'expose plus que `--customer-name` ; `order report --id 1` →
  **`40.0`** (3×10 + 2×5). Total **calculé** à partir des lignes.
- **28** — `invoice add` n'expose plus que `--customer-id` ; `invoice calculate-total --id 1` →
  **`35.0`** (3×7 + 2×7). Le total n'est **plus une entrée**, et le calcul est exerçable.

→ « le total n'est pas un champ fourni par l'appelant » **et** « il est calculé à partir de ses
lignes » : **satisfait** sur les deux prompts visés.

**Portes déterministes après A1** : surface **0/3**, cli-conformity **0/3**, repo-conformity
**0/3**, sémantique `library_system` **15/15**, `expenses` **16/16** — `ALL SEMANTIC CHECKS PASS`.

**Bug trouvé au passage (corrigé)** : dans `_line_child_spec`, le filtre des champs numériques
n'excluait que les noms finissant par `_id` — la clé primaire `id` (qui ne finit PAS par `_id`)
était donc comptée, et une ligne à un seul numérique produisait `value_field='id'`
(total = Σ `id` × prix : un nombre dénué de sens). `id` est désormais exclu des deux côtés.

**Risque nommés** : A1 modifie la surface CLI et le service, donc le protocole nommés est
re-mesuré avant toute déclaration d'acquisition (passe 8).
## C6 (Palier 3) — validations de champs énoncées par le prompt ✅ fonctionnel (prompt 09)

**Défaut de baseline** : « **aucune validation** : email invalide, âge 17/71, salaire négatif
tous acceptés ». Le spéc énonce pourtant le domaine de chaque champ en prose — « The email must
be valid, age must be between 18 and 70, and salary must be positive » — et rien ne l'appliquait.

**Correctif (2 nouveaux modules + 1 câblage, tous déterministes) :**

1. `pipeline/field_rules.py` — `extract_field_rules(prompt_text, entities_by_class)` lit les
   phrases du spéc : `_RANGE_RE` (« must be between A and B » / « from A to B »),
   `_POSITIVE_RE` (« must be positive / greater than 0 »), `_VALID_RE` (un champ `*email*`
   « must be (a) valid »). Chaque règle est **reliée à un champ réellement conçu** : une phrase
   sur une colonne que le modèle n'a pas est ignorée, jamais inventée en code.
2. `generation/field_guard.py` — rend chaque règle en **gardes** et les **épisse en tête** du
   corps `add_<entité>` / `create_<entité>` / `update_<entité>`. L'insertion est dirigée par
   l'AST (jamais `ast.unparse`) : le squelette, le remplissage et l'indentation de la méthode
   restent intacts octet pour octet, et une ligne-marqueur rend l'opération idempotente.
3. `pipeline/manifest.py` — les règles sont extraites une fois (étape 2.4) et appliquées au
   service rendu (étape 5.2b).

**Pourquoi épisser plutôt que rendre dans la recette de création** : le corps d'un `add_` est
produit par plusieurs étages (dispatch d'`impl`, délégation générique, remplissage LLM) ; une
règle doit tenir quel que soit l'étage, et l'épissure à la première instruction les couvre tous.

**Trois bugs trouvés et corrigés pendant la mise au point (chacun mesuré) :**

- **Clé de classe** : les règles sont indexées par l'ENTITÉ (`Employee`) alors que le service
  s'appelle `EmployeeService` — la recherche ne mordait pas. On retire le suffixe `Service`, et
  c'est l'ENTITÉ qui est passée à l'épissure (la garde vise `add_employee`, pas
  `add_employee_service`).
- **Descente dans la classe** : le service rendu est une CLASSE ; `_method_named` ne balayait que
  les fonctions de niveau module → aucune méthode trouvée. Il descend désormais dans les corps
  de classe.
- **Champ numérique typé `str`** : le design déclare `salary: str` (le CLI récolte du TEXT), donc
  un `salary <= 0` nu levait `TypeError: '<=' not supported between 'str' and 'int'` — une trace
  au lieu d'un refus. Toute garde numérique passe maintenant par `float()` dans un `try`, et une
  valeur non numérique est un refus comme un autre.

**Exception choisie par champ** : la conception déclare `InvalidEmailError`,
`AgeOutOfRangeError` et `NegativeSalaryError` ; chaque règle préfère l'exception déclarée qui
nomme SON champ, sinon les noms génériques, sinon `ValueError` — un refus ne porte donc jamais
le nom d'un autre champ.

**Mesure prompt 09** (régénéré, 133,9 s) — l'exécution manuelle est concluante :

| cas | résultat |
|-----|----------|
| email invalide (`nope`) | `Error: email must be a valid email address` |
| âge 17 | `Error: age must be between 18 and 70` |
| âge 71 | `Error: age must be between 18 and 70` |
| salaire −5 | `Error: salary must be positive` |
| valide (d@x.com, 30, 100) | accepté → `list` renvoie `Employee(name='D', …, id=1)` |

→ « email valide, âge entre 18 et 70, salaire positif » : **satisfait**, avec des refus propres
(pas de trace) et l'acceptation des données valides.

**Protocole nommés — mesuré, en deux passes.**

*Cible attendue : nulle.* Aucun prompt nommé ne porte de domaine de champ (`grep` sur
`agentlib/bench/named_prompt_suite.py` : aucun « must be positive/valid/between »), et parmi les
40 prompts numérotés **seul `prompt_09`** en contient ; de plus `apply_field_guards` n'est même pas
appelée quand aucune règle n'existe, donc le chemin est **littéralement inchangé** pour tout autre
prompt.

- **Passe 1 : 5/6.** L'unique échec est un **marqueur de remplissage du DÉPÔT** de
  `library_system` — `[fill] repository: kept 0/1 customs; reverted list_authors_with_books
  (SQL outside designed schema)` — sur un prompt sans aucun domaine de champ. C6 n'édite que le
  fichier de **service** : il ne peut pas produire un marqueur de **dépôt**. Les cinq autres
  prompts sont propres, et `library_system` lui-même est PASS sur `compile`, `fonctionnel` et
  `conforme`.
- **Passe 2 (`--only library_system`) : 6/6 clean**, `markers=0`.

→ La défaillance était **intermittente**, de la même famille que celle déjà consignée au baseline
(« l'échec est dépendant du run, pas systématique »). **C6 est acquis.**

**Observation sur le critère (à l'attention du lecteur)** : ce marqueur n'est pas un défaut du
code produit — c'est l'**avis de réparation du générateur lui-même** (« j'ai retiré une méthode
de dépôt dont la SQL sortait du schéma conçu »). Le protocole le compte pourtant comme « marqueur
interdit », donc une passe où la conception LLM propose une requête hors schéma échoue **alors
même que le générateur a bien fait son travail**. C'est une source structurelle de faux négatifs,
indépendante des correctifs en cours ; à traiter comme sa propre loi (faire que la conception
écarte en amont la méthode infaisable, au lieu de la réparer au remplissage) si la gêne se
reproduit.

**Écart au plan** : le plan plaçait C6 dans `pipeline/method_contract` (« effet
`field_validation` »). L'effet est ici obtenu par un module dédié + une épissure post-rendu, qui
couvre les trois étages de création sans toucher au contrat de méthode — même comportement,
moins de couplage.

**Note de méthode (erreur de ma part, corrigée)** : un premier test fonctionnel a été lancé
**avant** que la régénération soit terminée, donc contre les artefacts de la passe précédente
(encore porteurs du bug `salary <= 0`) ; d'où une trace trompeuse. Règle retenue : ne jamais
tester `generated/<id>` avant que le log de génération porte sa ligne `=== summary ===`.
## C1 (Palier 3) — delta numérique sur un champ, avec refus du découvert ✅ fonctionnel (prompt 31)

**Défaut de baseline — l'opération était INEXÉCUTABLE.** Le spéc dit « Deposits increase the
balance and withdrawals decrease it. A withdrawal must be rejected if it would make the balance
negative. » Or :

- la surface ne portait **aucun montant** : `account deposit --id INT [required]` et
  `account withdraw --id INT [required]`, si bien que `--amount` répondait
  `Error: No such option '--amount'` ;
- le service était un remplissage inerte : `withdraw_account(self, id: int)` (le paramètre
  `amount` avait **disparu**) et son corps levait inconditionnellement
  `ValidationError('Withdrawal amount is required but not provided')`.

Dépôt comme retrait étaient donc impossibles, et la garde de découvert inatteignable.

**Correctif — 4 pièces, toutes déterministes et pilotées par le seul spéc :**

1. `pipeline/amount_rules.py` (nouveau) — `extract_amount_ops(prompt_text, entities_by_class)`
   lit la phrase du spéc : `<nom> increase/decrease the <champ>` donne l'OPÉRATION (le nom,
   ramené à sa racine verbale : « withdrawals » → `withdraw`), le SENS (le signe) et le CHAMP
   (relié à une colonne **numérique** réellement conçue ; « it » reprend le champ de la
   proposition précédente). Une seconde lecture prend la phrase de refus
   (« must be rejected if it would make X negative ») et marque l'opération DÉCROISSANTE
   correspondante.
2. `manifest._apply_amount_op_surface` — ajoute `--amount` (requis, entier) à la commande de
   cette opération, appliqué à la surface **FINALE** (donc aussi bien au chemin dérivé qu'à un
   spéc qui énumère sa CLI).
3. `manifest._ensure_amount_op_methods` — attache au service l'`impl` `contract_effects` portant
   un effet `amount_delta`, et s'assure que la méthode accepte le paramètre `amount`.
4. `kernel/service/contract_effects._field_expr` + `_non_negative_guard` — rendent l'effet :
   `balance = (row.balance or 0) ± float(amount)`, et, pour l'opération décroissante qui a
   déclaré le refus, la garde `if (row.balance or 0) < float(amount): raise <Exc>` **avant**
   l'écriture (rien n'est écrit si l'opération passerait sous zéro).

**Le discriminant (c'est lui qui protège les nommés).** Le même tour de phrase existe dans le
prompt **nommé** `inventory` : « restock(id, qty): **increases** a product's stock_qty », qui
expose déjà `product restock --id --qty`. Une règle naïve aurait ajouté un second montant et
cassé une surface qui marche. Un montant implicite n'est donc synthétisé **que lorsque le spéc
ne nomme pas déjà de paramètre pour cette opération** (`restock(id, qty)` en nomme deux ;
`deposit`/`withdraw` du prompt 31 n'apparaissent dans aucune signature). Vérifié en isolation
avant tout câblage :
`31 → {'Account': {'field': 'balance', 'ops': [deposit(+1), withdraw(−1, non_negative=True)]}}`
et `inventory → {}`.

**Mesure prompt 31** (régénéré, 212,2 s) :

| étape | résultat |
|-------|----------|
| surface | `account deposit --id --amount` et `account withdraw --id --amount`, tous deux `[required]` |
| service | `deposit_account(id, amount)` → `balance + float(amount)` ; `withdraw_account(id, amount)` → garde puis `balance − float(amount)` |
| compte à 100 → dépôt 50 | `True` |
| → retrait 30 | `True` |
| → retrait 500 | **`Error: balance would become negative`** (refusé) |
| solde final | **120.0** = 100 + 50 − 30 |

→ « les dépôts augmentent le solde et les retraits le diminuent » et « un retrait doit être
refusé s'il rendait le solde négatif » : **satisfait**, et le solde observé est exactement la
somme des opérations acceptées.

**Exception choisie** : la conception déclare `InsufficientFundsError` ; le rendu cherche le nom
déclaré qui mentionne la règle (`insufficient`/`fund`/`balance`/`negative`), puis les noms de
validation génériques, puis `ValueError` — c'est `InsufficientFundsError` qui est levée.

**Note de méthode** : la règle a été écrite en ramenant les deux orthographes à une seule racine
(« deposits »→`deposit`, « withdrawals »→`withdraw`) ; sans cela la phrase de refus
(« withdrawal ») ne retrouvait pas sa propre opération et la garde restait inerte — bug vu en
isolation, corrigé avant le câblage.

**Portes déterministes et protocole nommés** : lancés après ce correctif (le risque nommés est
concentré sur `inventory`, dont le tour de phrase est le plus proche).
## C2 (Palier 3) — transitions d'état explicites, avec refus des mouvements interdits ✅ fonctionnel (prompt 32)

**Défaut de baseline — seule la moitié IDEMPOTENTE était là.** Le spéc dit « An order starts in
the `pending` state and can become `confirmed`, `shipped` or `cancelled`. A cancelled order cannot
be shipped, and a shipped order cannot be cancelled. Implement the allowed state transitions
explicitly. » Le code livré portait bien trois opérations qui POSENT l'état, et chacune refusait le
**répétition** (« `if row.status == 'shipped': return False` ») — mais :

- `ship_order` ne regardait **jamais** `cancelled` ;
- `cancel_order` ne regardait **jamais** `shipped`.

Les deux mouvements que le spéc interdit étaient donc exécutés sans broncher. Un garde de
répétition n'est pas un garde de transition.

**Correctif — 2 nouveaux modules + 1 câblage, tous déterministes :**

1. `pipeline/state_rules.py` (nouveau) — `extract_state_rules(prompt_text, entities_by_class)` lit
   la machine à états du spéc : les ÉTATS sont les mots que le spéc écrit **entre accents graves**
   (sa convention pour une valeur littérale), l'état INITIAL vient de « starts in the `X` state »,
   et les TRANSITIONS INTERDITES de la tournure « a `<from>` <mot> cannot be `<to>` ». Chaque
   classe servie doit nommer l'entité dans le prompt **et** porter une colonne d'état réelle
   (`status`/`state`, de type `str`). Une transition citant un mot que le spéc n'a jamais déclaré
   comme état est écartée plutôt que rendue.
2. `generation/state_guard.py` (nouveau) — `apply_state_guards` **épisse** la garde dans la méthode
   d'opération. Deux points de correction délibérés :
   - l'opération qui MÈNE à un état est trouvée par les **noms de méthodes** eux-mêmes
     (`ship_order` mène à `shipped` parce que `ship` est un préfixe de l'état cible ; le préfixe le
     plus long gagne), donc aucune connaissance de la surface CLI n'est nécessaire ;
   - l'ancrage est **après** le chargement de la ligne ET **après** le garde `if row is None:` quand
     il suit — sans quoi une ligne absente lèverait `AttributeError` sur `row.status` au lieu de
     l'erreur « introuvable » déclarée par la conception. (Bug vu en isolation avant câblage.)
3. `pipeline/manifest.py` — les règles sont extraites une fois (étape 2.4) et appliquées au service
   rendu (étape 5.2c), **en chaînant depuis le fichier tel qu'il est** pour ne jamais écraser une
   injection antérieure sur le même service.

**Exception choisie** : la conception déclare `InvalidStateTransitionError` ; le rendu cherche le nom
déclaré qui décrit la machine à états (`state`/`transition`/`status`/`invalid`), puis les noms de
validation génériques, puis `ValueError` — c'est bien `InvalidStateTransitionError` qui est levée, et
le message reprend la phrase du spéc (« a shipped order cannot be cancelled »).

**Mesure prompt 32** (régénéré, 133,4 s) — le graphe d'états complet est correct :

| étape | résultat |
|-------|----------|
| commande 1 à `pending` → `ship` | `True` |
| → `cancel` | **`Error: a shipped order cannot be cancelled`** (refusé) |
| commande 2 à `pending` → `cancel` | `True` |
| → `ship` | **`Error: a cancelled order cannot be shipped`** (refusé) |
| commande 3 → `confirm` | `True` |

→ « un ordre annulé ne peut pas être expédié » et « un ordre expédié ne peut pas être annulé » :
**satisfaits**, et les transitions légales restent exécutables.

**Risque nommés : nul, mesuré par lecture.** La règle exige des états **entre accents graves** ; or
`grep -rlE '`[a-z_]+`'` sur les six prompts nommés ne renvoie **rien** — aucun prompt nommé n'écrit
de valeur littérale de cette façon, donc la règle ne peut pas s'y déclencher. Parmi les 40 prompts
numérotés, seuls 32 et 36 contiennent « cannot be », et 36 (garde référentielle sur suppression,
C5) est d'une autre forme. Le protocole nommés est tout de même relancé pour satisfaire le critère.

**Note de méthode** : les deux modules ont d'abord été écrits à la racine du dépôt (l'outil
d'écriture a tronqué le chemin) puis déplacés à leur emplacement réel — vérifié par `py_compile`
et par l'import depuis `agentlib`.
## C3 (Palier 3) — chevauchement de plages sur une ressource ✅ fonctionnel (prompt 27)

**Défaut de baseline** : le spéc dit « A room cannot have two overlapping reservations. …
reject reservations that overlap an existing reservation. » Or le `create` du dépôt INSÉRAIT la
ligne sans condition : deux réservations de la même salle sur les mêmes nuits étaient acceptées
toutes les deux. La règle n'existait nulle part.

**Correctif — 2 nouveaux modules + 1 câblage, tous déterministes :**

1. `pipeline/overlap_rules.py` (nouveau) — `extract_overlap_rules` lit la tournure « a <ressource>
   cannot have two overlapping <éléments> » (le singulier est rétabli : « reservations » →
   `Reservation`). La règle n'est retenue que si l'entité est CONÇUE, porte **deux** colonnes de
   type `date`/`datetime` (résolues comme la paire début/fin : indices `start`/`end` d'abord,
   sinon exactement deux colonnes de date — tout autre compte décline, car une colonne devinée
   refuserait des réservations valides) **et** une clé étrangère vers la ressource nommée.
2. `generation/overlap_guard.py` (nouveau) — rend la règle des deux côtés :
   - le **dépôt** gagne `has_overlapping_<item>(<fk>, <début>, <fin>)`, un simple test
     d'existence SQL de la forme déjà utilisée partout (`with self.db.connect() as conn:`) :
     `SELECT 1 FROM <table> WHERE <fk> = ? AND <début> < ? AND <fin> > ? LIMIT 1`. Le nom de
     table est **relu dans le dépôt rendu** (sa propre clause `FROM`) plutôt que re-dérivé — le
     renderer fait autorité sur la table qu'il interroge ;
   - le **service** refuse AVANT d'insérer, avec les **noms de paramètres de la méthode** (reliés
     aux noms de champs du modèle). Si un nom ne correspond pas, la garde est abandonnée au lieu
     d'être inventée : appeler le test avec le mauvais argument vérifierait silencieusement la
     mauvaise colonne.
3. `pipeline/manifest.py` — règles extraites une fois (étape 2.4), appliquées au dépôt ET au
   service (étape 5.2d). L'application est placée **après** l'adoption des réparations de dépôt
   du même passage, sinon la source adoptée (antérieure à l'édition) écraserait le test ajouté.

**Sémantique d'intervalle (délibérée)** : la borne est **semi-ouverte** — une réservation qui
commence le jour où la précédente finit n'est PAS un chevauchement (`<` et `>` stricts, jamais
`<=`/`>=`), ce que le spéc demande implicitement (« two overlapping reservations » et non « deux
séjours qui se touchent »).

**Mesure prompt 27** (régénéré, 344,9 s) — les quatre cas discriminants sont corrects :

| cas | résultat |
|-----|----------|
| R1 salle 1, 01-01 → 01-05 | créée (`1`) |
| R2 salle 1, 01-03 → 01-07 (**chevauche R1**) | **`Error: the room already has an overlapping reservation`** |
| R3 salle 1, 01-05 → 01-08 (**adjacente**) | créée (`2`) — se toucher n'est pas chevaucher |
| R4 salle 2, 01-03 → 01-07 (même fenêtre, **autre salle**) | créée (`3`) |

→ « une salle ne peut pas avoir deux réservations qui se chevauchent » : **satisfait**, et le test
reste discriminant (il ne refuse ni l'adjacence ni une autre ressource).

**Exception choisie** : la conception déclare `OverlapException` ; le rendu cherche le nom déclaré
qui décrit ce refus (`overlap`/`conflict`/`unavailable`/`already`), puis les noms de validation
génériques, puis `ValueError` — c'est bien `OverlapException` qui est levée.

**Risque nommés : nul, mesuré par lecture.** La règle exige la tournure « cannot have two
overlapping » ; or `grep -rln overlapping prompts/` ne renvoie que `prompt_27.txt`, et aucun des
six prompts nommés ne la contient. Le plan signalait un risque (« dates expenses/library ») parce
que la règle touche des colonnes de date ; la tournure exigée le lève. Protocole nommés relancé
quand même, pour satisfaire le critère.
## C4 (Palier 3) — « au plus un actif » par ressource ✅ fonctionnel (prompt 26)

**Défaut de baseline** : le spéc dit « a book can have at most one active loan ». Or rien ne
l'appliquait : `loan add` insérait la ligne sans condition, donc un livre pouvait être emprunté
deux fois en même temps.

**Correctif — 2 nouveaux modules + 1 câblage, tous déterministes (même forme que C3) :**

1. `pipeline/active_rules.py` (nouveau) — `extract_active_rules` lit « a <ressource> can have at
   most one active <élément> » (singulier rétabli). La règle n'est retenue que si l'élément est
   CONÇU, porte une clé étrangère vers la ressource **et** un drapeau d'activité résoluble : une
   colonne `bool` dont le nom dit « active/open/current » (`is_active` du modèle `Loan`), ou —
   seulement si c'est le SEUL booléen de l'entité — ce booléen unique. Un second booléen
   (« is_returned ») signifierait l'inverse : mieux vaut décliner que garder la mauvaise colonne.
2. `generation/active_guard.py` (nouveau) — le dépôt gagne
   `has_active_<item>(<fk>)` → `SELECT 1 FROM <table> WHERE <fk> = ? AND <flag> = 1 LIMIT 1` (le
   nom de table est relu dans la clause `FROM` du dépôt rendu), et le service refuse AVANT
   d'insérer, avec les noms de paramètres réels. Les assistants d'insertion de classe et de
   résolution d'arguments sont **partagés avec `overlap_guard`** plutôt que dupliqués.
3. `pipeline/manifest.py` — règles extraites une fois (étape 2.4), appliquées dépôt + service
   (étape 5.2e), au même endroit (après l'adoption des réparations de dépôt) et en chaînant depuis
   le fichier tel qu'il est.

**Mesure prompt 26** (régénéré, 171,7 s) — l'invariant tient dans les deux sens :

| étape | résultat |
|-------|----------|
| prêt 1, livre 1 | créé (`1`) |
| prêt 2, livre 1 | **`Error: the book already has an active loan`** (refusé) |
| clôture du prêt 1 | `True` |
| prêt 3, livre 1 après clôture | créé (`2`) |

→ « un livre n'a qu'un seul prêt actif à la fois » : **satisfait**, et la clôture LIBÈRE bien le
livre (la garde ne bloque pas après coup, elle ne regarde que les prêts actifs).

**Exception choisie** : la conception déclare `BookAlreadyBorrowedException` ; le rendu cherche le
nom déclaré qui décrit ce refus (`active`/`already`/`borrow`/`unavailable`), puis les noms de
validation génériques, puis `ValueError`.

**Risque nommés : nul, mesuré par lecture.** `grep -rln "at most one" prompts/` ne renvoie que
`prompt_26.txt` — aucun prompt nommé ne porte la tournure. Protocole nommés relancé pour le critère.
## C5 (Palier 3) — garde référentielle au DELETE ✅ fonctionnel (prompt 36)

**Défaut de baseline** : le spéc dit « A category cannot be deleted while products still belong to
it. » Or `category delete` supprimait la ligne sans condition : la catégorie disparaissait et ses
produits restaient pointés sur une catégorie inexistante.

**Correctif — 2 nouveaux modules + 1 câblage, tous déterministes :**

1. `pipeline/reference_rules.py` (nouveau) — `extract_reference_rules` lit « a <ressource> cannot
   be deleted while <éléments> still belong to it ». La règle n'est retenue que si les DEUX classes
   sont conçues et que l'élément porte une clé étrangère réelle vers la ressource.
2. `generation/reference_guard.py` (nouveau) — **asymétrie délibérée** : la méthode
   `has_<items>(<fk>)` est posée sur le dépôt de la RESSOURCE (c'est SA suppression qu'on garde)
   mais interroge la table des ÉLÉMENTS, dont le nom est relu dans la clause `FROM` du dépôt des
   éléments. Le service refuse AVANT de supprimer.
3. `pipeline/manifest.py` — étape 2.4 (extraction) + étape 5.2f (application) **et** une passe
   **inter-services** (5.2g) décrite ci-dessous.

**Deux bugs de câblage trouvés et corrigés (chacun mesuré) :**

- **La méthode est hébergée par un AUTRE service.** Le prompt 36 ne produit **aucun
  `category_service.py`** : la conception n'a créé qu'un `ProductService`, et
  `category delete` appelle `svc.delete_category(...)` **sur ce service-là** (le CLI importe déjà
  `CategoryNotEmptyError`). Une garde posée sur le service de la ressource ne s'exécutait donc
  jamais. La passe 5.2g cherche la méthode `delete_<ressource>` **par son nom, dans TOUS les
  services rendus** — pas dans un fichier présumé.
- **Mauvaise exception.** Le choix de l'exception préférait d'abord un nom contenant celui de
  l'ÉLÉMENT ; or la conception déclare `CategoryNotEmptyError` (juste) ET `ProductNotFoundError`,
  et « product » désignait ce dernier : une suppression bloquée annonçait un produit introuvable.
  L'ordre est désormais : indices référentiels (`notempty`/`referenc`/`conflict`) **d'abord**, puis
  un nom contenant l'élément **à condition de ne pas dire `notfound`/`missing`**, puis les noms
  génériques, puis `ValueError`. La conception déclare `CategoryNotEmptyError` : c'est lui qui est
  levé.

**Mesure prompt 36** (régénéré, 215,3 s) :

| cas | résultat |
|-----|----------|
| catégorie 1 + un produit dedans | `has_products(category_id)` posée ; `delete_category` gardée |
| suppression de la catégorie 1 | **`Error: cannot delete category while products still belong to it`** |
| catégorie 2 (vide) → suppression | **`True`** |
| la catégorie 1 après coup | **toujours listée** (`Category(name='Electronics', id=1)`) |

→ « une catégorie ne peut pas être supprimée tant que des produits lui appartiennent » :
**satisfait**, et le test reste discriminant (une catégorie vide est bien supprimable, et la
catégorie référencée survit intacte — ni suppression ni cascade silencieuse).

**Distinction avec la cascade** : c'est une GARDE (un refus), délibérément distincte du
comportement de CASCADE que le prompt 37 demande — le spéc décide lequel s'applique, et ici il dit
que la suppression ne doit pas avoir lieu.

**Risque nommés : nul, mesuré par lecture.** `grep -rln "cannot be deleted" prompts/` ne renvoie
que `prompt_36.txt`. Le prompt nommé `inventory` expose pourtant `category delete --id` — mais il
n'énonce **jamais** la phrase de refus, donc la règle ne s'y déclenche pas. Protocole nommés
relancé pour le critère.
### E3 — arbre frais obtenu (2026-09-18 15:19)

38 a été régénéré avec le générateur courant (`python3 agent.py --prompt 38`, 15:19). Ce que le
générateur produit **aujourd'hui** (le journal de génération donne les signatures exactes) :

- `user_repository.py` — `authenticate_user(user_id) -> bool`, `add_user`, `get_user_by_email`,
  **`list_user_documents(user_id) -> List[Document]`**, **`get_document_by_id(document_id)`**,
  **`get_user_document_count(user_id)`**, **`get_user_status(user_id) -> str`** : les primitives
  de propriété sont donc **déjà** présentes côté dépôt.
- `document_repository.py` — `list_documents(title, is_public, created_at)`,
  `update_document(document_id, title, content, is_public)`, `delete_document(document_id)`.
- `auth_service.py` **et** `document_service.py` — deux services aux **mêmes méthodes** :
  `authenticate_user(id)`, `list_document(title, is_public, created_at)`,
  `update_document(id, title, content, user_id, is_public)`, `delete_document(id)`, `add_user`.
  Le CLI importe `AuthService` depuis `auth_service`.
- `cli.py` — `user authenticate --id` ; `document list --title --is-public --created-at`
  (**aucun acteur**) ; `document update --id --title --content --is-public --user-id`
  (**`--user-id` sert à ÉCRIRE le propriétaire**, pas à le vérifier) ; `document delete --id`
  (**aucun acteur**).

**Écart à l'exigence** : rien n'exige l'authentification avant d'accéder à un document, et
`list`/`delete` n'ont même pas d'acteur ; `update` laisse réattribuer un document à n'importe
qui. Le correctif E3 doit : exiger l'acteur sur `list`/`update`/`delete`, vérifier que l'acteur
est authentifié, refuser (`PermissionError`) quand la ligne n'appartient pas à l'acteur, et
restreindre `list` aux documents de l'acteur.

Deux défauts connexes, **hors périmètre E3**, à traiter séparément :
1. la conception émet **deux** fichiers de service avec les **mêmes méthodes**
   (`auth_service.py` + `document_service.py`) — doublon d'entité ;
2. `document update` accepte de réécrire `user_id` — c'est le même défaut que la propriété,
   mais sa correction est une conséquence directe de la garde (l'acteur n'est plus un champ).
### E3 — ACQUIS (2026-09-18 17:43)

**Exigence** (prompt 38) : « Users must authenticate before accessing documents. A user can only
read, modify or delete their own documents. » Deux obligations : (1) authentifier avant tout accès,
(2) n'accéder qu'à ses propres lignes.

**Deux modules.** `pipeline/ownership_rules.py` lit la phrase et rend la règle structurée
(`actor`, `resource`, `owner_field`, `auth_required`, `verbs`, `scoped_writes`) — ou `None`.
`generation/ownership_guard.py` la transforme en code : `list_<res>` gagne l'acteur et ne rend que
ses lignes, `update_/delete_<res>` chargent la ligne AVANT d'écrire et lèvent l'exception de
permission du design si elle appartient à un autre, le CLI gagne `--user-id` (obligatoire).

**Trois défauts d'implémentation trouvés et corrigés** (chacun mesuré) :

| défaut | symptôme | correctif |
|---|---|---|
| import mort | `from agentlib.naming import snake` — `naming` n'exporte que `_snake` | import de `_snake` |
| mauvais dépôt pour le chargeur | `self.document_repo.get_document_by_id(...)` → `AttributeError` (le chargeur vit sur `UserRepository`) | `_getter_for` rend le COUPLE (attribut, méthode), le dépôt de la ressource essayé en premier |
| `_add_param` tronquait l'annotation | `list_document(...)` perdait son `-> List[Dict[str, Any]]` | `_paren_span` apparie la parenthèse par profondeur ; le suffixe `-> …` est conservé |

**Le défaut de fond, trouvé par la mesure et non par lecture** : la première régénération a produit
des corps gardés (référençant `user_id`) avec des signatures NON étendues → `NameError` à chaque
appel de `list_document`/`delete_document`. Cause : `run.py:_restore_service_signatures`, exécuté
APRÈS le rendu, ré-impose la signature **conçue** de chaque méthode de service (il existe pour
rattraper les paramètres CLI perdus par la boucle de réparation) — et l'acteur ne fait pas partie du
design. La garde est donc déplacée en fin de phase de finalisation
(`run.py:_apply_ownership_scope`, juste après la restauration), la règle voyageant dans
`design_ctx`. Une exigence de spécification s'impose après le contrat de design, sur ce qui est
réellement livré.

**Preuve fonctionnelle** (deux utilisateurs A et B, un document appartenant à B — `generated/38`) :

| cas | résultat |
|-----|----------|
| `document list --user-id A` | `[]` — le document de B n'apparaît pas |
| `document list --user-id B` | la ligne de B est listée |
| `document delete --id <docB> --user-id A` | **refusé** (`Error: you may only access your own records`), la ligne **survit** |
| `document update --id <docB> --user-id A --title hacked` | **refusé**, le titre est inchangé |
| `document list --user-id 999` (acteur inconnu) | **refusé** (`User with ID 999 not found`) — l'authentification précède l'accès |
| `document update`/`delete` avec `--user-id B` | réussissent (`True`) |

12/12 vérifications passent.

**Formes produites** : `list_document(self, user_id: int, title=None, …) -> List[Dict[str, Any]]`,
`delete_document(self, id: int, user_id: int) -> bool`, et les TROIS commandes
`document list/update/delete` portent `--user-id` (int, obligatoire) transmis au service. Les DEUX
services (`auth_service.py` et `document_service.py`) sont gardés : deux copies qui divergeraient
sur « qui peut lire » sont pires qu'une seule.

**Portes sur 38** : `surface`, `cli-conformity`, `repo-conformity` → « No prompt enumerates a command
line » (38 n'énumère pas sa ligne de commande : ces portes ne s'appliquent pas) ;
`semantic --project 38` → « no spec invariants registered » (l'oracle ne couvre que les nommés).

**Risque nommés : nul, prouvé.** `grep -il "their own" prompts/prompt_*.txt` ne renvoie que
`prompt_38.txt` et `prompt_39.txt` ; aucun des six nommés ne contient la phrase, donc
`extract_ownership_rule` y rend `None` et `_apply_ownership_scope` est un no-op. Protocole complet
relancé (régénération comprise) :

| prompt | génération (s) | marqueurs | fonctionnel | conforme | façade |
|---|---|---|---|---|---|
| `cli_tool` | 11.3 | 0 | PASS | PASS | pass 5/5 |
| `expenses` | 393.3 | 0 | PASS | PASS | pass 14/14 |
| `hello_world` | 1.9 | 0 | PASS | PASS | no_mapped 0/0 |
| `inventory` | 228.4 | 0 | PASS | PASS | pass 11/11 |
| `library_system` | 217.1 | 0 | PASS | PASS | pass 9/9 |
| `multi_module` | 141.3 | 0 | PASS | PASS | pass 5/5 |

`[named-prompts] 6/6 prompt(s) clean` — instantané : `analysis/baseline_fixes/post_E3_report.{md,json}`.

**Contribution partielle à E4** : `extract_ownership_rule` se déclenche aussi sur 39 (« view their own
orders ») — la restriction des listes à l'acteur y sera donc déjà posée. E4 reste à faire pour les
RÔLES (administrateurs vs utilisateurs normaux), que cette règle ne couvre pas.
### E4 — ACQUIS (2026-09-18 20:25)

**Exigence** (prompt 39) : « Administrators can manage products and users. Normal users can create
orders and view their own orders but cannot modify products or other users. » Trois obligations :
(1) les écritures sur `product`/`user` sont réservées aux administrateurs, (2) un utilisateur normal
n'accède qu'à ses propres commandes, (3) un utilisateur normal peut modifier **son** compte mais pas
celui d'un autre.

**Deux modules.** `pipeline/role_rules.py` lit les deux clauses et rend la politique
(`actor`, `role_field`, `admin_values`, `restricted`, `own_row`) — ou `None` ; `generation/role_guard.py`
la transforme en code : `--actor-id` (obligatoire) sur les commandes réservées, chargement de l'acteur
et test de rôle **avant** toute écriture, refus par l'exception d'autorisation du design, et
l'exception écrite noir sur blanc par le spéc — `update_user` n'exige le rôle que si la ligne visée
n'est pas celle de l'appelant.

**La moitié « propres commandes » est E3.** `extract_ownership_rule` se déclenche aussi sur 39
(« view their own orders ») : `list_order` est donc déjà restreint à l'acteur par la règle E3, et
c'est exactement ce que le spéc demande. Les deux règles cohabitent sans se marcher dessus
(`--user-id` sur `order list`, `--actor-id` sur les écritures produit/utilisateur).

**Défaut trouvé par la mesure (et corrigé dans E3).** La revue du service fraîchement généré a montré
que le filtre de propriété comparait `int` (colonne `user_id`) à `str` (l'option `--user-id` du design
39 est TEXT) → `list_order` renvoyait **toujours `[]`**. Les deux comparaisons de la garde de propriété
(filtre de liste et refus d'écriture) sont désormais faites **en texte des deux côtés**. C'est un
défaut du même genre que ceux de E3 : invisible à la lecture, trouvé en exécutant.

**Preuve fonctionnelle** (trois comptes semés hors CLI — `user add` étant lui-même réservé aux
administrateurs, le premier administrateur s'amorce hors application ; le spéc ne dit rien de cet
amorçage) — `generated/39` :

| cas | résultat |
|-----|----------|
| utilisateur normal : `product add` | **refusé** (`Error: administrators only`), rien n'est écrit |
| administrateur : `product add` | `2` |
| utilisateur normal : `product update --id 1` | **refusé**, le nom reste `Widget` |
| administrateur : `product update --id 1 --name Renamed` | `True`, le nom change |
| utilisateur normal : `user update --id <lui>` | **`True`** — son propre compte est modifiable |
| utilisateur normal : `user update --id <autre>` | **refusé** (`you may only modify your own account`), l'autre est inchangé |
| administrateur : `user update --id <autre>` | `True` |
| utilisateur normal : `user add` / `product delete` | **refusés** |
| acteur inconnu (`--actor-id 999`) | **refusé** |
| utilisateur normal : `order add` | `1` (les commandes ne sont pas réservées aux admins) |
| `order list --user-id <lui>` | **une seule** commande, la sienne (`total_amount=5.0`) — pas celle de l'autre (`7.0`) |

28/28 vérifications passent.

**Formes produites** : les TROIS services (`user_service.py`, `product_service.py`,
`order_service.py`) portent la garde (le CLI n'en utilise qu'un, mais deux copies qui divergeraient
sur « qui peut écrire » sont pires qu'une) ; `product list` et `user list` sont **intacts** (lire
n'est pas « gérer ») ; l'exception levée est `PermissionDeniedError`, celle que le design déclare
(et elle est importée dans le service par la garde si elle ne l'était pas).

**Portes sur 39** : `surface`, `cli-conformity`, `repo-conformity` → « No prompt enumerates a command
line » (39 n'énumère pas sa ligne de commande) ; `semantic --project 39` → aucun invariant enregistré.

**Risque nommés : nul, prouvé.** `grep -il "admin\|normal user\|regular user\|role"` sur les six
nommés ne renvoie **rien**, et la règle exige de plus que la classe actrice porte une **colonne de
rôle** : `extract_role_rules` rend `None` pour les six (vérifié en isolation). Le prompt 60 (numéroté)
porte la même clause administrateur, mais sa conception n'a pas de colonne `role` → la règle décline
(elle ne peut pas comparer ce qui n'existe pas). Protocole complet relancé (régénération comprise) :

| prompt | génération (s) | marqueurs | fonctionnel | conforme | façade |
|---|---|---|---|---|---|
| `cli_tool` | 12.1 | 0 | PASS | PASS | pass 5/5 |
| `expenses` | 375.2 | 0 | PASS | PASS | pass 14/14 |
| `hello_world` | 2.1 | 0 | PASS | PASS | no_mapped 0/0 |
| `inventory` | 229.3 | 0 | PASS | PASS | pass 11/11 |
| `library_system` | 220.5 | 0 | PASS | PASS | pass 9/9 |
| `multi_module` | 133.5 | 0 | PASS | PASS | pass 5/5 |

`[named-prompts] 6/6 prompt(s) clean` — instantané : `analysis/baseline_fixes/post_E4_report.{md,json}`.

**E3 re-vérifié après la correction de type** (régénéré, `generated/38`) : **12/12** — l'acteur A ne
voit ni ne modifie ni ne supprime le document de B, l'acteur inconnu est refusé, B réussit sur ses
propres lignes.

**Conséquence assumée (à l'attention du lecteur)** : rendre `user add` réservé aux administrateurs
signifie qu'aucun utilisateur ne peut être créé par la CLI tant qu'un administrateur n'existe pas.
C'est la politique que le spéc énonce (« administrators can manage … users ») ; l'amorçage du premier
administrateur est une opération hors application (migration/seed), pas une commande à inventer. De
même, `order add --user-id` reste ouvert à tout acteur identifié : le spéc ne restreint pas *pour qui*
une commande est créée, seulement qui peut la **voir** (E3 s'en charge).
## 19/09 — état des prompts numérotés 01–40, mesuré (et non plus lu)

Le rapport du 17/09 (`analysis/numbered_01_40_report.md`) datait d'avant les
correctifs ; il fallait une mesure sur les arbres **régénérés**. Les quarante
prompts numérotés ont donc été régénérés d'affilée le 19/09 (~1 h 45, rc=0
partout), puis exercés par une sonde fonctionnelle : `/tmp/state_01_40.py`,
40 sondes, 71 vérifications, qui pilote le CLI livré et efface les `.db` avant
chaque prompt.

**Résultat : 56/71 vérifications, 29 prompts sur 40 entièrement conformes.**
Sortie brute conservée : `analysis/baseline_fixes/state_01_40_fresh.txt` ;
rapport détaillé : `analysis/numbered_01_40_report_v2.md`.

Onze prompts échouent, dont cinq défauts **invisibles à la lecture de sources**
(la sonde les a trouvés en exécutant) :

- **18** — l'import CSV s'exécute (rc=0), n'importe pas la ligne valide et ne
  rejette pas l'invalide, sans le dire : `contacts` reste inchangé.
- **19** — `task export` écrit `{"total_tasks":1,…}`, un résumé, au lieu des
  tâches ; l'import et le rejet d'un fichier invalide tombent avec lui.
- **20** — `sale report` exige un `--id` que le service **ignore** (il agrège
  toutes les ventes par produit) : paramètre inventé, commande refusée sans lui.
- **22** — conforme en apparence (le total affiché est bon) mais
  `get_order_report(self, id)` n'utilise pas son `id` et additionne
  `unit_price` au lieu de `quantité × prix` : méthode fausse, résultat juste
  par accident du jeu d'essai.
- **40** — la notification existe (`LoggingNotificationService.notify` →
  `logging.getLogger("notifications").info(…)`) mais aucun handler ni niveau
  n'est configuré : **aucune trace** n'est émise, même en insérant la commande
  en SQL. S'y ajoute l'absence de toute commande de création d'ordre.

Six défauts déjà connus persistent tels quels : 02 (division entière), 03
(`--list` exige une saisie), 14 (suppression dure — le champ `deleted_at`
existe mais n'est pas utilisé), 17 (aucune commande de création), 29/30
(`import sqlite3` dans `cli.py`, aucun `ABC`/`Protocol`), 35 (`bulk-update`
exige `name`, donc jamais partielle).

Neuf correctifs antérieurs sont vérifiés comme acquis sur les arbres frais :
26 (second prêt actif refusé), 27 (chevauchement refusé, créneaux adjacents et
autre salle acceptés), 28 (total calculé depuis les lignes), 31 (découvert
refusé sans effet), 32 (transitions d'état), 36 (catégorie référencée non
supprimable), 37 (cascade), 38 (propriété), 39 (rôles).

Deux artefacts de sonde ont été corrigés en route, et sont documentés ici pour
que personne ne les prenne pour des défauts : la sonde 22 lisait un `id`
entrant en collision (elle construit désormais sa ligne, y compris les colonnes
à valeur par défaut, `quantity` et `unit_price`), et la sonde 27 créait deux
salles avec le **même** `room-number`, ce qui faisait échouer la seconde.

Le plan de correction (`analysis/generator_fix_plan.md`) reçoit les lignes
`N1`–`N10` correspondant à ces onze prompts.
---

## Session 2 — les lois « création non demandée » et « frontière de couches »

Onze prompts mesurés, dix lois écrites. Chaque loi est une **règle structurelle**
appliquée à l'arbre rendu, pas un correctif ponctuel : elle nomme la forme du
défaut et refuse de s'appliquer quand cette forme n'est pas là (chaque garde
vérifie que le fichier recollé compile, sinon elle ne touche à rien).

Lois acquises, mesures à l'appui :

- **N1 (02)** `agentlib/generation/arithmetic_literals.py` — un programme qui
  offre la division ne peut pas être entier. `7 2 divide` → `3.5` (2/2).
- **N2 (03)** `agentlib/generation/click_prompts.py` — `prompt=` n'appartient
  qu'à une option REQUISE ; `--list` ne demande plus de saisie (1/1).
- **N3 (14)** `agentlib/generation/softdelete_guard.py` — la suppression devient
  un `UPDATE` sur la colonne `deleted_at` du design et tout listage filtre les
  lignes estampillées (2/2).
- **N4 (17)** `agentlib/generation/delegation_guard.py` — un service qui
  n'utilise pas son paramètre là où le dépôt expose la même méthode avec
  exactement ces paramètres : la délégation était prévue, elle est rétablie
  (7/7 : quatre filtres, leur combinaison, la recherche).
- **N5 (18)** / **N6 (19)** `import_guard.py`, `export_guard.py` — un import
  laissé en `return []` et un export qui ne nomme aucun champ de l'entité sont
  tous deux des corps à réécrire depuis le dataclass (4/4 et 3/3).
- **N7 (20)** `command_service_guard.py` — le design avait fourni
  `sale_report_service` (agrégat par produit, sans `id`) et le CLI câblait
  l'autre service avec un `--id` obligatoire. La commande est désormais câblée
  au module **nommé d'après elle** : `sale report` → `sale_report_service.py`,
  import aliasé, options que le service n'accepte pas retirées (2/2).
- **N8 (35)** `update_validation_guard.py` + `bulk_binding_guard.py` — deux
  défauts distincts dans une même opération. D'abord la règle de CRÉATION
  (`Required field 'name' is missing`) copiée dans la mise à jour ; ensuite une
  clause `SET` construite conditionnellement et **tous** les paramètres liés
  d'un coup (7 valeurs pour 2 marqueurs), puis liés dans le désordre. La loi lie
  exactement les valeurs que les conditions ont choisies, dans l'ordre où
  l'instruction les lit (`values + list(ids)`) — mesuré : `stock_quantity=9`.
- **N9 (40)** `notify_guard.py` — le logger du service de notification n'avait
  ni handler ni niveau, donc la notification promise ne laissait **aucune
  trace** : un handler est attaché au logger du module. Mesure :
  `notification to 1: confirmed order 1`.
- **N10 (29, 30)** `naming.py` + `cli_render.py` + `repository_interface_guard.py`
  — le CLI connaissait SQLite pour nommer l'erreur qu'il rattrapait. La couche
  de persistance traduit désormais `sqlite3.IntegrityError` en
  `IntegrityViolation` (erreur de domaine) et le CLI ne rattrape que celle-ci :
  la présentation n'importe plus aucun pilote. Pour **30** seulement, la loi
  synthétise l'interface réclamée (`TaskRepositoryInterface(ABC)`) depuis
  l'implémentation livrée et la fait implémenter par elle.

Deux artefacts de sonde corrigés en cours de route, à ne pas confondre avec des
défauts du générateur : la sonde 40 exigeait une commande de création d'ordre
que le prompt **ne demande pas** (elle vérifie maintenant que la confirmation
existe, et la notification qu'elle émet), et la sonde 19 attendait le mot
« error » là où l'import signale « not imported ».
---

## Session 2 — la campagne des 66 prompts : deux lois de plus, et une limitation caractérisée

La campagne `python3 agent.py` traite **66 prompts** (les 60 numérotés et les 6
nommés), pas 40. Résultat de la passe : **64 réussis, 2 échoués** — et les deux
échecs ont livré deux lois nouvelles, toutes deux vérifiées sur l'arbre frais.

### N11 — un total de période lit un paramètre qui peut ne pas exister

    agentlib/generation/service_render.py:2587, in _apply_impl_floors
        tok in params[0].lower()
    IndexError: list index out of range

Le plancher qui marque un « total sur une période » (kind `total_in_period`)
n'était atteint que par la forme stricte « une seule entité à une date et un
numérique », et il lisait alors `params[0]` **sans vérifier que la méthode a un
paramètre**. Une méthode sans paramètre faisait tomber **tout le prompt** (et
une seule fois ne suffisait pas : la nouvelle tentative rencontrait la même
forme). Correctif : le test de période exige désormais un paramètre
(`if not params or not any(...)`), exactement comme il refuse déjà un paramètre
qui ne nomme pas une période — la méthode garde alors son remplissage.

### N12 — une méthode nommée d'après sa COMMANDE n'est pas un identifiant

    [design] invoice_service.py invalid: bad method name 'payment/list' (attempt 2)
    Done -- 0 succeeded, 1 failed out of 1 prompt(s).

Le design a nommé une méthode de service d'après la commande qu'elle sert :
`payment/list`. La barre oblique n'est pas un identifiant Python, donc le
validateur rejetait le design, la nouvelle tentative produisait le **même** nom,
et le prompt entier était déclaré en échec — alors que le design portait une
méthode parfaitement utilisable. Loi : le nom est lu comme un **chemin**, le
dernier segment est le verbe et les précédents la ressource — la façon dont le
générateur écrit partout ailleurs `<verbe>_<ressource>` (`payment/list` →
`list_payment`, `order/line/add` → `add_order_line`). Toute entrée `calls` qui
nommait l'ancienne orthographe est réécrite, pour que rien ne pointe vers une
méthode disparue.

Mesure d'isolation (`/tmp/t_norm.py`) : erreurs avant
`["bad method name 'payment/list'", "bad method name 'order/line/add'"]`,
2 renommages, `calls` réécrits, **zéro** erreur après. Mesure en génération :
le prompt 46 passe de `0 succeeded, 1 failed` à **`1 succeeded, 0 failed`**.

### Une garde resserrée au passage (N7)

La réécriture de commande (`command_service_guard`) retrouvait son callback
**par nom de méthode**, ce qui pouvait tomber sur une autre commande appelant
une méthode homonyme, et elle pouvait retirer des options tout en laissant la
commande branchée sur l'ancienne classe. Elle travaille maintenant sur le
callback **qui a justifié le module** et exige que ce callback instancie bien la
classe que le module déclare : tout ou rien. Revérifié en isolation sur 20
(`REPORT_OK: True`).

### Limitation ouverte, caractérisée : le prompt 59

Le second échec est le prompt 59 (commandes, lignes, remises, taxes, annulation,
restauration de stock, rapports, export CSV — le plus gros spéc). Après
correctif du crash N11, sa génération entre dans la **boucle de réparation**
(`pipeline/run.py:193`, `for repair_attempt in range(3)`) qui régénère des
fichiers entiers par le modèle ; sur un spéc de cette taille, chaque génération
**dépasse le budget de sortie** :

    [warn] completion hit max_tokens=8192 — output truncated   (répété)

Le processus a alors tourné **50 minutes** en émettant des appels modèle en
continu (~1/s) **sans écrire un seul fichier** pour ce prompt. Ce n'est pas un
défaut introduit par les lois N1–N12 : c'est une limite d'échelle du chemin de
réparation (une demande plus grosse que le budget de sortie est réessayée à
l'identique, donc ne peut pas aboutir). Prochaine étape, précise : borner la
boucle de réparation par une mesure de **progrès** (si deux tentatives
consécutives tronquent sans réduire le jeu d'erreurs, cesser et rapporter), et
découper le remplissage/la réparation des gros fichiers par lots de méthodes,
comme le fait déjà le remplissage de service (`LARGE_STUB_SET = 1`).

Les deux échecs n'affectent **pas** la mesure 01–40 : le prompt 59 est hors de
son périmètre, et les 40 prompts numérotés restent à **78/78** (voir
`analysis/numbered_01_40_report_v3.md`).
