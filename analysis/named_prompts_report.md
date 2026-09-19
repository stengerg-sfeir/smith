# Prompts nommés — génération, fonctionnel, conformité

Chaque prompt nommé a été **régénéré** avec le générateur courant, puis
vérifié sur les deux axes demandés. La colonne *Génération* est le temps
mur de `agent.py --prompt <nom>`.

| prompt | génération (s) | marqueurs | compile | **fonctionnel** | **conforme** | façade |
|---|---|---|---|---|---|---|
| `cli_tool` | 11.8 | propre | OK | **PASS** | **PASS** | pass 5/5 |
| `expenses` | 406.7 | propre | OK | **PASS** | **PASS** | pass 14/14 |
| `hello_world` | 1.9 | propre | OK | **PASS** | **PASS** | no_mapped 0/0 |
| `inventory` | 244.5 | propre | OK | **PASS** | **PASS** | pass 11/11 |
| `library_system` | 255.0 | propre | OK | **PASS** | **PASS** | pass 9/9 |
| `multi_module` | 137.8 | propre | OK | **PASS** | **PASS** | pass 5/5 |

## `cli_tool`

- génération : **11.8 s** (exit 0)
- le prompt n'énumère pas de ligne de commande
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=pass pass=5/5

## `expenses`

- génération : **406.7 s** (exit 0)
- commandes énumérées par le prompt : 14 — `expense category add`, `expense category list`, `expense category update`, `expense category delete`, `budget list`, `budget add`, `budget update`, `budget delete`, `expense add`, `expense list`, `expense report monthly`, `expense report yearly`, `expense export`, `expense recurring detect`
- balayage de surface : 42 invocations
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=pass pass=14/14

## `hello_world`

- génération : **1.9 s** (exit 0)
- le prompt n'énumère pas de ligne de commande
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=no_mapped pass=0/0

## `inventory`

- génération : **244.5 s** (exit 0)
- commandes énumérées par le prompt : 11 — `product add`, `product list`, `product update`, `product delete`, `product restock`, `product report low-stock`, `product report value`, `category add`, `category list`, `category update`, `category delete`
- balayage de surface : 33 invocations
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=pass pass=11/11

## `library_system`

- génération : **255.0 s** (exit 0)
- commandes énumérées par le prompt : 9 — `library book add`, `library book list`, `library book search`, `library member add`, `library member list`, `library borrow`, `library return`, `library overdue`, `library member history`
- balayage de surface : 27 invocations
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=pass pass=9/9

## `multi_module`

- génération : **137.8 s** (exit 0)
- le prompt n'énumère pas de ligne de commande
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=pass pass=5/5

_Généré le 2026-09-19T09:07:10.875365+00:00._
