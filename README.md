# Agent neurosymbolique — générer des projets Python à partir d'une phrase

Ce dépôt contient deux programmes, et rien d'autre à la racine :

| Fichier | Rôle |
|---|---|
| **`agent.py`** | le **générateur** : lit un prompt en langage naturel et écrit un projet Python complet et exécutable dans `generated/` |
| **`bench.py`** | le **testeur** : régénère les projets, puis vérifie le code produit (fonctionnement réel, conformité au prompt, non-régression) |

L'idée de départ : un petit LLM local (4B) **ne sait pas** écrire un projet entier sans se
tromper. Le générateur ne le lui demande donc pas. Il sépare ce qui est **décidable** de ce
qui ne l'est pas :

- le LLM produit un **design** structuré (JSON contraint par schéma : entités, champs,
  relations, dépôts, services, commandes) ;
- un **rendu déterministe** (gabarits Python) en déduit tout ce qui est mécanique —
  les modèles, le schéma SQL, les dépôts CRUD, la CLI click, l'entrée du programme ;
- le LLM n'intervient plus que pour **remplir les corps de méthode** que les gabarits ne
  savent pas produire, dans des squelettes verrouillés ;
- des **vérificateurs** (AST, contrats, cohérence dépôt/entité) rejettent un corps invalide
  et le renvoient au LLM, avec un nombre d'essais borné.

Résultat visé, et mesuré par `bench.py` : du code qui **s'exécute** et dont la **surface CLI
est exactement celle du prompt** — ni commande manquante, ni commande inventée.

---

## 1. Prérequis

**Python ≥ 3.9 pour le générateur, ≥ 3.10 pour le testeur.**
(Développé et mesuré sur CPython 3.14.5. Le détail des raisons est en commentaire dans les
deux fichiers de dépendances.)

**Paquets :**

```bash
pip install -r requirements.txt        # générateur : ruff
pip install -r requirements-dev.txt    # testeur   : ruff + click
```

- `ruff` est le **seul outil externe** qu'invoque le générateur : il passe
  `ruff check --fix --select E,F,I,W` sur chaque projet généré, pour l'ordre des imports, les
  imports inutilisés et les espaces. Sans lui la génération aboutit quand même (l'appel est
  protégé), mais le code produit garde ces défauts.
- `click` n'est pas importé par le générateur : il est **requis par le testeur**, qui
  *exécute* les CLI générés (chacun étant une application click) dans le même interpréteur.
  Preuve : importer un `cli.py` généré sans click lève `No module named 'click'`.

**Non installable, mais indispensable :**

- un **serveur llama.cpp** joignable sur `http://localhost:8000/v1`, exposant une API
  compatible OpenAI. `server.sh` en lance un (modèle `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`,
  à placer à la racine) ; sur macOS il utilise `caffeinate`. Le script doit tourner pendant
  toute génération.
- le binaire **`claude`** (Claude Code) pour la seule commande `bench.py claude`, qui sert de
  référence externe.

---

## 2. `agent.py` — le générateur

### 2.1 Utilisation

```bash
bash server.sh                         # 1. démarrer le serveur LLM (dans un autre terminal)
python3 agent.py --list                # 2. lister les prompts disponibles
python3 agent.py --prompt expenses     # 3. générer le projet
```

| Option | Effet |
|---|---|
| `--prompt` / `-p NOM` | traite le prompt `prompts/prompt_<NOM>.txt` |
| `--list` / `-l` | liste les prompts disponibles |
| `--quiet` / `-q` | réduit la verbosité |

Le projet est écrit dans **`generated/<NOM>/`**. Le LLM est appelé en température 0 avec une
graine fixe (`LLM_SEED=42`) pour être reproductible ; les essais suivants augmentent la
température pour éviter de retomber sur la même erreur.

### 2.2 Configuration (variables d'environnement)

Définies dans `agentlib/config.py` :

| Variable | Défaut | Rôle |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:8000/v1` | endpoint du serveur LLM |
| `LLM_MODEL` | `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | nom du modèle annoncé |
| `LLM_MAX_TOKENS_LONG` | `8192` | plafond des générations longues (fichier entier) |
| `LLM_SEED` | `42` | graine de l'essai principal (température 0) |
| `LLM_RETRY_TEMPERATURE` | `0.7` | température des essais de rattrapage |

### 2.3 Ce que produit le générateur

Pour un prompt qui décrit une bibliothèque, par exemple, `generated/library_system/` contient
un fichier par classe, et rien d'autre :

```
models.py                 dataclasses des entités (avec leurs types et défauts)
database.py               ouverture SQLite (PRAGMA foreign_keys=ON) + CREATE TABLE (UNIQUE, FK, ON DELETE CASCADE)
exceptions.py             les classes d'erreur déclarées par le prompt
<entité>_repository.py    un dépôt par entité : CRUD + les requêtes demandées
<entité>_service.py       la ou les couches métier
cli.py                    la CLI click : exactement les commandes du prompt
main.py                   point d'entrée exécutable (python3 main.py ...)
money.py                  conversions centimes <-> décimal, si le prompt parle d'argent
```

La base `.db` n'est pas écrite par le générateur : elle est créée au premier lancement.

### 2.4 Étapes internes

1. **Manifeste** (`pipeline/manifest.py`) — le LLM décrit l'architecture (fichiers, classes),
   le schéma des entités, les dépôts et les services, en JSON contraint.
2. **Surface CLI** (`pipeline/cli_spec.py`) — quand le prompt **énumère** ses commandes
   (`library book add --title --isbn …`), la surface est **lue dans le prompt** au lieu d'être
   conçue par le LLM. C'est ce qui garantit des noms de groupes et d'options identiques au
   prompt, et l'absence de commandes inventées.
3. **Rendu déterministe** (`generation/`) — modèles, DDL, dépôts, services, CLI, `main.py`.
4. **Remplissage** (`llm/fill.py`) — le LLM écrit les corps de méthode restants, dans des
   signatures figées.
5. **Contrôles** (`checks/`, `pipeline/method_contract.py`, verrous de `generation/`) — noms
   liés, types cohérents, entité atteinte par le bon dépôt, effets du prompt respectés. Un
   corps refusé est renvoyé au LLM ; le nombre d'essais est borné.
6. **Nettoyage** — `ruff check --fix --select E,F,I,W` sur le projet.

---

## 3. `bench.py` — le testeur

### 3.1 Utilisation

À lancer **depuis la racine du dépôt** (les suites résolvent `prompts/`, `generated/`,
`analysis/` et `behavior_runs/` par rapport au répertoire courant) :

```bash
python3 bench.py --help
python3 bench.py named                                   # régénère et vérifie les 6 prompts nommés
python3 bench.py named --only expenses --only library_system
python3 bench.py named --only expenses --skip-generate   # vérifie l'arbre existant, sans régénérer
python3 bench.py cli-conformity                          # porte déterministe, sans LLM
```

### 3.2 Les sous-commandes

| Commande | Ce qu'elle vérifie | LLM ? |
|---|---|---|
| `named` | les six prompts nommés : génération puis les quatre axes (fonctionnel, conformité, façade) | oui (génération) |
| `surface` | aucune commande autorisée ne produit de trace Python | non |
| `cli-conformity` | la surface CLI correspond au prompt **dans les deux sens** : rien de manquant, rien en trop | non |
| `repo-conformity` | la surface des dépôts correspond au prompt | non |
| `semantic` | oracle exécuté sur les invariants du prompt, validé par **mutation** (chaque invariant doit échouer sur une copie mutée) | non |
| `behavior` | tests de comportement dérivés du prompt | oui |
| `cli-behavior` | atteignabilité et comportement des commandes | non |
| `facade-intents` | extrait les intentions utilisateur et découvre la façade CLI | oui |
| `facade-exec` | mappe les intentions stockées en invocations CLI et les exécute pour de vrai | non |
| `facade-all` | les deux précédentes, par lots | oui |
| `cost` | profil de coût par phase de génération (temps mural) | non |
| `claude` | référence externe : les mêmes prompts passés à Claude Code | externe |
| `floors` | tests unitaires des « planchers » de génération (annotations, point d'entrée) | non |
| `pruners` | tests unitaires de l'élagage des dépôts | non |

### 3.3 Les six prompts nommés

`cli_tool`, `expenses`, `hello_world`, `inventory`, `library_system`, `multi_module`
(fichiers `prompts/prompt_<nom>.txt`). Ce sont les seuls pour lesquels le testeur connaît les
intentions et les invariants attendus ; les 60 prompts numérotés (`prompt_01.txt` …
`prompt_60.txt`) servent de non-régression.

### 3.4 Artefacts

- `behavior_runs/<suite>/` : résultats machine des portes (JSON + journaux).
- `analysis/named_prompts_report.{md,json}` : le tableau des quatre axes, réécrit à chaque
  `bench.py named`.

---

## 4. Organisation du code

```
agent.py                     point d'entrée du générateur (shim : ré-exporte agentlib, expose main())
bench.py                     point d'entrée du testeur (14 sous-commandes)

agentlib/
  config.py                  constantes partagées + variables d'environnement
  design.py, naming.py       schémas du design, noms de fichiers et de classes
  prompts.py                 lecture des prompts, découpage en fichiers

  llm/
    client.py                client HTTP du serveur llama.cpp (urllib, sans SDK)
    fill.py                  remplissage des corps de méthode par le LLM

  pipeline/                  orchestration « manifest-first »
    manifest.py              le manifeste : architecture -> fichiers
    design.py                appels de design contraints par schéma
    cli_spec.py              surface CLI LUE dans le prompt
    cli_surface.py,
    cli_propagate.py         réconciliation prompt <-> design
    service_contract.py      signatures de service exigées par le prompt
    model_defaults.py        défauts de champs exigés par le prompt
    value_vocab.py           vocabulaires de valeurs (ex. cash/card/transfer)
    method_contract.py       contrat extrait du prompt SEUL + vérificateur de corps
    run.py                   boucle de génération et CLI du générateur

  generation/                rendu déterministe du code
    model_render.py          dataclasses + DDL
    repo_render.py           dépôts
    service_render.py        services (le plus gros des vérificateurs)
    cli_render.py            CLI click + main.py
    money_render.py          conversions centimes/décimal
    entrypoint.py, splice.py, helpers.py, annotations.py, repo_contract.py

  kernel/                    « recettes » déterministes
    repo/                    corps de dépôt (agrégats, filtres, seuils, variantes)
    service/                 corps de service (effets de contrat, rapports, exports,
                             création d'un enfant, totaux de période…)

  checks/ast_utils.py        vérifications syntaxiques/AST et liste des modules stdlib

  bench/                     LE TESTEUR (aucune dépendance du générateur envers lui)
    named_prompt_suite.py    les quatre axes des six prompts nommés
    conformity.py            conformité prompt -> surface CLI
    repo_conformity.py       conformité prompt -> surface dépôts
    semantic_oracle.py,
    spec_invariants.py,
    mutate_semantic.py       oracle exécuté + preuve par mutation
    facade_discovery.py,
    facade_mapping.py,
    facade_executor.py       découverte de la façade, mappage des intentions, exécution
    renderer.py, oracle.py,
    rule_kinds.py            testeur de comportement historique
    cmd_*.py                 une sous-commande par fichier

prompts/                     60 prompts + les 6 nommés
generated/                   projets générés (écrasés à chaque régénération)
behavior_runs/               artefacts des portes
analysis/                    notes d'analyse et rapports
```

`agentlib/bench/` est le **seul** paquet du testeur : le générateur ne l'importe jamais, et
`agentlib/bench/` n'importe du générateur que ce qu'il faut pour le piloter.

---

## 5. Dépendances, en résumé

| | paquets Python | outils externes | Python |
|---|---|---|---|
| **Générateur** (`agent.py`) | *aucun* (100 % stdlib, LLM en `urllib`) | `ruff` ; serveur llama.cpp | ≥ 3.9 |
| **Testeur** (`bench.py`) | `click` | les mêmes, plus `claude` pour `bench.py claude` | ≥ 3.10 |

Le détail et les justifications sont dans `requirements.txt` et `requirements-dev.txt`.

---

## 6. Connaître l'état réel du code

`analysis/semantic_dispositions.md` est le **journal des dispositions** : pour chaque défaut
sémantique corrigé, il indique le mécanisme qui l'empêche désormais de revenir et la mesure
qui le prouve. C'est la source de vérité sur ce qui est réellement garanti aujourd'hui ;
`analysis/convergence_plan.md` conserve la méthode et les preuves datées du chantier.

## 7. Limites connues

- **Le testeur a besoin du LLM** pour `named` et `facade-all` (les portes déterministes —
  `cli-conformity`, `repo-conformity`, `semantic`, `surface` — non).
- **Le « 100 % » est relatif au prompt** : il porte sur la surface CLI **déclarée** et sur les
  exigences **énumérées** par le prompt. Une valeur absurde, de la concurrence ou de très gros
  volumes ne sont couverts que si le prompt l'exige.
- **Le déterminisme n'est pas total** : le remplissage LLM des corps de méthode peut varier
  d'un run à l'autre. C'est pourquoi chaque garantie importante est soit rendue
  déterministe, soit couverte par un oracle exécuté.
- Certains prompts sont **ambigus** (par exemple `library_system` liste `--author-id` en CLI
  sans fournir de commande pour créer un auteur, et ne donne aucune durée de prêt). Le
  générateur suit alors le texte du prompt ; ces points sont documentés dans `analysis/`.
