# État des prompts numérotés 41–60 (mesure du 20/09, sans modification du générateur)

Mesure demandée : **régénérer 41–60 (59 exclu) puis retester fonctionnalité et
conformité**. Aucune ligne du générateur n'a été touchée ; le seul ajout est
l'instrument de mesure `analysis/state_41_60.py`.

## Ce qui a été fait

1. Régénération de **41..58 et 60** avec le générateur en l'état
   (`python3 agent.py --prompt N`), 19 prompts, arbres neufs dans `generated/`.
2. Écriture d'une sonde fonctionnelle `analysis/state_41_60.py` : une sonde par
   prompt, qui pilote la CLI LIVRÉE et n'affirme que ce que le prompt énonce.
   Elle réutilise les assistants de `analysis/state_01_40.py`.
3. Triage de chaque échec contre la surface réelle de l'application
   (`--help` de chaque groupe et de chaque commande) **et** par exécution
   directe, pour ne pas publier un artefact de nommage comme un défaut.

## Résultat global

    verdicts: 41:3/4  42:2/4  43:2/3  44:3/4  45:3/3  46:4/4  47:1/3  48:4/4
              49:1/3  50:4/5  51:3/3  52:1/3  53:0/1  54:0/1  55:2/4  56:1/2
              57:2/3  58:1/3  60:0/2
    TOTAL 37/59 checks

**Conformes (le prompt est satisfait)** : **45, 46, 48, 51** — et pour l'essentiel
41, 44 (création de l'entité exceptée), 57, 50.

**Non conformes, avec la cause vérifiée** : **42, 43, 47, 49, 52, 53, 54, 55, 56,
58, 60** — et partiellement 41, 50, 57.

La différence avec 01–40 (**78/78**) est frappante et a une cause unique :
**ces 19 prompts ne sont pas, pour la plupart, « servis » par une commande de
création pour les entités qu'ils nomment.** L'application reçoit souvent la
vue (liste, rapport, recherche) mais pas le geste qui remplit.

## Défauts constatés, avec la preuve

| # | Ce que le prompt exige | Ce que l'application livre | Preuve |
|---|------------------------|---------------------------|--------|
| 41 | « savoir quels livres sont disponibles » | un livre emprunté reste `available_copies=1` | `loan add` rc=0, table `loans` à 1 ligne, `books.available_copies` inchangé |
| 42 | suivre les achats d'un client | groupe `purchase` = `list`, `total` ; **pas de `add`** | `no add command` ; `purchase total --id 1` → `Purchase with id 1 not found` |
| 43 | « les projets contiennent des tâches » | groupe `task` = `list`, `report`, `update` ; **pas de `add`** | idem |
| 44 | suivre les ventes | groupe `sale` = `list` seul ; **pas de `add`** | idem |
| 47 | projets, tâches **et personnes** | `person` = `assign`, `list` ; `task` = `assign`, `list` ; **aucun `add`** | idem |
| 49 | gérer les employés | `employee` = `list` seul ; **pas de `add`** ; pas de filtre par département | idem |
| 50 | inscrire des personnes à un événement | `registration add --event-id 1 --person-id 1` échoue pour **toutes** les tentatives | `Error: FOREIGN KEY constraint failed` (aucune commande ne crée la personne référencée) |
| 52 | « un livre emprunté n'apparaît pas disponible » | `book` = `add`, `return` ; **pas de `list`** → l'état n'est pas observable | `book commands=['add', 'return']` |
| 53 | une commande contient des produits, stock vérifié | `order add --customer-id` seul ; `order_item` = `update` seul | `order add --help` → `['--customer-id', '--help']` |
| 54 | les rendez-vous ont un début et une fin | `appointment add`/`update` sans aucune option d'heure | `options=['--title', '--description', '--is-active', '--help']` |
| 55 | « l'inventaire ne doit jamais devenir incorrect » | une vente **ne décrémente pas** le stock et une vente de 100 sur un stock de 5 est **acceptée** | stock 5 → `sale add --quantity 2` rc=0 → stock **5** ; `--quantity 100` rc=0 |
| 56 | les commandes contiennent des produits | `order add --customer-id --status --cancelled-at` ; aucune commande de ligne | `order add --help` ; `line=None` |
| 57 | CLI indépendante de la persistance | — (cette exigence est **tenue**) mais `document add` échoue | `Error: NOT NULL constraint failed: documents.file_path` (colonne NOT NULL, option optionnelle) |
| 58 | interroger un service externe | groupe `customer` = `list`, `report` ; **pas de `add`**, aucune commande d'appel externe | idem |
| 60 | gérer produits, catégories, commandes | `product` = `list`, `search`, `update` ; `order` = `cancel`, `confirm`, `list` ; **aucun `add`** ; `category add` **plante** | `sqlite3.ProgrammingError: Incorrect number of bindings supplied` |

Les cas 50, 55 et 60 montrent un second motif : quand la commande existe, elle
**ne relie pas** ce qu'elle prétend relier (clé étrangère non satisfiable,
stock non mis à jour) ou **plante** sur un défaut de liaison SQL.

## Ce qui est conforme, et pourquoi c'est notable

- **45** : réservation de chambre avec refus du chevauchement (contrainte
  `UNIQUE(check_in_date, check_out_date, room_id)`) — la règle du prompt est
  tenue, par la base plutôt que par le service, mais tenue.
- **46** : `invoice add` / `list --status` / `mark` / `report` + `payment add` ;
  « quelles factures restent dues » est atteignable et le paiement y remonte.
- **48** : ajouter, chercher, organiser (genre), et la donnée survit au
  processus suivant.
- **51** : unicité du SKU **par catégorie** (le même SKU passe dans une autre
  catégorie) — exactement la double règle demandée.

## Portée de la mesure (franchise sur l'instrument)

- Les suites de conformité déterministes du dépôt (`bench.py cli-conformity`,
  `repo-conformity`, `surface`) **ne s'appliquent pas** à ce lot : aucune des
  spécifications 41–60 n'énumère de ligne de commande, donc elles répondent
  « No prompt enumerates a command line. ». La sonde fonctionnelle est ici le
  seul instrument.
- La sonde cherche les capacités **sur la surface de l'application** (nom de
  commande, options) au lieu de les coder en dur ; chaque échec rapporté
  ci-dessus a été revérifié à la main (`--help` + exécution) avant d'être
  classé. Les limites de l'instrument sont donc exclues du verdict.
- **59** est exclu à la demande : sa génération échoue à l'échelle (troncature
  du remplissage à 8192 tokens dans la boucle de réparation — voir
  `analysis/progress_journal.md`).

## Reproduire

    python3 analysis/state_41_60.py            # les 19 sondes
    python3 analysis/state_41_60.py 45 46 48 51  # les quatre conformes

Sortie brute conservée : `/tmp/state_41_60_final2.txt` (à archiver sous
`analysis/baseline_fixes/state_41_60.txt` si l'on veut la garder au dépôt).
