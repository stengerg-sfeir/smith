# Plan de correction du générateur — ordonné par gain

Critère de succès (rappel) : le code généré doit être **fonctionnel** (tourne et fait ce
qu'il annonce) **et conforme** au prompt. Chaque correctif est jugé sur le nombre de prompts
qu'il fait passer, sans casser les **6 prompts nommés** (`cli_tool`, `expenses`,
`hello_world`, `inventory`, `library_system`, `multi_module`).

## Constat d'architecture (ce qui oriente le plan)

Le générateur est un pipeline « manifeste → rendu déterministe → remplissage LLM ciblé »,
avec un **système de recettes** découvert par `pkgutil` (`agentlib/kernel/load.py:load_recipes_for`,
`recipe_types.Recipe`) et un **dispatcher** (`agentlib/kernel/service/__init__.py:dispatch_impl_body`)
qui choisit la recette par `impl["kind"]`. Les contrats (`pipeline/method_contract.py`) dérivent
du prompt des **effets** (`counter_delta`, `flag_toggle`, `flag_set`, `status_set`, `date_set`)
rendus par `kernel/service/contract_effects.py`.

Deux faits décisifs pour prioriser :

1. **Les noyaux de listing sont déjà là.** `agentlib/kernel/repo/bodies.py` implémente
   nativement : recherche LIKE (`<col>_prefix/_contains`, terme seul), filtre **domaine**
   (`<col>_domain`), **pagination** (`page/page_size` → `LIMIT/OFFSET`), tri mono-colonne
   (`_highest/_lowest/latest` → `ORDER BY … LIMIT 1`), agrégats (`SUM`, `COUNT`, `GROUP BY`),
   export/import JSON/CSV. Donc **07, 12, 16 ne sont pas des noyaux manquants** : c'est la
   **chaîne design → signature → noyau qui ne se referme pas** (la méthode/le paramètre
   attendu par la recette n'arrive pas jusqu'à elle, et le remplissage LLM prend la main).
2. **Ce qui manque vraiment** : le **tri multi-clé asc/desc** (aucun `sort`/`order` dans
   `pipeline/cli_surface.py` ni `generation/cli_render.py`), le **soft delete** (aucun
   `deleted_at`/`soft` nulle part), les **gardes d'état** au-delà du cas « already » de
   `contract_effects`, le **delta numérique avec garde négatif**, la **garde de
   chevauchement**, la **garde « au plus un »**, la **garde référentielle au delete**, les
   **effets d'audit/notification** et l'**autorisation/rôles**.

Le levier n'est donc pas d'écrire beaucoup de codes neufs, mais (a) de rendre fiables
2–3 points d'intégration déterministes, (b) de **déclarer** les capacités que les noyaux
savent déjà rendre, (c) d'ajouter une poignée de recettes/effets pour ce qui manque.

## Plan, par gain décroissant

Payoff = prompts débloqués (conformité). Effort : S/M/L. Risque nommés : oui/non.

### Palier 0 — Robustesse du pipeline (débloque/bloque tout le reste)

| # | Correctif | Cible | Payoff | Effort | Risque nommés |
|---|-----------|-------|--------|--------|---------------|
| R1 | Garder `ast.parse` contre un `None` : `_strip_import_enum_validation` (et les autres consommateurs de `_llm_fill`) doivent tolérer un remplissage nul | `generation/service_render.py:4064` (`_strip_import_enum_validation`), appelant `:4893` | **18** + supprime un crash intermittent | **S** | non |
| R2 | **Isoler un prompt défaillant** : `process_prompt` capture l'exception, marque le prompt en échec, et **continue le lot** (l'actuel abort fait tomber 19/20 quand 18 plante) | `pipeline/run.py:process_prompt` (+ boucle `main`) | protège **les 40** et les 6 nommés | **S** | non (bénéfique) |
| R3 | **Cohérence design↔rendu** : si un dépôt est synthétisé pour une entité référencée par une FK, créer **aussi** le modèle ; refuser un dépôt dont le modèle est absent | `pipeline/manifest.py:_synthesize_cli_repos` (`_ensure_entity`/`_ensure_repo`), `_merge_duplicate_entity` | **34** + classe « unresolved import » | M | oui (expenses/inventory ont des FK) |

### Palier 1 — Capacités de listing (le plus gros bloc, kernels déjà présents)

| # | Correctif | Cible | Payoff | Effort | Risque nommés |
|---|-----------|-------|--------|--------|---------------|
| W1 | **Tri paramétré** (nouvelle capacité bout-en-bout) : option `--sort-by`/`--order` dérivée du prompt, transportée jusqu'au dépôt, `ORDER BY <col> <dir>` | `pipeline/cli_surface.py:_derive_options` + `_crud_floor`/`derive_cli_surface` ; `generation/cli_render._build_service_call` ; `kernel/repo/bodies.py` (ORDER BY paramétré, aujourd'hui figé) | **15** | M | non |
| W2 | **Pagination opérante** : la surface émet déjà `--page/--page-size` (16) — brancher ces params jusqu'à la même méthode `list` et laisser le composer `LIMIT/OFFSET` s'activer | `pipeline/cli_propagate.py:_propagate_cli_commands`/`_dedupe_cli_options_by_param` ; `generation/service_render._generic_service_delegation` ; tracer pourquoi `page/page_size` ne sont pas transmis | **16** | S/M | oui (expenses/inventory list) |
| W3 | **Recherche & filtre domaine** : garantir qu'un `search(term)` et un `<col>_domain` déclarés arrivent au noyau LIKE (07 le terme, 12 le domaine) au lieu d'un remplissage | tracer `kernel/repo/bodies.py:7.LIKE` vs signature ; verrouiller dans `repo_contract.py` (le noyau doit primer sur le fill) | **07, 12** | M | oui (library search_book) |

### Palier 2 — Agrégats calculés (rapport/argent)

| # | Correctif | Cible | Payoff | Effort | Risque nommés |
|---|-----------|-------|--------|--------|---------------|
| A1 | **Total calculé depuis les lignes** : une facture/commande somme `quantité × prix unitaire` de ses lignes ; le total n'est pas un champ fourni par l'appelant | `kernel/service/sum_children.py`, `report_parts.py` ; `method_contract._report_impl` ; interdire un `--total-amount` d'entrée quand le total est dérivable | **28, 22** | M | oui (expenses total) |
| A2 | **Rapport complet** : ajouter le **nombre** au rapport par produit | `kernel/service/count_by_group.py`, `duplicate_groups.py` | **20** | S | non |

### Palier 3 — Règles métier via contrats/effets (le gros des échecs 31–36)

| # | Correctif | Cible | Payoff | Effort | Risque nommés |
|---|-----------|-------|--------|--------|---------------|
| C1 | **Delta numérique + garde négatif** : dépôt/retrait modifient `balance` ; refuser un retrait qui passerait sous zéro | nouveau kind d'effet `amount_delta` ; `kernel/service/contract_effects.py` (+ exception dédiée) | **31** | M | oui (expenses/limit_status) |
| C2 | **Transitions d'état explicites** : table `pending→confirmed/shipped/cancelled`, refus `cancelled→shipped`, `shipped→cancelled` | nouveau kind `state_transition` ; `contract_effects._already_state_guard` généralisé | **32** | M | non |
| C3 | **Garde de chevauchement** de plages de dates sur une ressource | nouveau kind `overlap_guard` ; `kernel/repo/*` (requête `EXISTS` chevauchante) | **27** | M | oui (dates expenses/library) |
| C4 | **« Au plus un actif »** (un livre ⇒ un seul prêt actif) | nouveau kind `at_most_one_active` ; `kernel/repo/*` | **26** | M | non |
| C5 | **Garde référentielle au delete** : refuser de supprimer une catégorie qui a des produits (aujourd'hui : cascade silencieuse) | `kernel/service/create_child_row._child_fk_guards` inversé pour `delete` ; distinguer *guard* (refus) de *cascade* (37, à conserver) | **36** | M | oui (inventory) |
| C6 | **Validations de champs** (email, bornes numériques) énoncées par le prompt | effet `field_validation` ; `pipeline/method_contract` → rendu dans le service | **09** | M | non |

### Palier 4 — Effets de bord & sécurité

| # | Correctif | Cible | Payoff | Effort | Risque nommés |
|---|-----------|-------|--------|--------|---------------|
| E1 | **Audit** : chaque create/update/delete écrit une ligne (opération, id, horodatage) | nouveau kind `audit_effect` + recette service ; table d'audit au modèle | **33** | M | non |
| E2 | **Notification (abstraction + impl. log)** : à la confirmation, appeler une `NotificationService` (interface + impl. qui logue) | `method_contract` (effet `notify`) ; nouveau `generation`/service pour l'abstraction ; brancher `order confirm` | **40** | M/L | oui (multi_module patterns) |
| E3 | **Propriété** : un utilisateur n'accède qu'à ses documents (contexte acteur sur les commandes) | surface + service (acteur exigé sur list/update/delete) | **38** | L | non |
| E4 | **Rôles** : admin vs user (produits/rôles réservés aux admins) | surface + service (vérif. de rôle) | **39** | L | non |

### Palier 5 — Intégrité déterministe (ne « devrait jamais » casser)

| # | Correctif | Cible | Payoff | Effort | Risque nommés |
|---|-----------|-------|--------|--------|---------------|
| D1 | **Câblage option↔paramètre** : le nom du paramètre de la fonction de commande doit être le `dest` de l'option (`--list` ⇒ `list`, pas `list_flag`) ; refuser un design incohérent | `generation/cli_render.py:_render_cli_file/_resolve_option_param/_match_param` ; contrôle existant `pipeline/design.py:_cli_wiring_errors` (à faire mordre sur 03) | **03** | S | non |
| D2 | **Point d'entrée de paquet** : émettre `__main__.py` quand la cible est un paquet (`python -m pkg`) | `generation/entrypoint.py:ensure_entry_point` | **01** | S | non |

## Protocole de non-régression (obligatoire après chaque correctif)

Les correctifs des paliers 1–4 touchent des noyaux **partagés** avec les prompts nommés
(`bodies.py`, `contract_effects.py`, `limit_status.py`, `sum_children.py`). Avant de valider
un correctif :

1. **Portes déterministes** (rapides, sans LLM) :
   `python3 bench.py surface --prompt expenses --prompt inventory --prompt library_system`,
   puis `cli-conformity` et `repo-conformity` sur les mêmes, puis
   `python3 bench.py semantic --project library_system --project expenses`.
2. **Les 6 nommés, 4 axes** : `python3 bench.py named` (régénère et lit
   `analysis/named_prompts_report.md` ; exiger « 6/6 clean » et **aucun marqueur interdit**
   `reject | dropped | still stubbed | reverted | sanitized`).
3. **Prompts numérotés touchés** : régénérer les prompts du palier + 2 prompts « témoins »
   d'un autre palier, et comparer au rapport `analysis/numbered_01_40_report.md`.
4. **Comparaison avant/après** : garder une copie de `analysis/named_prompts_report.{md,json}`
   avant le correctif, et vérifier qu'aucun axe ne régresse.

## Ordre d'exécution recommandé

1. **R1 + R2** (robustesse) : triviaux, suppriment des *faux* échecs et sécurisent toute la
   suite ; à faire en premier.
2. **D1 + D2** (déterministe) : petits, et 03/01 ne doivent jamais casser.
3. **W2 (pagination) puis W3 (recherche/domaine) puis W1 (tri)** : le plus gros gain de
   conformité, kernels existants.
4. **A1 + A2** (agrégats).
5. **R3**, puis **C1–C6** (règles métier), un kind d'effet à la fois, en relançant le
   protocole de non-régression à chaque fois.
6. **E1 → E4** (audit, notification, propriété, rôles) : les plus lourds, en dernier.

Chaque étape est « une loi à la fois » : un correctif, sa mesure, le protocole nommés,
puis le suivant.
---

## État d'exécution (journal détaillé : `analysis/progress_journal.md`)

| # | Correctif | Code | Mesure prompt | Protocole nommés |
|---|-----------|------|---------------|------------------|
| R1 | garde `ast.parse(None)` + `continue` sur remplissage nul | ✅ | **18 : OK** (généré 259 s, 0 erreur ; CRUD + export + import/test ligne invalide conformes) | en cours (passe 2, `sh-21`) |
| R2 | isolation d'un prompt défaillant dans le harnais de lot | ✅ | à mesurer (lot 34+18) | — |
| R3 | dépôt orphelin d'entité jamais conçue supprimé | ✅ | à mesurer (34) | — |
| D1 | renommage déterministe du paramètre click non câblé | ✅ | à mesurer (03) | — |
| D2 | `__main__.py` de paquet | ✅ | à mesurer (01) | — |
| E1 | audit : chaque create/update/delete écrit une ligne, et la ligne d'audit du delete survit | ✅ | **33 : OK** (create/update/delete écrivent chacun une ligne ; celle du delete survit) | 6/6 clean |
| E2 | notification : abstraction `NotificationService` + impl. qui logue, branchée sur `confirm_order` | ✅ | **40 : OK** (`['notification to 1: confirmed order 1']`) | 6/6 clean |
| E3 | propriété : acteur exigé sur `list`/`update`/`delete`, liste restreinte à l'acteur, refus `PermissionError` | ✅ | **38 : OK** (A ne voit ni ne modifie ni ne supprime le document de B ; acteur inconnu refusé ; B réussit) — 12/12 | 6/6 clean |
| E4 | rôles : `--actor-id` exigé sur les écritures `product`/`user`, rôle administrateur vérifié, un utilisateur normal ne modifie que son propre compte | ✅ | **39 : OK** (produit refusé à un non-admin, l'admin réussit ; son compte modifiable, celui d'un autre non ; acteur inconnu refusé ; `order list` ne montre que les siennes) — 28/28 | 6/6 clean |

### N — balayage fonctionnel des 40 prompts numérotés (19/09, 56/71)

Mesure sur arbres **régénérés** : `/tmp/state_01_40.py`, rapport
`analysis/numbered_01_40_report_v2.md`, sortie brute
`analysis/baseline_fixes/state_01_40_fresh.txt`. 29 prompts sur 40 conformes.

| # | Correctif (prompt) | Code | Mesure prompt |
|---|--------------------|------|---------------|
| N1 | calcul décimal (la calculatrice reste entière) — **02** | ❌ | `7 2 divide` → `Result: 3` |
| N2 | `--list` sans saisie interactive (option `prompt=`) — **03** | ❌ | `--list` → `Task to add: Aborted!` (rc=1) |
| N3 | suppression logique réellement utilisée (`deleted_at`) — **14** | ❌ | `project delete` puis `SELECT * FROM projects` → aucune ligne |
| N4 | commande de création quand le spéc n'énumère que des filtres — **17** | ❌ | groupe `product` : `filter/list/search/specify`, aucun `add` |
| N5 | import de fichier effectif **et** rejet signalé — **18** | ❌ | import rc=0, `contacts` inchangé, aucun message |
| N6 | export = les données, pas un résumé — **19** | ❌ | `tasks.json` = `{total_tasks, completed_tasks, …}` |
| N7 | paramètre d'entrée non dérivable : ne pas l'exiger (et l'utiliser s'il existe) — **20**, **22** | ❌ | `sale report` refusé sans `--id` ; `get_sale_report(id)`/`get_order_report(id)` ignorent `id` |
| N8 | mise à jour partielle (« only the quantity ») — **35** | ❌ | `bulk-update --ids 1 --stock-quantity 9` → `Required field 'name' is missing` |
| N9 | notification observable (logging configuré) + création de l'entité à confirmer — **40** | ❌ | `order confirm --id 1` → `True`, aucune trace émise |
| N10 | frontière CLI/persistance : pas de `sqlite3` dans le CLI, dépôt abstrait — **29**, **30** | ❌ | `import sqlite3` dans `cli.py` ; ni `ABC` ni `Protocol` |

Notes d'exécution :

- La passe `bench.py named` **régénère chaque prompt dans un sous-processus**
  (`agent.py --prompt <nom>`) : les correctifs D1/D2/R3 faits pendant la passe s'appliquent
  donc aussi aux prompts suivants de la même passe. La passe 2 (`/tmp/named_run2.log`) est
  lancée après R1+R2+R3+D1+D2 ; elle sert de mesure groupée, chaque axe régressant sera
  ré-imputé et re-mesuré seul.
- La passe 1 (`/tmp/named_run1.log`) n'a **jamais tourné** : la ligne `nohup …` a été avalée
  par un shell resté sur une invite de continuation de guillemet. Aucun fichier n'a été écrit
  par cette passe ; la baseline `analysis/baseline_fixes/…pre_R1.*` reste valide.
