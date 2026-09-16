# Agent Smith : Agent de génération de code Python neurosymbolique

**Agent Smith** est un agent de génération de code conçu pour produire des applications Python complètes, testées et robustes à partir de **petits modèles locaux (4B de paramètres)**.

Au lieu de reposer sur de gros LLM propriétaires en SaaS et sur des boucles lentes de correction après-coup (*post-hooks*), Agent Smith s'appuie sur une **architecture neurosymbolique** : il contraint strictly le LLM via un pipeline déterministe, des grammaires JSON (GBNF) et des validations AST dès la phase de génération.

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

* Python 3.10+
* Un serveur LLM local compatible OpenAI (ex. `llama-server` ou `vLLM`) accessible sur `http://localhost:8000/v1`.

### Installation

```bash
git clone git@github.com:stengerg-sfeir/smith.git
cd smith
pip install -r requirements.txt
```

Pour installer les outils de dev complémentaires :

```bash
pip install -r requirements-dev.txt
```

### Exécution

**Générer une application à partir d'un prompt :**
L'entrée principale s'effectue via `agent.py` :

```bash
python agent.py --prompt hello_world
```

**Lancer les suites d'évaluation et de benchmark :**
L'ensemble des outils de benchmark et de vérification est centralisé dans `bench.py` :

```bash
python bench.py --help
```

---

## Analyses & Documentation

Des rapports détaillés et des analyses d'architecture sont maintenus dans le dossier `analysis/` :
* `agent_architectural_analysis.md` : Analyse de la structure globale de l'agent.
* `claude_vs_generator.md` : Comparatif entre la baseline Claude et le générateur.
* `semantic_problems.md` : Cartographie des défauts sémantiques et comportementaux.
* `semantic_dispositions.md` : Stratégies de correction et évolutions du kernel.
