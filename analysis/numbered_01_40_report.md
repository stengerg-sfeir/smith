# Prompts numérotés 01–40 — rapport de test

Générateur : **Agent Smith**, modèle `Qwen3-4B-Instruct-2507-Q4_K_M` (llama.cpp 9430, Metal,
serveur `localhost:8000`). Sondes exécutées depuis la racine du dépôt.

## Méthode (par lots de 5)

1. **Génération + profil de coût** :
   `python3 bench.py cost --prompt … --json analysis/generation_cost_profile_batchNN.json`.
   Écrit `generated/NN/` et rapporte, phase par phase, secondes murales, appels LLM,
   tokens (ceux rapportés par le serveur) et caractères.
2. **Passe façade** (`python3 bench.py facade-all --only …`) : le LLM extrait les intentions
   d'utilisateur, découvre la façade CLI générée, mappe chaque intention sur une commande
   réelle et l'exécute.
3. **Exécution manuelle** de chaque application : c'est elle qui trouve les vrais défauts.
   La façade est **superficielle** — elle valide qu'une commande tourne (exit 0), pas qu'elle
   fait ce que le prompt demande. Beaucoup d'applications « pass » en façade ont échoué ici
   (05 sorties brutes, 07 recherche, 12 filtre domaine, 14 soft delete, 15 tri, 16 pagination,
   31 solde, 32 transitions, 33 audit, 36 garde catégorie, 38 propriété, 39 rôles…).

Convention : **fonctionnel** = l'appli tourne et ses opérations marchent ; **conforme** = elle
respecte ce que le prompt énonce **explicitement**. Ne pas implémenter ce que le prompt ne
demande pas n'est pas une faute. « ~ » = partiel.

## Verdict global

| | nombre | prompts |
|---|---|---|
| **conformes** | 14 / 40 | 04, 05, 06, 08, 10, 11, 13, 18, 19, 21, 24, 25, 29, 37 |
| **partiels** | 5 / 40 | 01, 02, 17, 20, 23 |
| **échecs** | 21 / 40 | 03, 07, 09, 12, 14, 15, 16, 22, 26, 27, 28, 30, 31, 32, 33, 34, 35, 36, 38, 39, 40 |

Deux prompts **ne se génèrent pas du tout** : **34** (crash reproductible, cf. §générateur) et,
au premier essai, **18** (crash intermittent). Les prompt « métier » (règles, transactions,
autorisation) sont ceux qui échouent le plus : 31–40 n'en passent que 2 (29, 37).

## Détail 01–40

| id | fonctionnel | conforme | défaut constaté |
|----|-------------|----------|-----------------|
| 01 | ~ | ~ | `main()` dans `__init__.py` ; pas de `__main__.py` → `python -m hello` échoue (marche via `python hello/__init__.py`) |
| 02 | ~ | ~ | division entière `//` : `7/2 → 3` (attendu 3,5) ; entiers seulement |
| 03 | **non** | **non** | **crash à chaque appel** : `TypeError: cli() got an unexpected keyword argument 'list'` |
| 04 | oui | oui | — |
| 05 | oui | oui | sorties brutes (repr/int/bool) |
| 06 | oui | oui | commandes en trop ; `price` typé TEXT |
| 07 | oui | **non** | **`search` cassé** : écrit un CSV dans un fichier nommé comme le terme, ne filtre pas |
| 08 | oui | oui | — |
| 09 | oui | **non** | **aucune validation** (email, âge 18–70, salaire>0) |
| 10 | oui | oui | marqueurs internes `sanitized`/`dropped` mais code OK |
| 11 | oui | oui | ISBN unique garanti (contrainte UNIQUE) |
| 12 | ~ | **non** | **filtre domaine email cassé** (`email = ?` au lieu d'un LIKE domaine) |
| 13 | oui | oui | SKU unique, filtre catégorie, stock bas OK |
| 14 | oui | **non** | **pas de soft delete** (vrai `DELETE`, colonne `deleted_at` ignorée) |
| 15 | oui | **non** | **pas de tri** (`ORDER BY id` constant) |
| 16 | ~ | **non** | **pagination ignorée** (`--page/--page-size` sans effet ; pas de total de pages) |
| 17 | ~ | ~ | 4 filtres combinables sur `product list` ✓ mais **aucune commande `add`** → pas de données |
| 18 | oui | oui | CSV import : ligne invalide rejetée, données intactes (2e essai ; 1er = crash générateur) |
| 19 | oui | oui | JSON export/import + `validate` ; 8/8 intentions |
| 20 | oui | ~ | rapport = montant par produit `{1: 50.0}`, **pas le nombre de ventes** |
| 21 | oui | oui | FK customer→orders, `order list --customer-id` filtre correctement |
| 22 | oui | **non** | **impossible d'ajouter des lignes de commande** (`order_item` n'a que update/delete) → total inatteignable (`report` → 0.0) |
| 23 | oui | ~ | CRUD + N—N (`post_tag`) + **recherche par tag** ✓ ; **`post detail` plante** (`no such column: id`) |
| 24 | oui | oui | project/task CRUD, `task list --project-id` filtre correctement |
| 25 | oui | oui | department/employee, `employee list --department-id` filtre correctement |
| 26 | oui | **non** | **règle « un seul prêt actif » non appliquée** (2 prêts sur le même livre acceptés) ; `loan close` refuse de clôturer un prêt actif ; disponibilité non mise à jour |
| 27 | oui | **non** | **chevauchement non rejeté** : réservation en conflit acceptée |
| 28 | oui | **non** | **total non calculé depuis les lignes** : `invoice add` exige `--total-amount` fourni ; `report` → `{}` |
| 29 | ~ | ~ | modules séparés (models/repository/service/cli) + service→repository ✓ ; `cli.py` importe `sqlite3` |
| 30 | oui | **non** | **pas d'interface de repository** (aucun ABC/Protocol) ; **CLI accède à SQLite** (`import sqlite3` + `Database(DB_PATH)`) |
| 31 | oui | **non** | **dépôt ne change pas le solde** (reste 100.0) ; **retrait à découvert accepté** |
| 32 | oui | **non** | **transitions interdites acceptées** (`cancel` après `ship`, `ship` après `cancel` → True) |
| 33 | oui | **non** | **aucun enregistrement d'audit** (table `auditrecords` vide après create/update/delete) |
| 34 | **non** | **non** | **le générateur plante** (reproductible) : `customer_repository.py: 'Customer' not found in 'models'` ; rien généré |
| 35 | oui | **non** | `bulk-update` **exige `name`** → impossible de ne changer que le stock ; atomicité sans objet |
| 36 | oui | **non** | FK produit→catégorie ✓ (catégorie inconnue rejetée) mais **supprimer une catégorie supprime ses produits** (cascade au lieu de la garde) |
| 37 | oui | oui | **cascade projet→tâches correcte** (2→0) et atomique |
| 38 | oui | **non** | **propriété non contrôlée** : l'utilisateur 2 modifie (et réattribue) puis supprime le document de l'utilisateur 1 ; pas de commande de création de document |
| 39 | oui | **non** | **rôles non appliqués** : un utilisateur `role=user` ajoute un produit |
| 40 | oui | **non** | **aucune abstraction de notification** : `NotificationService` ne fait que fixer le statut ; `grep notify/send/logging` → rien |
## Classes d'erreur (01–40)

| Classe | Nature | Prompts | Origine |
|--------|--------|---------|---------|
| **A** | Câblage CLI cassé (crash à l'appel) | 03 | déterministe (rendu CLI) |
| **B** | Corps de méthode qui ne fait pas ce que son nom dit | 07, 12, 14, 15, 23, 36 | remplissage LLM |
| **C** | Règle métier énoncée non appliquée | 09, 26, 27, 31, 32, 35 | remplissage LLM |
| **D** | Option déclarée mais inerte | 16, 35 | remplissage LLM |
| **E** | Logique d'opération fausse (arithmétique) | 02 | remplissage LLM (single-pass) |
| **F** | Agrégat / rapport incomplet | 20, 28 | remplissage LLM |
| **G** | Empaquetage / point d'entrée | 01 | déterministe (entrypoint) |
| **H** | Capacité manquante (CRUD / création) | 17, 18, 22, 37, 38 | design / rendu |
| **I** | Sur-génération (commandes/champs non demandés) | 06, 07, 12, 16, 18, 23, 29, 30 | design |
| **J** | Crash du générateur lui-même | 18 (intermittent), **34 (reproductible)** | pipeline |
| **K** | Autorisation / propriété / rôles non appliqués | 38, 39 | remplissage LLM |
| **L** | Machine à états non gardée | 32 | remplissage LLM |
| **M** | Cascade au lieu d'une garde référentielle | 36 | remplissage LLM |
| **N** | Effet de bord / audit non produit | 33, 40 | remplissage LLM |
| **O** | Architecture non respectée (abstraction absente, couche traversée) | 30, 40 | design + rendu |

**Lecture.** Sur les 21 échecs durs (hors partiels), **15 sont dans des corps remplis par le
LLM** (classes B, C, D, E, F, K, L, M, N), **2 dans le déterministe** (A=03, G=01), **2 par
crash du générateur** (J=18, 34), et le reste par manque de capacité/architecture (H, O).
C'est exactement la répartition que prédit la thèse neurosymbolique : la **structure**
(modèles, SQLite, CLI Click, contraintes UNIQUE, cascades) tient remarquablement bien ; les
**règles métier** (solde, transitions, chevauchement, audit, propriété, rôles, total calculé)
sont ce que le 4B rate le plus souvent. Deux catégories échappent toutefois à cette lecture :
- **A (03)** et **G (01)** : des défauts dans le déterministe, qui ne « devraient jamais »
  arriver ;
- **J (18, 34)** : le générateur plante au lieu de produire — le plus grave, car il n'y a
  alors **rien** à évaluer.

## Générateur : deux crashes

**34 — reproductible (2 essais sur 2)** :

```
RuntimeError: unresolved import-level errors after repair:
  customer_repository.py: 'Customer' not found in 'models' (has: ['Order', 'OrderLine'])
```

Le pipeline est strict : il lève au lieu de dégrader. Ici le design a produit un
`customer_repository.py` (qui dépend d'une entité `Customer`) mais le fichier `models.py`
n'a rendu que `Order`/`OrderLine`. Le prompt 34 ne parle pourtant ni de clients ni de lignes
comme entités séparées — la divergence naît du design lui-même. Aucun fichier n'est écrit :
le prompt est un échec franc, non un code dégradé.

**18 — intermittent (1 crash puis succès au 2e essai)** :

```
service_render.py:4893  cand = _strip_import_enum_validation(cand)
service_render.py:4064  tree = ast.parse(text)
TypeError: compile() arg 1 must be a string, bytes or AST object
```

`_llm_fill` peut renvoyer `None` ; `_strip_import_enum_validation` n'attrape que `SyntaxError`,
pas le `TypeError` d'`ast.parse(None)`. Comme ce crash **avorte le lot entier**, un seul
prompt défaillant peut empêcher les prompts suivants de tourner (c'est arrivé à 19/20).

Ces deux crashes partagent un défaut de robustesse : **le pipeline n'isole pas un prompt
défaillant** ; il propage l'exception et interrompt la série.
## Consommation et vitesse

Unités : **mur** = temps mural mesuré par le harnais de coût ; **LLM** = somme des secondes
passées dans les appels ; **appels** = nombre de complétions ; **tok in/out** = ce que le
serveur a rapporté (`usage`) ; **src** = caractères du code livré (tous fichiers `.py`).

Attention : les remplissages streamés (`fill.py:_llm_fill`) ne renvoient pas de `usage` — les
tokens sont donc **sous-comptés** ; `chars_out` (cf. JSON par lot) couvre tout le trafic.

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
| 21 | 331,0 | 330,6 | 24 | 8224 | 5867 | 19847 |
| 22 | 240,7 | 240,6 | 17 | 8198 | 7307 | 26622 |
| 23 | 477,6 | 477,3 | 32 | 11840 | 11428 | 35242 |
| 24 | 245,0 | 244,8 | 18 | 9723 | 8153 | 27728 |
| 25 | 195,5 | 195,4 | 18 | 8946 | 6705 | 21530 |
| 26 | 250,3 | 250,1 | 17 | 7699 | 8109 | 23627 |
| 27 | 416,2 | 416,0 | 23 | 11651 | 13001 | 30410 |
| 28 | 401,5 | 401,2 | 25 | 11777 | 11993 | 35233 |
| 29 | 399,9 | 399,7 | 22 | 12097 | 12894 | 33499 |
| 30 | 294,0 | 293,8 | 23 | 8966 | 8240 | 19054 |
| 31 | 244,1 | 243,9 | 18 | 8234 | 7293 | 28742 |
| 32 | 138,0 | 137,9 | 15 | 7172 | 4357 | 16273 |
| 33 | 233,0 | 232,9 | 19 | 8858 | 6986 | 24507 |
| 34 | **—** | **—** | **—** | **—** | **—** | **— (2 crashes)** |
| 35 | 164,4 | 164,3 | 16 | 7422 | 4900 | 19995 |
| 36 | 214,5 | 214,4 | 18 | 8868 | 8093 | 20342 |
| 37 | 172,2 | 172,1 | 18 | 7622 | 6182 | 19893 |
| 38 | 341,9 | 341,7 | 28 | 11467 | 7927 | 18508 |
| 39 | 386,0 | 385,9 | 24 | 15660 | 14753 | 33029 |
| 40 | 63,9 | 63,9 | 10 | 3942 | 1915 | 12772 |

**Totaux**

| périmètre | temps mural | tokens (in+out) | caractères livrés |
|---|---:|---:|---:|
| 01–20 | ~2 500 s (~42 min) | ~186 800 | ~368 000 |
| 21–40 | ~5 210 s (~87 min) | ~334 500 | ~620 000 |
| **01–40** | **~7 710 s (~2 h 09)** | **~521 300** | **~988 000** |

(Le total 21–40 **exclut** le prompt 34, qui n'a rien produit ; ses deux tentatives avortées
ont néanmoins consommé du temps LLM, non mesuré proprement.)

**Vitesse**
- Décodage : `tg ≈ 36–41 tok/s` (journal llama-server), stable tout du long.
- Rapport utile : **~6–7 ms par caractère de sortie** (`ms per output char`).
- Temps mural par prompt : **min 8,4 s** (01, script trivial) ; **médiane ~195 s** ;
  **max 477,6 s** (23, blog N—N : 32 appels). Les prompts relationnels (21–29) et métier
  (31–40) coûtent 2 à 4× plus cher que les CRUD simples, à cause du design multi-entités
  et des contrats de méthode (plus d'appels, plus de contexte).
- Le temps est **presque entièrement LLM** : `LLM ≈ mur` à 99–100 % sur tous les prompts.

## Conclusion

- Le générateur produit une application **exécutable dans tous les cas sauf deux** (03 plante
  à l'usage, 34 ne se génère pas) ; **14/40 respectent pleinement** leur spécification.
- La **structure** est fiable (entités, SQLite, CLI Click, contraintes d'unicité, cascades) :
  aucun prompt n'a produit de code syntaxiquement cassé ou d'hallucination d'API structurelle.
- Les **règles métier et l'autorisation** sont le point faible : solde, transitions d'état,
  chevauchement de dates, audit, total calculé, propriété, rôles — **9 échecs sur 10 dans
  31–40**. C'est précisément ce que la façade « pass » à tort : elle valide qu'une commande
  tourne, pas qu'elle obéit à la règle.
- Deux **défauts déterministes** (03 câblage CLI, 01 point d'entrée) et deux **crashes
  générateur** (18 intermittent, 34 reproductible) restent à corriger côté harnais, et à eux
  seuls empêchent 03, 18, 34 d'être évalués sur le fond.
