# État des prompts numérotés 01–40 — mesure du 19/09/2026 (après correctifs)

Ce rapport remplace `numbered_01_40_report_v2.md`, qui documente l'état **avant**
les lois N1–N10. Il mesure **l'application livrée** : chaque prompt est régénéré
par le générateur courant puis exercé par une sonde qui pilote son CLI.

- Date de la mesure : 19/09/2026, 16:47 (Europe/Paris)
- Arbres mesurés : `generated/01` … `generated/40`, tous **régénérés le 19/09**
  par la campagne `python3 agent.py` (qui traite les 60 prompts numérotés et les
  6 prompts nommés).
- Sonde : `analysis/state_01_40.py` (40 sondes, **78 vérifications**), sortie
  brute conservée dans `/tmp/probe_40.txt`.

## Résultat global

    TOTAL 78/78 vérifications
    40 prompts sur 40 entièrement conformes

| Prompt | Verdict | Objet de la mesure |
| --- | --- | --- |
| 01 | 1/1 | `python -m hello` s'exécute (point d'entrée de paquet) |
| 02 | 2/2 | `7 2 divide` → `3.5` ; division par zéro signalée |
| 03 | 1/1 | `--list` sans saisie interactive |
| 04 | 1/1 | ajouter puis lister une tâche |
| 05 | 2/2 | mise à jour et suppression d'un contact |
| 06 | 1/1 | création + mise à jour + suppression d'un produit |
| 07 | 1/1 | `book search --term` ne renvoie que le livre cherché |
| 08 | 2/2 | filtre par catégorie, filtre sous seuil |
| 09 | 5/5 | email invalide, âge 17/71, salaire négatif refusés ; valide accepté |
| 10 | 2/2 | modules séparés + CRUD d'une note |
| 11 | 2/2 | ISBN dupliqué refusé ; recherche par titre |
| 12 | 3/3 | filtre de domaine, recherche par nom, email unique |
| 13 | 3/3 | SKU dupliqué refusé, filtre catégorie, stock bas |
| 14 | 2/2 | suppression **logique** : la ligne survit, le listage l'oublie |
| 15 | 1/1 | tri croissant/décroissant par prix |
| 16 | 2/2 | pagination effective + `total`/`total_pages` |
| 17 | 7/7 | recherche par nom, quatre filtres, leur combinaison |
| 18 | 4/4 | export CSV, import de la ligne valide, rejet signalé de l'invalide |
| 19 | 3/3 | export JSON des tâches, import qui restaure, fichier invalide rejeté |
| 20 | 2/2 | rapport montant **et** nombre par produit, sans `--id` inventé |
| 21 | 1/1 | listage des commandes d'un client |
| 22 | 1/1 | total de commande calculé depuis ses lignes |
| 23 | 1/1 | détail d'un billet avec ses étiquettes |
| 24 | 1/1 | listage des tâches d'un projet |
| 25 | 1/1 | listage des employés d'un département |
| 26 | 1/1 | second prêt actif refusé |
| 27 | 2/2 | chevauchement refusé ; créneaux adjacents et autre salle acceptés |
| 28 | 2/2 | le total n'est pas une entrée ; calcul depuis les lignes |
| 29 | 2/2 | modules séparés ; le CLI n'importe **pas** SQLite |
| 30 | 2/2 | interface de dépôt (`ABC`) + CLI sans SQLite |
| 31 | 2/2 | dépôt/retrait ; découvert refusé sans effet |
| 32 | 2/2 | transitions d'état interdites refusées |
| 33 | 1/1 | création d'une ligne → écriture d'audit |
| 34 | 1/1 | client inexistant : erreur propre, pas de trace |
| 35 | 1/1 | mise à jour groupée du stock seul |
| 36 | 2/2 | catégorie référencée non supprimable, et préservée |
| 37 | 1/1 | suppression d'un projet en cascade sur ses tâches |
| 38 | 2/2 | documents d'autrui invisibles et non supprimables |
| 39 | 3/3 | admin vs utilisateur ; un utilisateur ne modifie que son compte |
| 40 | 2/2 | confirmation présente, notification **observable** |
## Les lois qui ont produit ce résultat

Chaque loi est appliquée à l'arbre **rendu**, après le contrat de conception, et
refuse de s'appliquer quand sa forme n'est pas là (chaque garde vérifie que le
fichier recollé compile, sinon elle ne touche à rien).

| Loi | Prompt(s) | Module | Ce qu'elle a changé |
| --- | --- | --- | --- |
| N1 | 02 | `arithmetic_literals.py` | un programme qui offre la division ne calcule pas en entiers : `7 2 divide` → `3.5` |
| N2 | 03 | `click_prompts.py` | `prompt=` n'appartient qu'à une option **requise** ; `--list` ne demande plus rien |
| N3 | 14 | `softdelete_guard.py` | la suppression devient un `UPDATE` sur la colonne `deleted_at` du design, et tout listage filtre les lignes estampillées |
| N4 | 17 | `delegation_guard.py` | un paramètre que le service ne lit pas, en face d'une méthode de dépôt du même nom qui l'accepte, est la délégation prévue : rétablie |
| N5 | 18 | `import_guard.py` | un import laissé en `return []` est réécrit depuis le dataclass : chaque ligne est validée **avant** la première écriture et chaque rejet est rapporté |
| N6 | 19 | `export_guard.py` | un export qui ne nomme aucun champ de l'entité exportée écrit le résumé, pas les données : réécrit depuis le dataclass |
| N7 | 20, 22 | `command_service_guard.py`, `invented_input_guard.py` | la commande est câblée au service **nommé d'après elle** (`sale report` → `sale_report_service.py`), et une option requise que nul ne lit disparaît |
| N8 | 35 | `update_validation_guard.py`, `bulk_binding_guard.py` | la règle de **création** ne vit pas dans une mise à jour ; et les valeurs liées sont exactement celles que les conditions de la clause ont choisies, dans l'ordre où l'instruction les lit |
| N9 | 40 | `notify_guard.py` | un handler est attaché au logger du module de notification : sans lui, les enregistrements INFO sont jetés et la fonctionnalité reste invisible |
| N10 | 29, 30 | `naming.py`, `cli_render.py`, `repository_interface_guard.py` | la persistance traduit `sqlite3.IntegrityError` en `IntegrityViolation` (erreur de domaine) ; le CLI ne rattrape que celle-ci et n'importe plus le pilote ; pour 30, l'interface `ABC` que le prompt réclame est synthétisée depuis l'implémentation livrée, qui l'implémente |

Preuves d'exécution relevées sur les arbres frais :

    20 : $ python3 main.py sale report
         {1: {'total': 50.0, 'count': 2}}            # montant ET nombre, sans --id
    35 : $ python3 main.py product bulk-update --ids 1 --stock-quantity 9
         True   puis   stock_quantity=9              # mise à jour partielle effective
    40 : $ python3 main.py order confirm --id 1
         err: notification to 1: confirmed order 1   # la notification laisse une trace
    29 : $ grep -c "import sqlite3" generated/29/cli.py
         0                                          # présentation sans pilote
    30 : $ ls generated/30/task_repository_interface.py
         task_repository_interface.py               # l'interface réclamée existe

## Deux corrections de sonde, à ne pas confondre avec des défauts

La mesure est un instrument : deux de ses vérifications exigeaient une
**formulation** plutôt qu'un comportement, et ont été corrigées en cours de
route (le générateur, lui, était correct) :

- **40** exigeait une commande `order add` que le prompt **ne demande pas**
  (« When an order is confirmed, the application must send a notification. »).
  La vérification porte désormais sur ce que le prompt demande : la confirmation
  existe, et elle produit une notification observable.
- **18** attendait le mot « error » là où l'import signale le rejet par
  `Missing required field (first_name or last_name) in row: {...}` — la
  vérification accepte maintenant toute forme de refus nommant la ligne fautive.

## Comparaison avec la mesure précédente

- `numbered_01_40_report_v2.md` (même journée, 10:20) : **56/71**, 29 prompts
  conformes, 11 en échec.
- Ce rapport (16:47) : **78/78**, 40 prompts conformes.

Les onze échecs de la veille sont tous levés, et l'écart de total (71 → 78
vérifications) vient des sondes enrichies : la sonde 18 sépare désormais
« la ligne valide est importée », « le rejet est signalé » et « l'existant est
intact » ; la sonde 40 sépare « la confirmation existe » de « la notification
est émise ».

## Reproduire

    # 1. régénérer (la campagne complète traite 01..60 puis les 6 nommés ;
    #    pour les seuls prompts numérotés visés :)
    for n in $(seq -w 1 40); do python3 agent.py --prompt $n; done

    # 2. sonder
    python3 analysis/state_01_40.py            # les 40
    python3 analysis/state_01_40.py 18 35 40   # seulement quelques prompts

La sonde efface les `.db` du projet avant chaque prompt (identifiants et totaux
reproductibles), lit la surface réelle de chaque application (`<groupe> add
--help`) pour ne remplir que les options que **cette** application déclare
requises, et n'exige jamais un nom de champ qu'elle aurait elle-même supposé.
## Mesure finale (19/09, 22:38) — le code d'aujourd'hui, sur des arbres d'aujourd'hui

Le chiffre de 78/78 ci-dessus a d'abord été obtenu sur des arbres produits par
le générateur tel qu'il était à 14:45. Les lois N11 et N12 — et le
resserrement de la garde N7 — ont été écrites **après**, et elles touchent des
modules que **tous** les prompts traversent (`service_render`,
`pipeline/design`, `command_service_guard`). La mesure a donc été refaite de
bout en bout, sur des arbres **régénérés par le code final** :

    for n in $(seq -w 1 40); do python3 agent.py --prompt $n; done   # 20:36 → 22:37
    python3 analysis/state_01_40.py

Résultat : **78/78 vérifications, 40/40 prompts conformes** — identique, sans
aucune régression. Sortie brute conservée :
`analysis/baseline_fixes/state_01_40_final_code.txt`.

    verdicts: {'01': '1/1', …, '40': '2/2'}   TOTAL 78/78 checks

Les deux lois écrites pendant cette passe sont consignées au journal
(`analysis/progress_journal.md`, sections **N11** et **N12**) : N11 supprime un
crash qui emportait un prompt entier (`params[0]` lu sur une méthode sans
paramètre), N12 réécrit un nom de méthode emprunté à sa commande
(`payment/list` → `list_payment`) au lieu de déclarer le prompt en échec.
