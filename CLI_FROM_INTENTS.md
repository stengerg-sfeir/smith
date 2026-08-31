# Redesign CLI — génération dérivée des intentions

## 1. Contexte / problème

Le testeur de façade (`behavior_tests/facade_*`) vérifie que l'app générée offre ce
qu'un **utilisateur** veut, à la surface CLI. Deux défauts ont été observés :

### 1.1 Beaucoup d'apps n'avaient pas de CLI
Sur les 46 prompts, 12 avaient `facade.kind = none` : le manifest LLM (`_generate_manifest`)
ne déclarait pas de `cli.py`, alors que ce sont des apps CRUD. Un `compute_needs_cli()`
déterministe (déjà implémenté) injecte un spec `cli.py` quand les intentions extraites du
prompt impliquent une CLI. Résultat : **11/12** prompts ont maintenant un CLI (seul `01`,
un script sans entités, reste sans CLI — comportement attendu).

### 1.2 Le sanitizer supprime des commandes / options
Pendant la régénération, beaucoup de messages :
```
[design] cli.py sanitized: book/update/update -> dropped (no designed service method serves its surface)
[design] cli.py sanitized: book/list/list: stripped dead option(s) --author, --start-year, --end-year, --title
[design] cli.py sanitized: category/summary/summary: stripped dead option(s) --category-name
```
Ces messages viennent de `_sanitize_cli_design` (`agentlib/pipeline/design.py`), qui **retire
ce que le service ne peut pas servir**. **Cause racine** : le design CLI et le design service
sont **deux décisions LLM indépendantes** qui divergent.

## 2. Diagnostic : qui a raison, le CLI ou le service ?

Le CLI est **verrouillé sur le service** (`allowed = {m.get("name") for m in service_methods}`),
donc le CLI ne peut pas exposer une méthode absente du service. C'est le **service** qui est
fautif quand il ne couvre pas une intention du prompt.

**Exemple prompt 11** (bibliothèque) : le prompt exige `create, list, update, search, delete`.
Le service expose `update_book(book)` — une signature "objet entier" **non pilotable en CLI**
(besoin de `--id --title --author ...`). Le design CLI avait proposé la bonne surface
(`book/update --title --author --isbn --publication-year`), mais elle ne matche aucune
méthode service → le sanitizer a tout supprimé. Le service n'a donc pas satisfait l'intention
"update" de façon exploitable.

**Conclusion** : la faiblesse n'est pas le CLI (fidèle au service), mais le fait que le
**service ne couvre pas les intentions** avec des signatures CLI-drivables.

## 3. Trois liaisons et leur état

| Liaison | État |
|---|---|
| CLI ↔ service | **déjà fait** (`_design_cli` contraint + `_sanitize_cli_design`) |
| Service ↔ intention du prompt | **pas fait de façon vérifiable** ← chaînon manquant |

## 4. Approche retenue : **B — dériver depuis les intentions**

Deux options étaient possibles :
- **A** : vérification *a posteriori* + réparation (boucle de repair, coût LLM variable).
- **B** : dériver la surface CLI depuis les intentions, contraindre le service à fournir
  exactement ces méthodes, puis rendre le CLI déterministiquement. **Une seule source de
  vérité** (l'intention) → cohérence par construction, **pas de boucle de réparation**.

**B est retenu.**

## 5. Règle de priorité pour la source de la CLI

La surface CLI est déterminée par ordre de précédence :

1. **Le prompt définit explicitement une CLI** (nomme des commandes : `product add --sku --name ...`,
   `python main.py list`, « CLI interface using click »)
   → **utiliser CES commandes telles quelles**. Le prompt est la source.
2. **Sinon, si une CLI est nécessaire** (gate `compute_needs_cli`)
   → **dériver la surface depuis les intentions** extraites du prompt.
3. Dans les deux cas, **le service est contraint** à fournir les méthodes correspondant à la
   surface retenue, avec des signatures **CLI-drivables** (paramètres primitifs).

### Ce qui existe déjà et supporte cette règle
- `extract_intentions` remplit `cli_command` quand le prompt nomme des commandes
  (`_prompt_specifies_cli`). Le signal « le prompt définit une CLI » est déjà capturé.
- `_design_cli` a un `_CLI_SYSTEM` : « Use the exact command surface and option names the spec
  names » — l'intention est déjà là, mais **noyée dans un design LLM libre**.

## 6. Ce que B change par rapport à l'existant

| Élément | Aujourd'hui | Avec B |
|---|---|---|
| CLI explicite du prompt | le LLM « devrait » le suivre (peut diverger) | **déterministe** : on extrait les commandes nommées et on les impose |
| CLI sans spec explicite | gate `compute_needs_cli`, puis design LLM | **dérivé des intentions** |
| Service | design LLM libre → diverge | **contraint** à la surface retenue (signatures primitives) |
| Réparation | `_sanitize_cli_design` (stripped/dropped) | **quasi nulle** : cohérence par construction |

## 7. Bénéfice attendu
- `prompt_inventory` (CLI explicite) → respecte exactement `product add --sku --name ...`,
  `category delete --id`, `product report low-stock`.
- `prompt_11` (pas de CLI explicite, intent "update") → la surface dérivée exige `book-update`,
  le service fournit un `update_book(book_id, title=..., ...)` CLI-drivable → plus de
  `book/update dropped`.

---

# TODO list d'implémentation

- [ ] **Étape 1 — Extraire les intentions pour tous les prompts (agentlib.pipeline.intents)**
  - [ ] Ajouter un appel `extract_intentions(prompt)` au début du pipeline de génération
        (pas seulement pour les prompts sans CLI).
  - [ ] Rendre l'échec d'extraction non bloquant (dégradation : pas de CLI dérivée).

- [ ] **Étape 2 — Détecter la définition CLI explicite du prompt**
  - [ ] Déterminer si le prompt nomme des commandes CLI (réutiliser `_prompt_specifies_cli` /
        les `cli_command` des intentions, ou un parse déterministe des blocs `--option`).
  - [ ] Si oui → extraire la surface CLI exacte à partir du prompt.

- [ ] **Étape 3 — Dériver la surface CLI depuis les intentions (cas sans spec explicite)**
  - [ ] À partir des intentions (`text`, `cli_command`, `requires`, `observable`), inférer la
        liste des commandes attendues (create/list/update/delete/search/report/export…).
  - [ ] Déterminer les options nécessaires à partir de `requires` / `observable`.

- [ ] **Étape 4 — Contraindre le design service à la surface retenue**
  - [ ] Modifier le system prompt du design service pour imposer : « une méthode par
        commande de la surface, avec des paramètres primitifs (pas d'objet entiers) ».
  - [ ] Passer la surface CLI (commandes + options) comme contexte au design service.
  - [ ] Valider que chaque commande de la surface est servie par une méthode service.

- [ ] **Étape 5 — Rendre le CLI déterministiquement depuis la surface**
  - [ ] Remplacer le design LLM du CLI (`_design_cli`) par un rendu 100 % déterministe à
        partir de la surface retenue (commandes + options + cible service).
  - [ ] Les cibles service sont résolues depuis les méthodes service réellement conçues.

- [ ] **Étape 6 — Vérifications**
  - [ ] `compute_needs_cli` reste correct (09/20/28 → True).
  - [ ] Régénérer `prompt_inventory` (CLI explicite) : la CLI respecte exactement la spec.
  - [ ] Régénérer `prompt_11` : la commande `book-update` existe et est exécutable.
  - [ ] Régénérer les prompts `22, 26, 27, 28, 31, 32, 34, 40` : plus de
        `book/update dropped` / `stripped dead option(s)`.
  - [ ] Relancer le testeur facade complet : vérifier l'évolution des `fail` → `pass`.
  - [ ] `tsc --noEmit`-équivalent : aucun import cassé, `agentlib` toujours self-contained.
