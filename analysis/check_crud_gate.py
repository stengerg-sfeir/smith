"""Prove the CRUD floor is gated on the literal token, and that it is the only
deterministic net for missing creation commands.

Loads the design dump of prompt 42 (NEUROSYM_DUMP_DESIGNS=/tmp/d42), then:
  * prints the designed METHODS per entity, so we see whether the LLM emitted a
    purchase-creation method at all;
  * runs ``_crud_floor`` with the REAL prompt text and with the same text plus
    the word "CRUD", and prints what the floor adds in each case.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/Users/gillesstenger/Documents/neurosymbolic")))
from agentlib.pipeline.cli_surface import _crud_floor  # noqa: E402

DUMP = Path("/tmp/d42/designs.json")
PROMPT = Path("/Users/gillesstenger/Documents/neurosymbolic/prompts/prompt_42.txt")

data = json.loads(DUMP.read_text(encoding="utf-8"))
entities = data["entities_by_class"]
designs = data["designs"]
prompt_text = PROMPT.read_text(encoding="utf-8")

print("=== entités conçues ===")
print(sorted(entities))

print("\n=== méthodes conçues, par classe ===")
for _path, klass, design in designs:
    methods = design.get("methods") if isinstance(design, dict) else None
    if methods:
        names = [
            str(m.get("name") or "") if isinstance(m, dict) else str(m)
            for m in methods
        ]
        print("%-12s %s" % (klass, sorted(names)))

print("\n=== _crud_floor, texte RÉEL de 42 (sans le mot CRUD) ===")
with_real = _crud_floor([], prompt_text, entities)
print("commandes ajoutées: %d" % len(with_real))
for command in with_real:
    print("   ", command.get("group"), command.get("name"))

print("\n=== _crud_floor, même texte + « Provide CRUD operations. » ===")
with_crud = _crud_floor([], prompt_text + "\nProvide CRUD operations.\n", entities)
print("commandes ajoutées: %d" % len(with_crud))
for command in with_crud:
    print("   ", command.get("group"), command.get("name"))
