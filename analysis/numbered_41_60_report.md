# État des prompts numérotés 41–60 (mesure du 20/09, générateur inchangé)

Mesure demandée : **régénérer 41–60 (59 exclu) puis retester fonctionnalité et
conformité**. Aucune ligne du générateur n'a été touchée ; le seul ajout est
l'instrument de mesure `analysis/state_41_60.py`.

## Deux lectures, et pourquoi elles donnent deux verdicts

Une remarque juste a été faite : **« ce que le prompt ne spécifie pas n'est pas un
défaut »**. Elle oblige à séparer deux questions :

1. **Lecture littérale** — les énoncés du prompt sont-ils vrais du logiciel livré ?
   (« un livre emprunté ne doit pas apparaître disponible » : oui ou non.)
2. **Lecture inférentielle** — les verbes de gestion du prompt (« manage »,
   « keep track of », « X contient Y ») impliquent-ils de pouvoir **enregistrer**
   X ? Cette inférence n'est pas écrite dans le prompt : c'est un choix
   d'interprétation.

Les deux verdicts sont donnés séparément ci-dessous. Le premier est un fait sur
le code livré ; le second dépend de la lecture qu'on adopte.

## Verdict littéral : 10 prompts sur 19

Les énoncés du prompt **tiennent** pour :

| # | Énoncé du prompt | Ce qui le rend vrai |
|---|------------------|---------------------|
| 42 | « trouver l'historique d'achat d'un client et savoir combien il a dépensé » | `purchase list --customer-id` (l'historique) et `customer report --id 1` → `{'customer': {...}, 'purchases': []}` (« combien il a dépensé ») |
| 43 | « voir ce qui demande attention » | `task list --priority … --status …` (filtres présents) |
| 44 | « savoir ce qui a été vendu et ce qui reste en stock » | `sale list --sale-date-from/--customer-id/--product-id` ; quantité en stock lisible sur le produit |
| 45 | « ne pas réserver deux fois la même chambre pour la même période » | refus effectif (contrainte `UNIQUE(check_in_date, check_out_date, room_id)`) |
| 46 | « savoir quelles factures restent dues » | `invoice list --status …` + `payment add` qui y remonte |
| 47 | « voir qui est responsable de quoi » | `person assign` + `task list --project-id/--status` (mécanisme d'affectation présent) |
| 48 | « ajouter, trouver, organiser ; se souvenir entre exécutions » | `book add/search` + champ de classement + données survivant au processus suivant |
| 49 | « savoir quels employés appartiennent à quels départements ; trouver un employé vite » | `employee list --department-id` et `--first-name/--last-name` |
| 51 | « SKU unique par produit, mais SKU partageable entre catégories » | exactement les deux règles, et elles mordent |
| 57 | « la CLI reste indépendante de la persistance » | service + dépôt séparés, la CLI n'importe ni `sqlite3` ni le dépôt |

## Verdict littéral : 9 prompts en violation

Ici le prompt **dit** quelque chose que le logiciel ne fait pas :

| # | Énoncé du prompt | Ce que le logiciel fait | Preuve |
|---|------------------|-------------------------|--------|
| 41 | « permettre de savoir quels livres sont disponibles » | un livre emprunté reste annoncé disponible | `loan add` rc=0 (1 ligne dans `loans`), `books.available_copies` reste **1** |
| 50 | « les gens doivent pouvoir s'inscrire à un événement » | l'inscription échoue **toujours** | `registration add --event-id 1 --person-id 1` → `Error: FOREIGN KEY constraint failed` (3/3) |
| 52 | « un livre emprunté ne doit pas apparaître disponible, et redevenir disponible au retour » | il n'existe **aucune** vue des livres | `book` = `add`, `return` (pas de `list`) : l'état n'est pas observable |
| 53 | « les commandes contiennent des produits ; stock insuffisant refusé ; stock décrémenté » | une commande ne peut pas contenir de produit | `order add --help` → `['--customer-id', '--help']` ; `order_item` = `update` seul |
| 54 | « les rendez-vous ont un début et une fin ; la fin suit le début » | aucune option d'heure nulle part | `appointment add`/`update` → `['--title', '--description', '--is-active', '--help']` |
| 55 | « l'inventaire ne doit jamais devenir incorrect » | la vente **ne décrémente pas** le stock, et la survente passe | stock 5 → `sale add --quantity 2` rc=0 → stock **5** ; `--quantity 100` rc=0 |
| 56 | « les commandes contiennent des produits ; annuler doit restaurer les quantités » | idem 53 | `order add` sans produit ; aucune commande de ligne (`line=None`) |
| 58 | « récupérer des informations client auprès d'un service externe » | aucune commande ne le fait | groupe `customer` = `list`, `report` |
| 60 | « les administrateurs gèrent produits et catégories ; les clients passent des commandes contenant plusieurs produits ; confirmer réserve le stock ; une facture est créée à la confirmation » | ni `product add` ni `order add` ; `category add` **plante** | `product` = `list/search/update` ; `order` = `cancel/confirm/list` ; `category add --name C1` → `sqlite3.ProgrammingError: Incorrect number of bindings supplied` |

## Ce qui n'est un défaut que sous la lecture inférentielle

Ces prompts **nomment** une entité à gérer, mais l'application n'offre pas de
commande pour l'**enregistrer** ; leurs énoncés littéraux, eux, tiennent :

| # | Verbe du prompt | Capacité littérale | Ce qui manque (inféré) |
|---|-----------------|--------------------|------------------------|
| 42 | « gérer les clients et leurs achats » | historique et dépense atteignables | pas de `purchase add` — donc ces vues ne pourront jamais rien montrer |
| 43 | « les projets contiennent des tâches » | filtres priorité/statut | pas de `task add` |
| 44 | « suivre produits, clients et ventes » | `sale list` filtrable | pas de `sale add` |
| 47 | « l'équipe a besoin de projets, tâches et personnes » | affectation | pas de `person add` ni `task add` |
| 49 | « gérer les employés » | filtre par département | pas de `employee add` |
| 57 | « gérer des documents » | séparation CLI/persistance ✔ | `document add` échoue : `NOT NULL constraint failed: documents.file_path` (colonne NOT NULL, option optionnelle) |

## Défauts qui ne dépendent d'aucune lecture

- **60** : `category add --name C1` **plante** (`sqlite3.ProgrammingError:
  Incorrect number of bindings supplied`) — un plantage n'est jamais conforme.
- **57** : `document add` remonte une **erreur SQL brute** à l'utilisateur.
- **50** : l'échec d'inscription est une `FOREIGN KEY constraint failed`
  non traitée, répétée pour chaque tentative.

## Mesure fonctionnelle, pour mémoire

    verdicts: 41:3/4  42:2/4  43:2/3  44:3/4  45:3/3  46:4/4  47:1/3  48:4/4
              49:1/3  50:4/5  51:3/3  52:1/3  53:0/1  54:0/1  55:2/4  56:1/2
              57:2/3  58:1/3  60:0/2
    TOTAL 37/59 checks

Ces 37/59 comptent les vérifications **inférentielles** (ex. « une tâche peut
être créée ») au même rang que les littérales ; c'est ce mélange qui faisait
paraître le lot plus faible qu'il n'est. Le verdict littéral est le tableau
ci-dessus : **10 prompts sur 19**.

## Portée et honnêteté de l'instrument

- Les suites déterministes du dépôt (`cli-conformity`, `repo-conformity`,
  `surface`) **ne s'appliquent pas** à ce lot : aucune spécification 41–60
  n'énumère de ligne de commande (« No prompt enumerates a command line. »).
- Chaque échec a été revérifié à la main (`--help` de chaque commande **et**
  exécution directe) : les écarts de nommage de la sonde ont été corrigés, pas
  comptés comme défauts.
- **59** est exclu à la demande (génération en échec à l'échelle, voir
  `analysis/progress_journal.md`).

## Reproduire

    python3 analysis/state_41_60.py               # les 19 sondes
    python3 analysis/state_41_60.py 42 43 44 45 46 48 49 51 57   # les conformes

Sortie brute : `analysis/baseline_fixes/state_41_60.txt`.
