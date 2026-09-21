# Esus

> Et si le LLM ne devait pas tout décider ?

Esus est un prototype expérimental de génération de code qui explore une approche **neuro-symbolique** : utiliser un petit LLM pour les décisions qui nécessitent du raisonnement et confier au logiciel déterministe tout ce qui peut être formalisé, vérifié et reproduit.

L'objectif n'est pas de forcer un petit modèle à écrire du code comme un grand modèle.

**Au contraire : il s'agit de lui laisser faire ce qu'il fait le mieux.**

Le LLM interprète la demande, extrait les intentions et prend des décisions structurées. Un kernel déterministe transforme ensuite ces décisions en code, applique les contraintes connues et vérifie le résultat.

## Pourquoi cette approche ?

Le code est un domaine particulièrement favorable à une approche neuro-symbolique.

Contrairement à de nombreuses tâches confiées aux LLM, le logiciel dispose déjà d'une structure symbolique riche et opérationnelle : types, signatures, AST, interfaces, schémas SQL, contraintes, compilateurs et tests.

Certaines décisions qu'un LLM prendrait normalement de manière probabiliste peuvent donc être représentées explicitement et traitées de manière déterministe.

La frontière est volontaire :

- **LLM** : interprétation, raisonnement et décisions sémantiques ;
- **Kernel** : contrats, structure, génération, câblage et validation ;
- **Humain** : décisions qui nécessitent réellement un jugement humain.

L'objectif n'est pas de supprimer l'incertitude du LLM, mais de **réduire la partie du système qui en dépend**.

## Architecture

Esus utilise une chaîne de traitement en plusieurs étapes :

1. **Conception** — le LLM transforme la spécification en décisions structurées.
2. **Rendu** — le kernel déterministe construit la structure connue de l'application.
3. **LLM & Splice** — le LLM complète les parties qui nécessitent une interprétation métier. Le code produit est vérifié puis réinjecté dans la structure générée.
4. **CLI & Validation** — le kernel câble l'application et effectue les vérifications déterministes.

L'élément central de l'architecture est donc la frontière entre la partie **probabiliste** et la partie **déterministe**.

```text
                  ┌──────────────────────┐
                  │  Prompt utilisateur  │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │         LLM          │
                  │  Raisonnement        │
                  │  Intentions          │
                  │  Décisions structurées│
                  └──────────┬───────────┘
                             │
                    contrats typés
                     + invariants
                             │
                             ▼
                  ┌──────────────────────┐
                  │    Kernel Esus       │
                  │  Génération          │
                  │  Validation          │
                  │  Câblage             │
                  │  Contraintes         │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Application générée  │
                  └──────────────────────┘
```

## Les petits modèles

Esus a été développé à l'origine comme une expérimentation avec un petit LLM local.

L'idée est volontairement différente de demander à un modèle de 4B de générer directement une application complète.

Le modèle travaille plutôt sur des contextes réduits et produit des décisions structurées. Le kernel déterministe prend ensuite en charge le reste du travail.

Cela permet notamment d'expérimenter avec :

- des modèles locaux de petite taille ;
- des sorties contraintes ;
- de la génération de code déterministe ;
- des contrats et invariants explicites ;
- de la validation reproductible ;
- un *Human-in-the-loop* placé au niveau des décisions.

## État du projet

Esus est un **projet expérimental de recherche**, et non un générateur de code prêt pour la production.

Les expérimentations actuelles portent principalement sur des applications Python, notamment des applications CRUD et des outils en ligne de commande.

La suite de tests contient à la fois des spécifications nommées et des spécifications de benchmark.

L'objectif n'est pas uniquement de vérifier si les projets générés s'exécutent, mais aussi de distinguer :

- la réussite fonctionnelle ;
- la conformité à la spécification ;
- les défauts du générateur ;
- les limites du kernel ;
- les erreurs du banc de test.

## Benchmark

Le benchmark nommé actuel contient six spécifications :

- `hello_world`
- `cli_tool`
- `expenses`
- `inventory`
- `library_system`
- `multi_module`

Le dernier passage donne les résultats suivants :

| Mesure | Résultat |
|---|---:|
| Réussite fonctionnelle | 6 / 6 |
| Conformité stricte à la spécification | 4 / 6 |

Ces résultats sont expérimentaux. Ils ne constituent pas une affirmation générale selon laquelle Esus serait meilleur que d'autres agents de génération de code.

L'objectif du benchmark est surtout de mesurer les limites de l'architecture et d'identifier les décisions qui pourraient progressivement être déplacées de la partie probabiliste vers le kernel déterministe.

### Analyses du benchmark

Les résultats détaillés et les comparaisons sont disponibles dans le dépôt :

- [Analyse des benchmarks](analysis/)
- [Comparaison avec Claude](analysis/claude_vs_generator.md)

La comparaison avec Claude est exploratoire et doit être interprétée avec précaution : les environnements et les mécanismes de test ne sont pas nécessairement identiques.

## D'Agent Smith à Esus

Si vous arrivez ici depuis le premier épisode, vous connaissez peut-être ce projet sous le nom **Agent Smith**.

Smith a simplement changé de corps. 😉

Le projet est le même : seul son nom a changé.

**Esus** fait référence à une divinité gauloise représentée notamment sur le Pilier des Nautes à Paris, associée à l'image d'un artisan travaillant un arbre.

Une référence plutôt appropriée pour un projet dont l'objectif est justement de transformer des décisions abstraites en construction logicielle.

## Philosophie

Esus part d'une idée simple :

> **Le LLM n'a pas besoin de tout faire pour être utile.**

Un agent de génération de code doit aujourd'hui gérer de nombreuses responsabilités : comprendre la demande, choisir une architecture, inventer des abstractions, écrire du code, modifier des fichiers, exécuter des commandes et interpréter les erreurs.

Une partie de ces tâches nécessite effectivement les capacités d'un modèle de langage.

D'autres sont au contraire suffisamment formalisables pour être confiées à du logiciel traditionnel.

Esus explore cette deuxième catégorie.

Le but n'est donc pas de remplacer le LLM, mais de **réduire son périmètre de responsabilité**.

## Pistes d'évolution

Plusieurs pistes sont actuellement explorées :

- extraction des invariants métier par le LLM ;
- contrats typés entre le LLM et le kernel ;
- génération et vérification par TDD ;
- architectures hybrides combinant des modèles généralistes et Esus ;
- utilisation de MCP ;
- décodage spéculatif ;
- nouvelles méthodes d'entraînement et de raisonnement pour les petits modèles ;
- transformation progressive des décisions récurrentes en primitives déterministes du kernel.

La question de fond reste la même :

> **Quelle partie d'un agent de génération de code doit réellement rester probabiliste ?**

## Licence

Voir le fichier [`LICENSE`](LICENSE) du dépôt.
