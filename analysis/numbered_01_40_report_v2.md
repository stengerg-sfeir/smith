# État des prompts numérotés 01–40 — mesure du 19/09/2026

Ce rapport remplace, pour les prompts numérotés, la lecture de sources du
17/09 (`analysis/numbered_01_40_report.md`). Il mesure **l'application
livrée**, pas le générateur : chaque prompt est régénéré puis exercé par une
sonde qui pilote son CLI.

- Date de la mesure : 19/09/2026, 10:20 (Europe/Paris)
- Arbres mesurés : `generated/01` … `generated/40`, **régénérés le 19/09**
  (boucle `for n in $(seq -w 1 40); do python3 agent.py --prompt $n; done`)
  après les correctifs E1–E4 (rôle, propriété), W1–W3, C1–C6, R1, D1, D2, A1, A2.
- Sonde : `analysis/state_01_40.py` (40 sondes, 71 vérifications), sortie brute
  conservée dans `analysis/baseline_fixes/state_01_40_fresh.txt`.

## Résultat global

    TOTAL 56/71 vérifications
    29 prompts sur 40 entièrement conformes
    11 prompts avec au moins un échec

| Prompt | Verdict | Ce qui échoue |
| --- | --- | --- |
| 01 | 1/1 | — |
| 02 | 1/2 | `7 2 divide` → `Result: 3` (division entière) |
| 03 | 0/1 | `--list` demande une saisie interactive |
| 04 | 1/1 | — |
| 05 | 2/2 | — |
| 06 | 1/1 | — |
| 07 | 1/1 | — |
| 08 | 2/2 | — |
| 09 | 5/5 | — |
| 10 | 2/2 | — |
| 11 | 2/2 | — |
| 12 | 3/3 | — |
| 13 | 3/3 | — |
| 14 | 1/2 | la suppression est **dure** : la ligne disparaît |
| 15 | 1/1 | — |
| 16 | 2/2 | — |
| 17 | 0/1 | aucune commande de création (`filter/list/search/specify`) |
| 18 | 2/3 | l'import CSV n'importe rien et ne signale rien |
| 19 | 0/3 | `task export` écrit un **résumé**, pas les tâches |
| 20 | 1/2 | le rapport exige un `--id` que la spec ne mentionne pas |
| 21 | 1/1 | — |
| 22 | 1/1 | — |
| 23 | 1/1 | — |
| 24 | 1/1 | — |
| 25 | 1/1 | — |
| 26 | 1/1 | — |
| 27 | 2/2 | — |
| 28 | 2/2 | — |
| 29 | 1/2 | le CLI importe `sqlite3` directement |
| 30 | 0/2 | dépôt non abstrait (ni `ABC` ni `Protocol`) + `sqlite3` dans le CLI |
| 31 | 2/2 | — |
| 32 | 2/2 | — |
| 33 | 1/1 | — |
| 34 | 1/1 | — |
| 35 | 0/1 | `bulk-update` ne peut pas ne changer que le stock |
| 36 | 2/2 | — |
| 37 | 1/1 | — |
| 38 | 2/2 | — |
| 39 | 3/3 | — |
| 40 | 0/2 | aucune commande de création d'ordre + notification invisible |

Les correctifs portent leurs fruits sur les points visés : 27 (refus du
chevauchement **et** acceptation des créneaux adjacents et de l'autre salle),
28 (total calculé à partir des lignes, pas saisi), 31 (le découvert ne change
rien), 32 (transitions d'état), 36 (catégorie référencée non supprimable),
37 (cascade), 38 (documents d'autrui invisibles et non modifiables), 39
(administrateur vs utilisateur normal, `update_user` limité à son compte),
26 (second prêt actif refusé).
## Les onze échecs, un par un

### 02 — la calculatrice reste entière (partiel)

    $ python3 main.py 7 2 divide
    Result: 3        # attendu 3.5

L'erreur de division par zéro est bien signalée (`Error: Division by zero is
not allowed.`), mais le corps calcule en `int`. Le prompt demande « a simple
command-line calculator that supports addition, subtraction, multiplication,
division » : `3` pour `7 / 2` est faux.

### 03 — la liste demande une saisie (échec)

    $ python3 main.py --list
    Task to add: Aborted!        # rc=1, aucun résultat

Le mode liste est inutilisable hors terminal interactif : il exige une saisie
avant d'afficher quoi que ce soit. Le prompt demande « a command-line tool
that lets me add and list tasks » ; `--list` doit lister.

### 14 — suppression dure au lieu d'une suppression logique (échec)

    $ python3 main.py project delete --id 1
    $ sqlite3 app.db 'SELECT * FROM projects'
    (aucune ligne)

Le projet disparaît au lieu de « rester dans la base » comme l'exige le
prompt. Le champ `deleted_at` existe pourtant dans le modèle (il apparaît dans
`project add --help`), mais il n'est pas utilisé par la suppression.

### 17 — aucune commande de création (échec)

    $ python3 main.py product --help
    Commands: filter  list  search  specify

Le prompt demande de « search by name, filter by category, specify a maximum
price and specify a minimum quantity » : ces quatre filtres existent et sont
combinables, mais aucune commande ne permet de créer un produit. Les filtres
ne peuvent donc jamais s'exercer sur des données — l'application est
incomplète.

### 18 — l'import CSV est inerte (partiel)

    $ python3 main.py contact export --filename /…/exported.csv   # rc=0, CSV correct
    $ cat incoming.csv
    id,first_name,last_name,email,…
    ,Bob,B,b@x.com,,…
    ,,,
    $ python3 main.py contact import --filename /…/incoming.csv
    rc=0 out=[] err=
    $ sqlite3 contacts.db 'SELECT * FROM contacts'
    ('Alice', 'A', 1, 1, 'a@x.com', …)        # ni Bob, ni message

L'export est conforme (en-tête complet, lignes correctes). L'import, lui,
s'exécute sans erreur, n'ajoute **pas** la ligne valide et ne **rejette pas**
la ligne invalide sans le dire. Le prompt est explicite : « Invalid rows during
import must be rejected without corrupting existing data » — ici aucune ligne
n'est traitée et rien n'est signalé. L'application ne satisfait donc ni la
partie import, ni la partie « rejected ».

### 19 — l'export JSON écrit un résumé, pas les tâches (échec, 3 vérifications)

    $ python3 main.py task add --title T1 --description D
    1
    $ python3 main.py task export --filename /…/tasks.json
    $ cat tasks.json
    {
      "total_tasks": 1,
      "completed_tasks": 0,
      "pending_tasks": 1,
      "overdue_tasks": 0
    }

Le prompt demande « commands to export all tasks to JSON and import tasks from
JSON » : le fichier produit est un tableau de bord (compteurs), pas la liste
des tâches. Conséquences en cascade : `task import` (qui attend des tâches) ne
restaure rien, et un fichier JSON volontairement invalide n'est pas rejeté —
même si, ici, l'échec de l'import est aussi dû à ce que l'export ne contient
pas de tâches.

### 20 — le rapport exige un identifiant sans objet (partiel)

    $ python3 main.py sale report --id 1
    {1: {'total': 50, 'count': 2}}      # total et nombre par produit : conforme
    $ python3 main.py sale report
    Error: Missing option '--id'.       # refusé

Le fond est bon (le rapport donne bien le montant **et** le nombre de ventes),
mais la commande impose un `--id` obligatoire que le prompt ne mentionne pas.
Le service appelé (`get_sale_report(self, id)`) ignore d'ailleurs ce
paramètre : il parcourt **toutes** les ventes et agrège par `product_id`.
L'option est donc un paramètre inventé, sans effet.

### 29 — le CLI parle SQLite en direct (partiel)

    $ grep -n "import sqlite3" generated/29/cli.py
    import sqlite3

Le découpage demandé existe (`models`, `note_repository`, `note_service`,
`cli`), mais la couche CLI ouvre elle-même la base, ce qui annule la séparation
entre présentation et persistance.

### 30 — dépôt non abstrait et CLI qui parle SQLite (échec, 2 vérifications)

    $ grep -rn "ABC\|Protocol" generated/30/*.py
    (aucune occurrence)
    $ grep -n "import sqlite3" generated/30/cli.py
    import sqlite3

Le prompt demande que la persistance soit derrière un contrat (« repository
interface ») : aucune classe abstraite ni `Protocol` n'existe, et le CLI
importe SQLite lui-même. L'architecture est donc plate, malgré des noms de
fichiers qui suggèrent le contraire.

### 35 — `bulk-update` ne peut pas ne changer que le stock (échec)

    $ python3 main.py product bulk-update --ids 1 --stock-quantity 9
    Error: Required field 'name' is missing.

Le prompt demande explicitement de pouvoir mettre à jour **plusieurs**
produits en ne modifiant **que** le stock. La commande impose le nom, si bien
qu'une mise à jour partielle est impossible : elle réécrit tous les champs.

### 40 — pas de création d'ordre et notification invisible (échec, 2 vérifications)

    $ python3 main.py order --help
    Commands: confirm  list  report      # aucune commande de création
    $ python3 main.py order confirm --id 1
    True                                 # mais aucun « notification » nulle part

Le groupe `order` n'offre aucune commande permettant de créer la commande à
confirmer : le scénario du prompt (confirmer une commande → notification) est
inatteignable par le CLI.
Le mécanisme de notification existe pourtant (`notifications.py` :
`LoggingNotificationService.notify` → `logging.getLogger("notifications")
.info(...)`) mais aucun handler ni niveau n'est configuré : le message est jeté
et rien n'apparaît dans `stdout`/`stderr`. Même en insérant la ligne en SQL,
la confirmation ne laisse aucune trace observable.

## Comparaison avec la lecture du 17/09

Le rapport précédent (`analysis/numbered_01_40_report.md`) lisait les sources
et les surfaces ; celui-ci exécute. Les écarts notables :

- **Conformes des deux côtés** : 01, 04–13, 15, 16, 21–28, 31–34, 36–39.
- **Nouvellement mesurés comme défaillants** (invisibles à la lecture) : 18
  (l'import « existe » mais ne fait rien), 19 (l'export « existe » mais écrit
  autre chose), 20 (le rapport exige un `--id` inutile), 22 (le service
  `get_order_report` ignore son `id` et agrège par produit — le total affiché
  reste correct, mais la méthode est fausse), 40 (la notification n'est jamais
  écrite).
- **Déjà connus et toujours présents** : 02 (division entière), 03 (saisie
  interactive), 14 (suppression dure), 17 (aucune création), 29/30 (SQLite dans
  le CLI, dépôt non abstrait), 35 (`bulk-update` non partielle).
- **Corrigés depuis, vérifiés ici** : 26 (prêt actif), 27 (chevauchement), 28
  (total calculé), 31 (découvert), 32 (transitions), 36 (catégorie
  référencée), 37 (cascade), 38 (propriété des documents), 39 (rôles).

## Reproduire

    # 1. régénérer les quarante arbres (≈ 1 h 45)
    for n in $(seq -w 1 40); do python3 agent.py --prompt $n; done

    # 2. sonder
    python3 analysis/state_01_40.py            # tout
    python3 analysis/state_01_40.py 18 19 40   # seulement quelques prompts

La sonde efface les `.db` du projet avant chaque prompt : les identifiants et
les totaux sont donc reproductibles. Elle lit la surface réelle de chaque
application (`<groupe> add --help`) pour remplir les options requises, afin de
ne pas mesurer ses propres suppositions sur les noms de champs.
