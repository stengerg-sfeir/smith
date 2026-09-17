# `bench.py` — le testeur

`agent.py` **génère**. `bench.py` **vérifie**. Ce document explique ce que chaque porte
teste, pourquoi elle existe, et comment s'en servir — pour un prompt, pour un lot, ou pour
tous.

À lancer **depuis la racine du dépôt** : les suites résolvent `prompts/`, `generated/`,
`analysis/` et `behavior_runs/` par rapport au répertoire courant.

```bash
python3 bench.py --help          # la liste des 14 commandes
```

---

## 1. Les quatre questions, et la cinquième

Le harnais ne vérifie pas « le code compile ». Il **exécute** le projet généré et répond à
quatre questions indépendantes :

| # | Question | Porte qui y répond |
|---|---|---|
| 1 | **Est-ce que ça marche ?** Chaque commande du prompt s'exécute sans trace Python, et le scénario minimal du prompt (créer puis lister) fonctionne pour de vrai. | `surface`, `named` (axe fonctionnel) |
| 2 | **Est-ce que ça respecte le prompt ?** La surface CLI et la surface des dépôts sont exactement celles demandées : rien de manquant, **rien en trop**. | `cli-conformity`, `repo-conformity`, `named` (axe conforme) |
| 3 | **Est-ce que le métier est correct ?** Les invariants que la spécification décrit en prose tiennent sur une base réelle. | `semantic` |
| 4 | **Un utilisateur qui suit le prompt y arrive-t-il ?** Les intentions d'un utilisateur sont extraites, traduites en commandes réelles, et exécutées. | `facade-intents`, `facade-exec`, `facade-all` |

Et une cinquième, qui porte sur le test lui-même :

| # | Question | Porte |
|---|---|---|
| 5 | **Ce test prouve-t-il quelque chose ?** Chaque invariant doit **échouer** sur une copie volontairement mutilée. Un invariant qui survit à sa propre mutation ne prouve rien. | `semantic` (validation par mutation) |

C'est le point le plus important du harnais : une porte qui passe n'a de valeur que si l'on a
montré qu'elle **peut** échouer.

---

## 2. Les 14 commandes

« Cibles » = ce que la commande traite **quand on ne lui passe aucune option**.

| Commande | Ce qu'elle teste | Cibles par défaut | LLM ? | Sortie |
|---|---|---|---|---|
| `named` | les 4 axes sur les 6 prompts nommés (génération comprise) | 6 nommés | oui (génère) | `analysis/named_prompts_report.{md,json}` |
| `surface` | aucune commande autorisée ne produit de trace Python | 3 énumérants | non | `behavior_runs/surface_smoke/` |
| `cli-conformity` | la surface CLI = celle du prompt, dans les deux sens | 3 énumérants | non | `behavior_runs/cli_conformity/` |
| `repo-conformity` | la surface des dépôts = celle du prompt | 3 énumérants | non | `behavior_runs/repo_conformity/` |
| `semantic` | oracle exécuté + preuve par mutation | `library_system`, `expenses` | non | console |
| `behavior` | tests de comportement dérivés de la spec | — (sélecteur obligatoire) | oui | `behavior_runs/NNN/` |
| `cli-behavior` | atteignabilité et comportement des commandes | 3 énumérants | non | console |
| `facade-intents` | extraction des intentions + découverte de la façade | 46 prompts | oui | `behavior_runs/facade/<id>.json` |
| `facade-exec` | intentions → invocations CLI → exécution | 46 prompts | non | `behavior_runs/facade/execution/` |
| `facade-all` | les deux précédentes, par lots de 5 | 46 prompts | oui | `behavior_runs/facade/batches/` |
| `cost` | où passe le temps mural d'une génération, phase par phase | 1 prompt (obligatoire) | oui | console |
| `claude` | la même spec passée à Claude Code (référence externe) | 6 nommés | externe | `analysis/` |
| `floors` | tests unitaires des « planchers » de génération | — | non | console |
| `pruners` | tests unitaires de l'élagage des dépôts | — | non | console |

---

## 3. Les cibles, chiffrées

Vérifié sur le dépôt actuel :

| Ensemble | Nombre | Qui |
|---|---|---|
| `prompts/` | **66** | 60 numérotés (`01`…`60`) + 6 nommés |
| Les 6 **nommés** | 6 | `cli_tool`, `expenses`, `hello_world`, `inventory`, `library_system`, `multi_module` |
| Les prompts qui **énumèrent une ligne de commande** | **3** | `expenses`, `inventory`, `library_system` |
| Les prompts de la **façade** | **46** | les 6 nommés + `01`…`40` |
| L'**oracle sémantique** | 2 | `library_system`, `expenses` |

Le chiffre « 3 » surprend souvent : `surface`, `cli-conformity` et `repo-conformity`
**scannent** les 66 fichiers de `prompts/`, mais ne retiennent que ceux dont la
spécification **liste elle-même** ses commandes. Les 63 autres décrivent leur interface en
prose ; il n'y a rien à comparer nom à nom, donc rien à conclure. Ces portes le disent
explicitement (« No prompt enumerates a command line ») au lieu de faire croire à une
couverture qu'elles n'ont pas.

De même, `behavior` **exige** un sélecteur (`--prompt`, `--start/--end` ou `--all`) : il
n'a pas de cible par défaut, pour qu'un `bench.py behavior` lancé par erreur ne déclenche
pas 66 passes de LLM.

---

## 4. Comment on s'en sert

### 4.0 Ce qui est déterministe, et ce qui ne l'est pas

C'est la distinction la plus utile du harnais. Cinq portes n'ont **aucun** LLM dans la
boucle : elles lisent le prompt, lisent le code généré, l'exécutent, comparent. Elles
tournent en quelques secondes, sans serveur, et donnent toujours le même verdict.

| Porte | Déterministe | Ce qui doit tourner |
|---|---|---|
| `surface`, `cli-conformity`, `repo-conformity`, `semantic`, `cli-behavior`, `floors`, `pruners` | **oui** | rien (Python seul) |
| `named`, `behavior`, `facade-intents`, `facade-all`, `cost`, `claude` | non | le serveur LLM (sauf `claude` : Claude Code) |

### 4.1 Un prompt — le bench unitaire

```bash
# les portes déterministes sur un seul prompt
python3 bench.py surface         --prompt expenses
python3 bench.py cli-conformity  --prompt expenses
python3 bench.py repo-conformity --prompt expenses
python3 bench.py semantic        --project expenses

# la façade sur un seul prompt (nécessite un projet déjà généré)
python3 bench.py facade-intents --prompt expenses
python3 bench.py facade-exec    --prompt expenses

# les quatre axes + génération, pour un prompt nommé
python3 bench.py named --only expenses

# vérifier un arbre déjà généré, sans régénérer
python3 bench.py named --only expenses --skip-generate

# où passe le temps de génération
python3 bench.py cost --prompt expenses
```

### 4.2 Un lot de prompts

Les options qui sélectionnent sont **répétables** : on les donne autant de fois qu'on veut.

```bash
python3 bench.py named           --only expenses --only library_system
python3 bench.py surface         --prompt expenses --prompt inventory
python3 bench.py cli-conformity  --prompt expenses --prompt library_system
python3 bench.py semantic        --project library_system --project expenses
python3 bench.py facade-all      --only expenses inventory library_system
```

Pour `behavior`, le lot se donne par **plage** :

```bash
python3 bench.py behavior --start 21 --end 30      # les prompts 21 à 30
python3 bench.py behavior --prompt 27              # un seul, par numéro
python3 bench.py behavior --prompt expenses        # ou par nom
```

### 4.3 Tous les prompts

Chaque porte a son idée de « tous » — c'est celle du tableau du §3 :

```bash
python3 bench.py surface           # les 3 prompts qui énumèrent une ligne de commande
python3 bench.py cli-conformity    # idem
python3 bench.py repo-conformity   # idem
python3 bench.py semantic          # library_system + expenses
python3 bench.py named             # les 6 nommés (régénère)
python3 bench.py facade-all        # les 46 prompts de la façade, par lots de 5
python3 bench.py behavior --all    # les 66 prompts (LLM, long)
```

`facade-all` **découpe en lots de 5** et écrit le résumé de chaque lot dès qu'il est
terminé : un run interrompu au prompt 30 garde les résultats des 30 premiers. On peut
ajuster avec `--batch-size`.

```bash
python3 bench.py facade-all --batch-size 3
```

### 4.4 La boucle rapide, quand on modifie le générateur

Le cycle de travail à privilégier : régénérer, puis lancer les portes déterministes. Elles
ne demandent ni serveur ni patience, et ce sont elles qui attrapent les régressions de
forme (commande en trop, crash, invariant cassé).

```bash
python3 agent.py --prompt expenses          # 1. régénérer
python3 bench.py surface --prompt expenses  # 2. ça ne crashe pas
python3 bench.py cli-conformity --prompt expenses   # 3. la surface est celle du prompt
python3 bench.py repo-conformity --prompt expenses  # 4. les dépôts aussi
python3 bench.py semantic --project expenses        # 5. le métier tient, et le test mord
```

### 4.5 Avant de conclure — la recette complète

```bash
python3 bench.py named            # les 6 nommés : génération + 4 axes + rapport
python3 bench.py semantic         # oracle + mutation sur les 2 projets à invariants
python3 bench.py facade-all       # les 46 prompts passés à la moulinette « utilisateur »
python3 bench.py cost --prompt expenses   # si le temps de génération compte
```

Puis lire `analysis/named_prompts_report.md` (le tableau des 4 axes) et
`analysis/semantic_dispositions.md` (ce qui est réellement garanti).

---

## 5. Lire les résultats

### Les statuts

Chaque porte imprime une ligne par cible, puis un total :

```text
[expenses] status=pass commands=13 runs=39 violations=0
[cli-conformity] failures=0/3 summary -> behavior_runs/cli_conformity/summary.json
[expenses] status=pass mapped=12 unmapped=0 pass=12 fail=0
[named-prompts] 6/6 prompt(s) clean
```

- `commands` / `runs` : combien de commandes, combien d'invocations réellement lancées ;
- `violations` : ce qui a échoué, détaillé juste en dessous ;
- `mapped` / `unmapped` (façade) : combien d'intentions ont pu être traduites en commandes
  réelles — un `unmapped` élevé veut dire que la façade ne permet pas de faire ce que le
  prompt décrit ;
- `pass` / `fail` : les intentions exécutées avec succès.

### Les codes de sortie — attention

| Commande | Code de sortie |
|---|---|
| `surface`, `cli-conformity`, `repo-conformity`, `semantic`, `behavior` | **0** si tout passe, **1** sinon |
| `named`, `facade-all` | **toujours 0** |

`named` et `facade-all` retournent toujours 0 : ils écrivent un **rapport** et c'est lui
qu'il faut lire, pas `$?`. Pour `named`, la dernière ligne donne le verdict
(`N/M prompt(s) clean`) et le tableau complet est dans `analysis/named_prompts_report.md`.

### Les artefacts

| Chemin | Contenu |
|---|---|
| `analysis/named_prompts_report.md` | le tableau des 4 axes + le détail par prompt |
| `analysis/named_prompts_report.json` | les mêmes données, exploitables |
| `behavior_runs/surface_smoke/<id>.json` + `summary.json` | les violations de surface |
| `behavior_runs/cli_conformity/<id>.json` + `summary.json` | les écarts prompt ↔ CLI |
| `behavior_runs/repo_conformity/` | les écarts prompt ↔ dépôts |
| `behavior_runs/facade/<id>.json` | les intentions extraites et la façade découverte |
| `behavior_runs/facade/execution/<id>.json` | l'exécution de chaque intention |
| `behavior_runs/facade/batches/batch_NN.json` | l'état de chaque lot de `facade-all` |
| `behavior_runs/NNN/` | un run de `behavior` : `prompt.txt`, `test_spec.json`, `test_behavior.py`, `generated/` |
| `/tmp/named_prompt_logs/<id>.log` | le journal de génération, celui que `named` scanne |

Un `--only` partiel sur `named` **ne perd pas** les mesures des prompts qu'il n'a pas
touchés : les enregistrements précédents sont repris depuis le JSON. On peut donc relancer
un seul prompt sans repayer les autres.

### Les marqueurs interdits

`named` scanne le journal de génération à la recherche de six marqueurs :

```text
reject | dropped (unknown target) | dropped (no designed service method)
still stubbed | reverted | sanitized | dropped infeasible
```

Un seul hit signifie que le générateur a **silencieusement dégradé** une méthode au lieu de
la rendre ou de la remplir. C'est un échec, même si le code produit tourne : le résultat
n'est pas ce que le pipeline prétend avoir produit. La colonne « marqueurs » du rapport
affiche `propre` ou le nombre de hits.

---

## 6. Ce que les portes ne couvrent pas

- **La conformité est mesurée sur ce que le prompt énonce.** `cli-conformity` compare des
  **noms** de commandes et d'options à ceux du prompt. Un prompt qui décrit son interface en
  prose (les 63 non-énumérants) n'est pas vérifié nom à nom — il n'y a pas de contrat
  explicite à comparer.
- **`surface` vérifie l'absence de trace Python, pas le bon résultat.** Une commande qui
  renvoie `0` en ne faisant rien passe cette porte. C'est `named` (scénario minimal),
  `semantic` (invariants) et la façade (intentions) qui regardent le résultat.
- **L'oracle sémantique ne couvre que deux projets** (`library_system`, `expenses`) : ce sont
  ceux pour lesquels des invariants ont été écrits depuis la prose du prompt. Les autres
  prompts n'ont pas d'invariants exécutés.
- **La façade ne couvre que 46 prompts** (6 nommés + `01`…`40`).
- **Le déterminisme n'est pas total** : le remplissage LLM des corps de méthode peut varier
  d'un run à l'autre. C'est pourquoi chaque garantie importante est soit rendue
  déterministe, soit couverte par un oracle exécuté, soit validée par mutation.
