# Agent Smith : Agent de génération de code Python neurosymbolique

**Agent Smith** est un agent de génération de code conçu pour produire des applications Python complètes, testées et robustes à partir de **petits modèles locaux (4B de paramètres)**.

---

Au lieu de reposer sur de gros LLM propriétaires en SaaS et sur des boucles lentes de correction après-coup (*post-hooks*), Agent Smith s'appuie sur une **architecture neurosymbolique** : il contraint strictement le LLM via un pipeline déterministe, des grammaires JSON (GBNF) et des validations AST dès la phase de génération.

---

## Pourquoi Agent Smith ?

Les assistants de code IA classiques traitent la génération comme un problème de texte libre. Avec des petits modèles locaux (comme Qwen 4B), cette approche échoue rapidement :
* **Erreurs de syntaxe :** Oublis d'imports ou indentation cassée.
* **Hallucinations d'API :** Inventions de méthodes ou de colonnes inexistantes.
* **Saturation de contexte :** Réinjecter les erreurs de linters dans le prompt consomme du contexte et dégrade le raisonnement.

**La solution :** Ne jamais laisser le LLM écrire un fichier entier en texte libre.

---

## Architecture Neurosymbolique

Agent Smith utilise le LLM uniquement pour la compréhension sémantique et la logique métier, tandis que le code déterministe (AST Python, rendu par templates) gère la structure exacte.

1. **Phase de Manifeste & Design :** Le LLM analyse le prompt utilisateur sous contrainte JSON pour extraire les entités, les signatures des services et les options de la CLI.
2. **Génération déterministe du squelette :** `agentlib` génère mécaniquement les modèles, la base de données SQLite et le routage de la CLI Click. Aucune hallucination possible sur la structure.
3. **Remplissage ciblé des stubs :** Le LLM est appelé uniquement pour remplir des fonctions métier isolées avec un contexte très étroit.
4. **Valideurs AST :** Les violations de noms ou de syntaxe sont corrigées au niveau de l'AST avant l'écriture du fichier.

---

## Installation & Utilisation

### Prérequis

**Python.** ≥ 3.10 pour le testeur (`bench.py`), ≥ 3.9 pour le générateur (`agent.py`).
Développé et mesuré sur CPython 3.14.5. Le détail des raisons est en commentaire dans les
deux fichiers de dépendances.

**Paquets.**

* `ruff` — le générateur exécute `ruff check --fix --select E,F,I,W` sur chaque projet
  produit. Dépendance *souple* (l'appel est protégé par un `try/except`), mais sans lui le
  code généré garde ses défauts d'ordre d'imports et d'imports inutilisés. Installé par
  [`requirements.txt`](requirements.txt).
* `click` — le testeur *exécute* les CLI générés (chacun étant une application click) dans
  le même interpréteur, donc l'environnement du testeur doit l'avoir. Installé par
  [`requirements-dev.txt`](requirements-dev.txt).

**Serveur LLM local**, compatible OpenAI, accessible sur `http://localhost:8000/v1`
(`llama-server`, `vLLM`, …). Version mesurée : **llama.cpp build `9430`** (commit
`d48a56eff`), installé par Homebrew sur macOS arm64, backend **Metal** activé :

```bash
brew install llama.cpp
llama-server --version      # version: 9430 (d48a56eff)
                            # built with AppleClang 21.0.0.21000099 for Darwin arm64
```

`server.sh` lance ce serveur (le modèle `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` est attendu à
la racine du dépôt) ; sur macOS il passe par `caffeinate`. Toutes les options qu'il utilise
(`--ctx-checkpoints`, `--cache-ram`, `--parallel`, `--log-file`, `--host`, `-sps`, `-ngl`,
`-ub`, `-c`, `-b`) sont acceptées par ce build ; `--cache-ram` et `--ctx-checkpoints` étant
récentes, prévois un build du même ordre de grandeur.

**Le modèle.** `server.sh` attend `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (2,33 Go) à la racine
du dépôt. Il est publié par **bartowski** ; le fichier distant porte un préfixe `Qwen_`,
d'où le `-o` qui le renomme au nom attendu :

```bash
curl -L -o Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
  https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

Contrôle d'intégrité (2 497 280 736 octets) :

```bash
shasum -a 256 Qwen3-4B-Instruct-2507-Q4_K_M.gguf
# 2fde00ce69dd4899c70d020845e2638353015bba0fdf161b3eb965f2bca4464e
```

Le fichier est ignoré par git (`.gitignore` : `*.gguf`), il n'est donc pas versionné.

### Installation

```bash
git clone git@github.com:stengerg-sfeir/smith.git
cd smith
python3 -m pip install -r requirements.txt        # générateur : ruff
```

Pour installer les outils de dev complémentaires (ajoute `click`, et reprend le
générateur) :

```bash
python3 -m pip install -r requirements-dev.txt    # testeur : ruff + click
```

### Exécution

**Générer une application à partir d'un prompt :**
L'entrée principale s'effectue via `agent.py` :

```bash
bash server.sh                            # dans un autre terminal : le serveur LLM
python3 agent.py --list                   # lister les prompts disponibles
python3 agent.py --prompt hello_world
```

**Lancer les suites d'évaluation et de benchmark :**
L'ensemble des outils de benchmark et de vérification est centralisé dans `bench.py`
(à lancer depuis la racine du dépôt) :

```bash
python3 bench.py --help
```

Le détail des quatorze commandes — ce que chacune teste, pourquoi, et comment la lancer
sur un prompt, un lot, ou tous — est dans **[`BENCH.md`](BENCH.md)**.

---

## Analyses & Documentation

Le dossier `analysis/` contient un ledger et des rapports datés :

* [`semantic_dispositions.md`](analysis/semantic_dispositions.md) — **le document de
  référence** : pour chaque défaut sémantique corrigé, le mécanisme qui l'empêche désormais
  de revenir et la mesure qui le prouve.
* [`convergence_plan.md`](analysis/convergence_plan.md) — la méthode du chantier (« une loi à
  la fois »), ses lois et ses preuves datées ; marqué clos.
* [`named_prompts_analysis.md`](analysis/named_prompts_analysis.md) — ce que les portes du
  harnais vérifient sur les six prompts nommés.
* [`named_prompts_report.md`](analysis/named_prompts_report.md) /
  [`named_prompts_report.json`](analysis/named_prompts_report.json) — le tableau des quatre
  axes, réécrit à chaque `bench.py named`.
* [`claude_vs_generator.md`](analysis/claude_vs_generator.md) — comparatif entre la baseline
  Claude Code et le générateur.
* [`claude_baseline_report.md`](analysis/claude_baseline_report.md) /
  [`claude_baseline_report_sonnet.md`](analysis/claude_baseline_report_sonnet.md) — les
  mesures brutes de cette comparaison (Haiku / Sonnet).
* [`small_model_trials.md`](analysis/small_model_trials.md) — trois modèles plus petits que
  le 4B de référence, et ce qu'ils révèlent.
* [`generation_cost_profile.md`](analysis/generation_cost_profile.md) — où passe le temps
  mural d'une génération.
