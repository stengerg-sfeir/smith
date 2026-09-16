"""Library of input fixtures for the facade tester.

The facade tester drives the generated CLI against external inputs (CSV to
convert, JSON to list, a note to process, ...). Rather than hard-coding a file
per prompt, the tester keeps a small LIBRARY of named fixtures, each described
semantically. The mapping stage (``facade_mapping``) gives the LLM this list
(id + description); the LLM picks the fixture(s) an intention needs. The
execution stage (``facade_executor``) then materialises those fixtures to a
real file on disk and substitutes its path into the CLI invocation.

This keeps the tester prompt-agnostic: the LLM chooses a fixture by semantic
description, and the tester only writes the content and passes the path.
"""

from __future__ import annotations

import json
from pathlib import Path


# kind -> file extension used when materialising
_EXT_BY_KIND = {
    "csv": ".csv",
    "json": ".json",
    "text": ".txt",
    "empty": ".txt",
}

# The fixture library. Each fixture:
#   id: unique name (used by the LLM and as the file stem)
#   kind: csv | json | text | empty
#   description: semantic description shown to the LLM (why an intention picks it)
#   data: the content. For kind "json" this is a Python object (list/dict);
#         for all other kinds it is a string written verbatim.
FIXTURES: dict[str, dict] = {
    "people_csv": {
        "id": "people_csv",
        "kind": "csv",
        "description": "A CSV table of people with columns: name, age, city.",
        "data": "name,age,city\nAlice,30,Paris\nBob,25,Lyon\n",
    },
    "products_csv": {
        "id": "products_csv",
        "kind": "csv",
        "description": "A CSV table of products with columns: product_id, name, "
                       "price, stock.",
        "data": "product_id,name,price,stock\n1,Widget,9.99,10\n2,Gadget,19.99,5\n",
    },
    "inventory_csv": {
        "id": "inventory_csv",
        "kind": "csv",
        "description": "A CSV table of inventory with columns: item, quantity, "
                       "location.",
        "data": "item,quantity,location\nApple,20,Shelf A\nBanana,10,Shelf B\n",
    },
    "expenses_csv": {
        "id": "expenses_csv",
        "kind": "csv",
        "description": "A CSV table of expenses with columns: id, date, amount, "
                       "category.",
        "data": "id,date,amount,category\n1,2024-01-01,12.50,Food\n"
                "2,2024-01-02,30.00,Transport\n",
    },
    "books_csv": {
        "id": "books_csv",
        "kind": "csv",
        "description": "A CSV table of books with columns: id, title, author.",
        "data": "id,title,author\n1,The Hobbit,Tolkien\n2,Dune,Herbert\n",
    },
    "items_json": {
        "id": "items_json",
        "kind": "json",
        "description": "A JSON array of items with fields: id, name, quantity.",
        "data": [{"id": 1, "name": "Apple", "quantity": 10},
                 {"id": 2, "name": "Banana", "quantity": 5}],
    },
    "tasks_json": {
        "id": "tasks_json",
        "kind": "json",
        "description": "A JSON array of tasks with fields: id, title, done.",
        "data": [{"id": 1, "title": "Write report", "done": False},
                 {"id": 2, "title": "Review PR", "done": True}],
    },
    "note_text": {
        "id": "note_text",
        "kind": "text",
        "description": "A free-form text note.",
        "data": "Remember to buy milk\nCall the plumber\n",
    },
    "empty_csv": {
        "id": "empty_csv",
        "kind": "csv",
        "description": "A CSV file with only a header row, no data rows.",
        "data": "name,age,city\n",
    },
    "malformed_csv": {
        "id": "malformed_csv",
        "kind": "csv",
        "description": "A malformed CSV file (empty, missing header) that should "
                       "produce an error when read.",
        "data": "",
    },
}


def fixture_listing(fixtures: dict[str, dict] | None = None) -> str:
    """A compact listing of fixture ids + descriptions for the LLM prompt."""
    lib = fixtures if fixtures is not None else FIXTURES
    lines = []
    for fx in lib.values():
        lines.append("%s (%s): %s" % (
            fx.get("id", ""), fx.get("kind", "text"), fx.get("description", "")))
    return "\n".join(lines)


def materialize_fixture(fx: dict, out_dir: Path | str) -> Path:
    """Write one fixture to ``out_dir`` and return its path.

    The file is named ``<id>.<ext>`` (ext from kind) and written as UTF-8.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ext = _EXT_BY_KIND.get(fx.get("kind", "text"), ".txt")
    path = out / ("%s%s" % (fx.get("id", "fixture"), ext))
    if fx.get("kind") == "json":
        data = fx.get("data")
        content = (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
                   if not isinstance(data, str) else data)
    else:
        content = fx.get("data", "")
    path.write_text(content, encoding="utf-8")
    return path


def materialize_fixtures(fixtures: dict[str, dict] | None,
                         used_ids: list[str], out_dir: Path | str) -> dict[str, Path]:
    """Materialise the fixtures whose ids appear in ``used_ids``.

    Returns ``{id: path}`` for every id that exists in the library. Unknown ids
    are silently skipped (the executor reports a warning via the result).
    """
    lib = fixtures if fixtures is not None else FIXTURES
    paths: dict[str, Path] = {}
    for fid in used_ids:
        fx = lib.get(fid)
        if fx is not None:
            paths[fid] = materialize_fixture(fx, out_dir)
    return paths
