# Plan — Correction des bugs de service (avant modification)

> Objectif : classifier les bugs de service observés au testeur facade, puis
> proposer un plan **avant** de toucher à l'agent. Aucune modification n'a été
> faite pour l'instant.

## Contexte

Les commandes CLI sont désormais correctement générées (Approche B : plus de
`dropped`/`stripped`). Les échecs restants du testeur facade pour les prompts
régénérés (32, 27, 31, 40) + anciens (35, 38) sont des **bugs de logique dans
les services générés** — la commande existe mais plante à l'exécution
(`exit_code=1`). On classe ces bugs par familles.

---

## Famille 1 — Référence à un repository non câblé / inexistant

**Symptôme** : `AttributeError: ... object has no attribute '<x>_repo'` au run.

| Prompt | Commande en échec | Bug |
|---|---|---|
| **31** | `add_customer` | `AccountService.__init__` ne câble que `self.account_repo` ; `add_customer` appelle `self.customer_repo.create(...)` qui **n'existe pas** (et `generated/31/` n'a pas de `customer_repository.py`). |
| **40** | `list_notification` | `NotificationService.__init__` ne crée **aucun** repo ; `list_notification` appelle `self.notification_repo.list(...)` inexistant. |

**Cause racine** : le corps du service (rempli par le LLM) référence un repo qui
n'est ni instancié (le header ne câble que les entités dont le fichier
`*_repository.py` est **rendu**) ni présent dans le design. C'est une
**incohérence service↔repo** : le design service déclare une méthode de repo que
l'arbre généré ne possède pas.

**Ce qu'on corrige** > **Pourquoi** > **Résultat attendu**
- **Corrige** : rendre le câblage service↔repo cohérent — (a) le design service
  ne doit déclarer que des méthodes dont le repo cible est réellement
  rendu/instancié, OU (b) le header service doit instancier le repo de chaque
  entité référencée, OU (c) le fill est rejeté si le corps appelle
  `self.<x>_repo` absent de `_service_repo_interface`.
- **Pourquoi** : chaque `AttributeError` fait échouer la commande (exit_code=1)
  alors que la surface CLI est correcte. C'est le « chaînon manquant »
  service↔intention de `CLI_FROM_INTENTS.md` §3.
- **Attendu** : `31`, `40` → commandes exécutées sans AttributeError ; le
  testeur facade les compte `pass`.

---

## Famille 2 — Logique d'agrégation erronée

**Symptôme** : `TypeError` ou résultat faux (agrégation sur un non-numérique /
mauvais champ).

| Prompt | Commande en échec | Bug |
|---|---|---|
| **27** | `reservation-list` | `list_reservation` fait `results[key] = results.get(key, 0) + row.start_date` → `0 + datetime` → **TypeError**, et retourne un `dict` alors que le type attendu est `list[dict]`. |
| **32** | `order-add` | `add_order` passe `total_amount` (str depuis le CLI) et `created_at`/`updated_at` (isoformat str) au modèle `Order` déclarés `float`/`datetime` — aucune conversion, incohérence de type. |

**Cause racine** : le remplissage LLM écrit des corps incorrects (sommer un champ
date, ne pas convertir les types primitifs). Même symptôme que
`get_product_count_by_category` / `stock_value_by_category` déjà repérés
(somme au lieu de `+1`, somme prix au lieu de `prix × quantité`).

**Ce qu'on corrige** > **Pourquoi** > **Résultat attendu**
- **Corrige** : renforcer les planchers déterministes (`_apply_impl_floors` /
  délégation CRUD) pour que les agrégations à forme connue (count, sum_by_group,
  total_in_period) soient **rendues déterministiquement** sur les bons champs
  numériques, jamais une date ; empêcher le fill d'écraser un corps déterministe
  et **valider** les corps d'agrégation LLM (pas de `+ <date>`).
- **Pourquoi** : une agrégation incorrecte produit soit un crash, soit un
  **résultat faux** qui passerait l'exécution mais échouerait l'assertion de la
  façade (résultat observé ≠ attendu).
- **Attendu** : agrégations calculées sur les bons champs (count/sum sur une
  valeur numérique), bon type de retour ; `reservation-list` répond comme
  l'intention l'exige.

---

## Famille 3 — Logique métier / lifecycle incomplète

**Symptôme** : la commande échoue car elle suppose un état préexistant (seed) ou
une méthode de repo custom non rendue.

| Prompt | Commande en échec | Bug |
|---|---|---|
| **32** | `order-confirm/ship/cancel` | `confirm_order`/`ship_order`/`cancel_order` lèvent `OrderNotFoundError` si l'id n'existe pas. Sans seed d'ordre, la commande échoue sur un simple lookup. |
| **35** | `bulk-update_stock` | `bulk_update_stock` appelle `self.product_repo.bulk_update_stock(...)` — méthode probablement absente du repo rendu (ou signature différente) → AttributeError. |
| **38** | `authenticate-login` | `authenticate_user` lève `AuthenticationError` si l'utilisateur n'existe pas (aucun seed) — ou `_verify_password` n'est pas rempli. |

**Cause racine** : le service modélise un métier qui suppose un état de départ
(un ordre déjà créé, un utilisateur déjà enregistré) ou un repo custom non rendu.
La façade exécute la commande sur un état vide → erreur légitime (« non
trouvé ») comptée comme échec car le test attend `exit_code=0`.

**Ce qu'on corrige** > **Pourquoi** > **Résultat attendu**
- **Corrige** : (a) pour les repo custom non rendus — étendre le rendu
  (`_render_simple_finder`/`_existing_variant_alias`-like) ; (b) pour les
  seed/state — faire du mapping une **séquence** (create → confirm) ou seed via
  `behavior_tests/fixtures.py`.
- **Pourquoi** : on ne veut pas masquer un vrai bug métier, mais distinguer
  « commande non câblée » de « état prérequis manque ». Le service a raison de
  refuser de confirmer un ordre inexistant ; c'est le test qui doit fournir
  l'état.
- **Attendu** : les commandes à état prérequis réussissent quand le test seed
  correctement ; les méthodes repo manquantes sont soit rendues, soit retirées
  du design.

---

## Note de cadrage (retour utilisateur)

Le service est **déduit du CLI**, lui-même déduit des intentions. Si un repo
n'existe pas, c'est que **le design ne l'a pas capturé** : c'est un problème de
**design**, pas de corps LLM. L'agent a déjà une mécanique de **rétro-propagation**
(`_propagate_cli_commands` : Pass A FK completion dans les modèles, Pass B
synthèse de méthodes service). Il faut l'**étendre** au cas où c'est le
**repo/modèle** qui manque entièrement.

## Plan d'implémentation proposé (ordre, affiné)

### Famille 1 — design : repo/modèle manquant → rétro-propagation
- Étendre `_propagate_cli_commands` (déjà : FK completion + synthèse de methods
  service) pour **synthétiser aussi le repo/modèle** d'une entité que le service
  référence mais que le design n'a pas capturé (ex. `Customer` derrière
  `add_customer`, `Notification` derrière `list_notification`).
- Pour `35`/`38` : la méthode repo custom référencée (`bulk_update_stock`,
  `get_user_by_email`, `_verify_password`) est traitée pareil — soit rendue,
  soit back-propagée au design.
- Résultat : `31`, `40` (et le volet repo de `35`/`38`) passent ; plus de
  `self.<x>_repo` fantôme **par construction**.

### Famille 2 — recettes : prudence, créer à côté
- **Ne pas modifier les recettes existantes** (`total_in_period`, `sum_by_group`,
  ...) — risque de casser des prompts qui marchent.
- Si nécessaire, **créer de nouvelles recettes non ambiguës à côté** (ex. un
  `list_grouped_count` / `count_by_group` pour le cas `0 + <date>` du 27), et
  renforcer `_apply_impl_floors` pour y diriger les formes claires.
- Résultat : `27` calcule juste ; les recettes existantes restent intacts.

### Famille 3 — reclassification
- **32** : **bug du testeur**, pas de l'appli. `OrderNotFoundError` est correct
  (on ne confirme pas un ordre inexistant).
  - **Le mapping a déjà une séquence « create before delete »** : chaque commande
    porte `creates` (l'entité qu'elle crée) et `refs` (les FK parents) — le
    testeur crée le parent puis substitue le vrai id (`_infer_refs_and_creates`
    dans `facade_mapping.py`).
  - **Ce qui manque** : une **précondition d'entité de travail non-CRUD**. Pour
    `confirm_order`/`ship_order`/`cancel_order`, la commande n'est pas
    create-style et ne référence pas un FK parent — mais elle exige qu'un
    `Order` **existe déjà** (elle prend `--id`). Il faut **étendre la séquence**
    pour déduire : « toute commande non-create qui cible une entité via
    `--id`/`<entity>_id` exige d'abord un `create <entity>` » (séquence
    spécifique à l'appli, hors CRUD).
  - → `_infer_refs_and_creates` généralisé : en plus des `refs` (FK parents),
    une précondition « create <entity> » pour les transitions d'état
    (confirm/ship/cancel/approve...).
- **35** : probablement **Famille 1** (méthode repo custom non rendue)
  → back-propagation.
- **38** : probablement **Famille 1** (repo/méthode manquante) + **fixture**
  nécessaire (comme les CSV) pour fournir un utilisateur enregistré.
- Résultat : `32` passe via la séquence étendue ; `35`/`38` passent via
  back-propagation + fixture.

## Vérification

- Régénérer les prompts concernés (sous `caffeinate`).
- Relancer le testeur facade ciblé (31, 40, 27, 35, 38, 32), puis la suite
  complète.
- Critère : disparition des `exit_code=1` **sans** masquer un vrai bug métier ;
  les recettes existantes ne changent pas de comportement (prompts actuellement
  `pass` restent `pass`).
