# Prompts nommés — mesure et analyse (16/09/2026)

Les **six** prompts nommés ont été **régénérés de zéro** avec le générateur
courant (branche `fix-behavioral-tester`, dernier correctif : `database.py`
minimal + règle R3h), puis vérifiés sur les deux axes demandés — *le code
fonctionne*, *le code respecte le prompt* — plus le **temps de génération**.
Les résultats bruts sont dans `analysis/named_prompts_report.md` (tableau) et
`analysis/named_prompts_report.json` (machine).

## Protocole

Pour chaque prompt :

1. `python3 agent.py --prompt <nom>`, chronométré au chronomètre mural ;
2. **marqueurs interdits** du log (`reject`, `still stubbed`, `reverted`,
   `sanitized`, `dropped …`) — un seul hit est un échec ;
3. `compileall` sur l'arbre produit ;
4. **fonctionnel** — chaque commande que la spécification énumère est invoquée
   sans option, avec `--help`, puis avec toutes ses options, dans une **copie
   de travail** (jamais dans `generated/`) ; une trace d'exécution Python ou une
   sortie hors 0/1/2 est un échec. Puis le **workflow minimal de la
   spécification** est exécuté pour de vrai (créer une ligne, la relire) ;
   pour les deux scripts, le script lui-même est exécuté ;
5. **conforme** — surface de commandes (`behavior_tests.conformity`), surface de
   dépôt (`behavior_tests.repo_conformity`), plus les propriétés que chaque
   spécification énonce en prose (indices de type, clés CSV pilotées par
   l'en-tête, vocabulaire de statuts, champs du modèle) ;
6. **façade** (`run_facade_execution.py`) comme contrôle **indépendant**,
   piloté par le LLM, qui exécute des intentions réelles.

## Résultats

| prompt | génération (s) | marqueurs | compile | **fonctionnel** | **conforme** | façade |
|---|---|---|---|---|---|---|
| `cli_tool` | 12.1 | propre | OK | **PASS** | **FAIL (1)** | pass 5/5 |
| `expenses` | 414.9 | propre | OK | **PASS** | **PASS** | pass 14/14 |
| `hello_world` | 2.2 | propre | OK | **PASS** | **FAIL (1)** | pass 1/1 |
| `inventory` | 249.6 | propre | OK | **PASS** | **PASS** | pass 12/12 |
| `library_system` | 230.6 | propre | OK | **PASS** | **PASS** | pass 9/9 |
| `multi_module` | 135.6 | propre | OK | **PASS** | **PASS** | pass 5/5 |

**4 prompts sur 6 sont entièrement propres**, et les deux échecs restants sont
deux défauts distincts du générateur, reproduits sur régénération fraîche.

Les trois plus gros projets (`expenses`, `inventory`, `library_system`)
exécutent aussi **toutes** les commandes de leur propre spécification, y compris
leurs workflows réels : `expense category add` → `expense add --amount 12.34`
(sans `--expense-date`) → `expense list` affiche la ligne ; `category add` →
`product add` → `product list` affiche le produit ; `library book add` →
`library book list` → `library book search` retrouvent le livre.

## Défaut 1 — `cli_tool` : un `import sqlite3` que la spécification ne demande pas

Le fichier fraîchement produit `generated/cli_tool/csv_to_json.py` commence par

```python
import click
import csv
import json
import sqlite3      # <-- jamais utilisé : ce projet n'a aucune base
import sys
```

**Cause (trouvée).** `agentlib/pipeline/generate.py::_generate_file` écrit ses
règles **pour tous les fichiers de tous les projets** :

```python
        - Use stdlib sqlite3. No sqlalchemy.
        - The SQLite database filename is "%s" — use exactly this
          name wherever the project opens its database.
```

Ces deux règles décrivent un module de stockage — et le projet `cli_tool`
n'en a aucun (pas de `database.py` dans son manifeste). Elles sont donc une
**sur-génération transmise au modèle**, exactement l'analogue, une couche plus
bas, d'une commande CLI non demandée : le modèle implémente une règle qui ne le
concerne pas, et l'import inutilisé en est la trace. Rien dans les règles ne dit
non plus « n'importe que ce que tu utilises », et aucun nettoyage post-génération
ne retire un import mort (`_run_ruff_fix` s'appuie sur `ruff`, absent ici).

**Correction proposée (non appliquée).** Ne rendre ces deux règles que si le
projet possède réellement un module de stockage, ajouter la règle « n'importe
que ce que le fichier utilise », et — filet déterministe indépendant du modèle —
élaguer les imports jamais référencés (`import X` dont `X` n'est jamais chargé ;
`from M import Y` dont `Y` n'est jamais chargé ; jamais `from __future__`).
L'élagage est sûr par construction : retirer un nom jamais lu ne peut pas casser
un programme.

## Défaut 2 — `hello_world` : `main()` sans le moindre indice de type

Le fichier fraîchement produit :

```python
@click.command()
def main():                 # <-- ni -> None ni paramètre annoté
    print("Hello, World!")
```

Alors que la spécification demande explicitement « with type hints ». Le prompt
du chemin « script » ne contient **aucune** contrainte d'annotation (aucune
règle de type n'y figure, contrairement aux règles de stockage ci-dessus), et
aucun contrôle ne la rétablit ensuite : le modèle écrit `def main():` et rien ne
le corrige.

**Correction proposée (non appliquée).** Énoncer la contrainte dans le prompt de
génération (« annote paramètres et type de retour ; la spécification demande des
indices de type ») **et** ajouter un plancher déterministe : une fonction de
module sans aucune annotation, dont le corps ne retourne aucune valeur
(`return` nu ou absent), reçoit `-> None`. Borné ainsi, il ne peut pas
contredire un type réel.

## Ce qui a été écarté après analyse (erreurs de MON test, pas du générateur)

Ces trois points étaient signalés au premier passage ; l'analyse sur les arbres
**frais** montre que le générateur est correct et que l'hypothèse de mesure
était fausse. Ils sont consignés pour que les deux défauts ci-dessus soient
lisibles sans ambiguïté.

1. **`inventory` : `product add --price 9.99` refusé** — `"Invalid value for
   '--price': '9.99' is not a valid integer."` La spécification d'`inventory`
   n'énonce que la moitié **stockage** de la convention monétaire (« All
   monetary values must be stored as integers (cents) »), jamais la moitié
   affichage/entrée décimale (« convert to/from decimal for display ») que porte
   celle d'`expenses`. `money_display_enabled` exige **les deux** : un prompt qui
   ne mentionne que les centiers est laissé tel quel — c'est le comportement
   voulu, documenté dans le module. L'option est donc un entier de centiers et
   `--price 999` est l'entrée correcte ; avec elle, le workflow passe.
2. **`library_system` : `library book add` échouait sur `author 1 not found`** —
   mon harnais semait l'auteur dans le **premier** `*.db` trouvé, alors que
   l'arbre livre un `app.db` **vide** à côté du vrai `library.db` du CLI. Il lit
   désormais le `DB_PATH` du `cli.py` lui-même. Correctif de mesure ; le
   générateur n'y était pour rien.
3. **`multi_module` : `--id` refusé (`--task-id` attendu), `list_tasks`
   « re-spelles list() », `get_task_count` non demandé, vocabulaire
   `in_progress`/`done` absent** — ces quatre constats venaient d'un arbre
   **périmé** (généré avant les élagueurs). Sur l'arbre frais, tout passe :
   l'option est découverte dans l'aide du CLI, et les élagueurs R1/R2/R3c
   suppriment bien les doublons et les capacités non demandées.

## État

- **Fonctionnel : 6/6.** Aucune trace d'exécution sur aucun chemin, aucun
  marqueur interdit, `compileall` OK partout ; les workflows réels et la façade
  LLM passent sur les six.
- **Conforme : 4/6.** Deux défauts du générateur, tous deux dans le chemin
  **passe unique** (le pipeline manifeste, lui, est propre sur les quatre projets
  à entités) : une règle de stockage appliquée à un projet sans stockage, et une
  contrainte d'annotation absente. Aucun des deux ne casse l'exécution ; les
  deux sont des écarts au texte du prompt.
