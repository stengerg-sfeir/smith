# Numérotation des prompts 01–20 — point d'étape

Méthode, par lot de 5 : (1) génération + profil de coût
(`bench.py cost --prompt … --json analysis/generation_cost_profile_batchNN.json`),
(2) passe façade (`bench.py facade-all --only …` : intentions utilisateur → commandes
réelles → exécution), (3) **exécution manuelle** de chaque application (c'est elle qui
trouve les vrais défauts ; la façade est superficielle — elle valide qu'une commande
tourne, pas qu'elle fait ce que le prompt demande).

Convention : « fonctionnel » = l'appli tourne et ses opérations marchent.
« conforme » = elle respecte ce que le prompt **énonce explicitement**. Un générateur qui
n'implémente pas ce que le prompt ne demande pas n'est pas pénalisé.

## Synthèse 01–20

| id | fonctionnel | conforme au prompt | défaut constaté |
|----|-------------|--------------------|-----------------|
| 01 | oui | oui | **corrigé (D2)** : `hello/__main__.py` est émis → `python -m hello` imprime `Hello, World!` |
| 02 | ~ | ~ | **division entière** `//` : `7 / 2 → 3` (devrait être 3,5) ; entiers seulement |
| 03 | oui | ~ | **crash corrigé (D1)** : le paramètre porte le `dest` de l'option (`list_flag` → `list`). **Résiduel** : l'option garde `prompt='Task to add'` → click réclame une saisie interactive même pour `--list` |
| 04 | oui | oui | — |
| 05 | oui | oui | sorties brutes (`1`, `True`, repr dataclass) |
| 06 | oui | oui | commandes en trop (search/retrieve/export) ; `price` typé TEXT |
| 07 | oui | oui | **corrigé (W3)** : `search_book(term)` délègue au dépôt → `book search --term Ring` renvoie la ligne |
| 08 | oui | oui | — |
| 09 | oui | **non** | **aucune validation** : email invalide, âge 17/71, salaire négatif tous acceptés |
| 10 | oui | oui | aucun défaut bloquant (marqueurs internes `sanitized`/`dropped` mais code OK) |
| 11 | oui | oui | ISBN unique réellement garanti (contrainte UNIQUE) |
| 12 | oui | oui | **corrigé (W3)** : `--email-domain` émet `email LIKE '%<valeur>'` → Alice+Bob (`example.com`), Carol (`other.org`) |
| 13 | oui | oui | SKU unique, filtre catégorie, stock bas (`list --max-stock`) OK |
| 14 | oui | **non** | **pas de soft delete** : `delete()` fait un `DELETE` réel (ligne disparue) malgré une colonne `deleted_at` |
| 15 | oui | oui | **corrigé (W1)** : `--sort-by`/`--order` → `ORDER BY <col> ASC|DESC` (prix croissant : Apple, Mango, Zebra ; décroissant : l'inverse) |
| 16 | oui | oui | **corrigé (W2)** : l'enveloppe `{items, page, page_size, total, total_pages}` ; `--page-size 2` → C1,C2 (`total: 5`, `total_pages: 3`) ; page 2 → C3,C4 ; page 3 → C5 |
| 17 | ~ | ~ | filtres présents et combinables sur `product list` (`--name --category --max-price --min-quantity`) ; mais **aucune commande `add`** → aucune donnée possible |
| 18 | oui | oui | CSV import : ligne invalide rejetée (email/mail manquant), données existantes intactes |
| 19 | oui | oui | JSON export/import + `validate` ; 8/8 intentions OK |
| 20 | oui | oui | **corrigé (A2)** : rapport = `{1: {'total': 50.0, 'count': 2}, …}` — le montant **et** le nombre par produit |

Bilan **après correctifs** : **16/20 conformes** — 01,03,07,12,15,16,20 corrigés, re-mesurés
et validés par le protocole nommés (6/6 clean à chaque passe) : D2 (01), D1 (03, crash),
W3 (07, 12), W1 (15), W2 (16), A2 (20). **Restants** : 02 (division entière `//` au lieu
de `/`), 09 (aucune validation), 14 (pas de soft delete malgré `deleted_at`), 17 (aucune
commande `add`).

## Consommation et vitesse (générateur Qwen3-4B, llama.cpp 9430, Metal)

Tokens = ceux rapportés par le serveur (`usage`) ; les remplissages streamés
(`fill.py:_llm_fill`) ne rapportent pas de `usage` → **les tokens sont sous-comptés**,
`chars_out` couvre tout le trafic.

| id | mur (s) | LLM (s) | appels | tok in | tok out | src (chars) |
|----|--------:|--------:|-------:|-------:|--------:|------------:|
| 01 | 8,4 | 8,3 | 5 | 1110 | 222 | 219 |
| 02 | 8,6 | 8,5 | 2 | 281 | 321 | 1254 |
| 03 | 14,1 | 14,1 | 2 | 269 | 553 | 2114 |
| 04 | 14,5 | 14,5 | 2 | 275 | 568 | 2438 |
| 05 | 98,8 | 98,7 | 15 | 5769 | 2861 | 9335 |
| 06 | 150,2 | 150,0 | 16 | 7008 | 4475 | 13457 |
| 07 | 140,9 | 140,7 | 14 | 7222 | 4429 | 16016 |
| 08 | 105,0 | 104,9 | 14 | 6998 | 3447 | 11473 |
| 09 | 133,1 | 133,0 | 14 | 7232 | 4310 | 12905 |
| 10 | 142,6 | 142,4 | 16 | 8203 | 4892 | 10213 |
| 11 | 137,2 | 137,0 | 14 | 7221 | 4590 | 13923 |
| 12 | 154,2 | 154,0 | 16 | 7032 | 4385 | 12116 |
| 13 | 161,7 | 161,6 | 15 | 6227 | 4993 | 15470 |
| 14 | 103,8 | 103,7 | 13 | 6134 | 3380 | 11672 |
| 15 | 133,8 | 133,6 | 16 | 6920 | 4093 | 11303 |
| 16 | 172,1 | 171,9 | 14 | 6453 | 4541 | 17676 |
| 17 | 103,1 | 103,0 | 14 | 5846 | 3006 | 9562 |
| 18 | 289,5 | 289,3 | 18 | 7715 | 6007 | 22746 |
| 19 | 206,1 | 205,9 | 16 | 6262 | 5785 | 20430 |
| 20 | 222,2 | 222,1 | 18 | 9191 | 6619 | 21883 |

- **Débit de décodage** : `tg ≈ 36–39 tok/s` (journal llama-server). Rapport
  utile : ~**6–7 ms par caractère de sortie**.
- **Temps mural** : de 8 s (01, script trivial) à 290 s (18, multi-entités). Les prompts
  script/single-pass (01–04) tiennent en 1 seul appel LLM de code ; les prompts CRUD
  multi-fichiers font 13–18 appels (design, contrats de méthode, CLI, remplissages).
- **Total 01–20** : ~2 500 s de génération (~42 min), ~186 800 tokens rapportés,
  ~368 000 caractères produits.

## Défaut du générateur (pas du code généré)

**18 a fait planter le générateur au premier essai** :

```
service_render.py:4893  cand = _strip_import_enum_validation(cand)
service_render.py:4064  tree = ast.parse(text)
TypeError: compile() arg 1 must be a string, bytes or AST object
```

`_llm_fill` peut renvoyer `None` (échec de remplissage) ; `_strip_import_enum_validation`
n'attrape que `SyntaxError`, pas le `TypeError` levé par `ast.parse(None)`. Le crash a
**avorté le lot entier** (19 et 20 n'ont jamais tourné dans ce run). Relancé seul, 18 a
réussi (289 s) : l'échec est **dépendant du run**, pas systématique — d'où un risque
d'instabilité sur n'importe quel prompt multi-entités.

## Classes d'erreur (01–20)

« ~ » = **partiel** : l'appli tourne mais ne satisfait qu'une partie de l'exigence.

| Classe | Nature | Prompts | Où le bug naît |
|--------|--------|---------|----------------|
| **A** | Câblage CLI cassé (crash à l'appel) | 03 | déterministe (rendu CLI) |
| **B** | Corps de méthode qui ne fait pas ce que son nom dit | 07, 12, 14, 15 | remplissage LLM |
| **C** | Contrainte métier énoncée non appliquée | 09 | remplissage LLM |
| **D** | Option déclarée mais inerte (présente, ignorée) | 16 | remplissage LLM |
| **E** | Logique d'opération fausse (arithmétique) | 02 | remplissage LLM (single-pass) |
| **F** | Agrégat / rapport incomplet | 20 | remplissage LLM |
| **G** | Empaquetage / point d'entrée | 01 | déterministe (entrypoint) |
| **H** | Capacité CRUD manquante | 17 (pas d'`add`), 18 (pas de `get`) | design / rendu |
| **I** | Sur-génération (commandes/champs non demandés) | 06, 07, 12, 16, 18 | design |
| **J** | Crash du générateur lui-même | 18 (1er essai) | pipeline |

Détail des défauts « durs » (A, B, C, D, E, F, G) :

- **A — 03** : `@click.option('--list','-l', …)` produit un `dest` `list`, mais la fonction
  `cli(...)` déclare `list_flag` → `click` appelle `cli(list=…)` → `TypeError`. **Bug du
  rendu CLI déterministe**, pas du LLM. C'est le plus grave : la partie « censée être
  infaillible » casse.
- **B — 07, 12, 14, 15** : le corps rempli par le LLM ne correspond pas à la signature.
  - 07 : `search_book(term)` écrit un CSV nommé `term`, ne filtre pas.
  - 12 : `list(email_domain=…)` compare `email = ?` au lieu d'un `LIKE '%@domaine'`.
  - 14 : `delete()` fait un `DELETE` réel au lieu de poser `deleted_at`.
  - 15 : `list()` ne trie jamais (`ORDER BY id` constant).
- **C — 09** : `add_employee` construit l'entité sans aucun contrôle (email/âge/salaire).
- **D — 16** : `--page`/`--page-size` sont bien câblés jusqu'à la méthode, mais le corps
  ignore la pagination (et ne renvoie pas le total de pages).
- **E — 02** : `num1 // num2` (division entière) au lieu de `/`.
- **F — 20** : le rapport renvoie `{produit: montant_total}` mais pas le **nombre** de ventes.
- **G — 01** : `main()` placé dans `__init__.py`, pas de `__main__.py` → `python -m hello`
  échoue.

Lecture : sur les 7 défauts durs, **5 sont dans des corps remplis par le LLM**
(B=07,12,14,15 ; C=09 ; D=16 ; E=02 ; F=20 — soit 8 prompts) et **2 dans le déterministe**
(A=03, G=01). Les classes B/C/D/F sont exactement le risque que l'architecture
neurosymbolique prétend réduire : la structure est posée correctement, c'est la
*sémantique* des corps qui dérape avec un modèle 4B.

## Suite

Reprendre 21–40 par lots de 5, même protocole (génération + cost, façade, exécution
manuelle), puis compiler le rapport final 01–40 (conformité + tokens + vitesse).
## Prompts 21–40 mesurés (en cours)

| id | fonctionnel | conforme au prompt | défaut constaté / état |
|----|-------------|--------------------|------------------------|
| 22 | oui | oui | **corrigé (A1)** : `order add` ne réclame plus de total ; `order report --id 1` → `40.0` (3×10 + 2×5), calculé à partir des `order_item` |
| 28 | oui | oui | **corrigé (A1)** : `invoice add` ne réclame plus de total ; `invoice calculate-total --id 1` → `35.0` (3×7 + 2×7) via `sum_children` (quantité × prix du produit référencé) |
| 34 | oui | ~ | **corrigé (R3)** : `models.py` dédupliqué → `class Customer` rendue (plus de `unresolved import`) ; `order add --customer-id 1` échoue proprement sur FK. **Restant** : aucune commande pour créer un client ni des lignes de commande (capacité métier) |

Défaut transversal relevé sur 22/28 (classe **H**, capacité manquante) : aucune commande
`order_item add` / `invoice_line add` n'est exposée, donc les lignes ne sont créables que par
le dépôt. La règle d'atomicité « créer le parent ET ses lignes, sinon rien » n'est pas
exerçable en CLI.
