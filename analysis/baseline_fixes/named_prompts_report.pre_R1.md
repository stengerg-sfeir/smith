# Prompts nommés — génération, fonctionnel, conformité

Chaque prompt nommé a été **régénéré** avec le générateur courant, puis
vérifié sur les deux axes demandés. La colonne *Génération* est le temps
mur de `agent.py --prompt <nom>`.

| prompt | génération (s) | marqueurs | compile | **fonctionnel** | **conforme** | façade |
|---|---|---|---|---|---|---|
| `cli_tool` | 14.2 | propre | OK | **PASS** | **PASS** | no_result ?/? |
| `expenses` | 399.5 | propre | OK | **PASS** | **PASS** | no_result ?/? |
| `hello_world` | 2.0 | propre | OK | **PASS** | **PASS** | no_result ?/? |
| `inventory` | 244.8 | propre | OK | **PASS** | **PASS** | no_result ?/? |
| `library_system` | 223.5 | propre | OK | **PASS** | **PASS** | no_result ?/? |
| `multi_module` | 141.6 | propre | OK | **PASS** | **PASS** | no_result ?/? |

## `cli_tool`

- génération : **14.2 s** (exit 0)
- le prompt n'énumère pas de ligne de commande
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=no_result pass=None/None

## `expenses`

- génération : **399.5 s** (exit 0)
- commandes énumérées par le prompt : 14 — `expense category add`, `expense category list`, `expense category update`, `expense category delete`, `budget list`, `budget add`, `budget update`, `budget delete`, `expense add`, `expense list`, `expense report monthly`, `expense report yearly`, `expense export`, `expense recurring detect`
- balayage de surface : 42 invocations
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=no_result pass=None/None

## `hello_world`

- génération : **2.0 s** (exit 0)
- le prompt n'énumère pas de ligne de commande
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=no_result pass=None/None

## `inventory`

- génération : **244.8 s** (exit 0)
- commandes énumérées par le prompt : 11 — `product add`, `product list`, `product update`, `product delete`, `product restock`, `product report low-stock`, `product report value`, `category add`, `category list`, `category update`, `category delete`
- balayage de surface : 33 invocations
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=no_result pass=None/None

## `library_system`

- génération : **223.5 s** (exit 0)
- commandes énumérées par le prompt : 9 — `library book add`, `library book list`, `library book search`, `library member add`, `library member list`, `library borrow`, `library return`, `library overdue`, `library member history`
- balayage de surface : 27 invocations
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=no_result pass=None/None

## `multi_module`

- génération : **141.6 s** (exit 0)
- le prompt n'énumère pas de ligne de commande
- marqueurs interdits : aucun
- compile : OK
- **fonctionnel** : PASS
- **conforme** : PASS
- façade (contrôle indépendant, piloté par LLM) : status=no_result pass=None/None

_Généré le 2026-09-17T09:33:14.884876+00:00._
