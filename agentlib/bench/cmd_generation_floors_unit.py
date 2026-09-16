#!/usr/bin/env python3
"""Unit cases for the two deterministic post-generation floors.

`agentlib/generation/annotations.py` (annotate a valueless return `-> None`)
and `agentlib/generation/entrypoint.py` (add the `__main__` dispatch guard)
edit generated source as text, so they are the last place the generator can
corrupt a file that already compiles. These cases pin the two properties
that matter: each floor fires on exactly the shapes it targets, and it never
touches a file it should leave alone.

Usage: python3 run_generation_floors_unit.py
"""
import sys

from agentlib.generation.annotations import add_missing_none_returns
from agentlib.generation.entrypoint import ensure_entry_point

# (name, source, expected_additions, must_contain, must_not_contain)
ANNOTATION_CASES = [
    ("hello_world_main",
     'import click\n\n@click.command()\ndef main():\n    print("hi")\n',
     1, ["def main() -> None:"], []),
    ("returns_a_value", "def f():\n    return 1\n", 0, [], ["-> None"]),
    ("generator", "def g():\n    yield 1\n", 0, [], ["-> None"]),
    ("nested_only_inner",
     "def outer():\n    def inner():\n        pass\n    return inner\n",
     1, [], ["def outer() -> None"]),
    ("already_annotated", "def h() -> None:\n    pass\n", 0, [], []),
    ("multiline_signature_skipped", "def big(\n    a: int,\n):\n    pass\n",
     0, [], ["-> None"]),
    ("trailing_comment_skipped", "def c():  # note: nothing\n    pass\n",
     0, [], ["-> None"]),
    ("class_method", "class A:\n    def m(self):\n        pass\n",
     1, ["def m(self) -> None:"], []),
    ("docstring_body", 'def d():\n    """Doc."""\n', 1, ["def d() -> None:"], []),
    ("async_def", "async def a():\n    pass\n", 1, ["async def a() -> None:"], []),
    ("bare_return_is_none", "def b():\n    return\n", 1, ["def b() -> None:"], []),
    ("raise_only", "def r():\n    raise ValueError('x')\n",
     1, ["def r() -> None:"], []),
]

_CLICK = ("import click\n\n\n@click.command()\ndef main(x: str) -> None:\n"
          "    click.echo(x)\n")
_GROUP = "import click\n\n\n@click.group()\ndef cli() -> None:\n    pass\n"
_GUARD = '\n\nif __name__ == "__main__":\n    %s()\n'

# (name, files, expected_additions, must_contain)
ENTRY_POINT_CASES = [
    ("click_command_gets_guard", {"csv_to_json.py": _CLICK}, 1,
     ['if __name__ == "__main__":\n    main()']),
    ("click_group_gets_guard", {"cli.py": _GROUP}, 1,
     ['if __name__ == "__main__":\n    cli()']),
    ("already_guarded_untouched",
     {"cli.py": _CLICK + (_GUARD % "main")}, 0, []),
    ("no_click_command_untouched",
     {"helpers.py": "def helper(x: int) -> int:\n    return x\n"}, 0, []),
    ("main_py_gets_guard",
     {"main.py": "def main() -> None:\n    print('hi')\n"}, 1,
     ['if __name__ == "__main__":\n    main()']),
]


def _check_annotation_cases():
    failures = []
    for name, source, expected, contains, forbidden in ANNOTATION_CASES:
        files, added = add_missing_none_returns({"m.py": source})
        text = files["m.py"]
        if added != expected:
            failures.append("%s: added=%d expected=%d" % (name, added, expected))
            continue
        for needle in contains:
            if needle not in text:
                failures.append("%s: missing %r in %r" % (name, needle, text))
        for needle in forbidden:
            if needle in text:
                failures.append("%s: contains forbidden %r" % (name, needle))
        if added:
            compile(text, "m.py", "exec")

    once, _ = add_missing_none_returns({"m.py": "def z():\n    pass\n"})
    twice, added2 = add_missing_none_returns(once)
    if added2 != 0 or twice["m.py"] != once["m.py"]:
        failures.append("idempotence: second pass added=%d" % added2)

    files, added = add_missing_none_returns({"notes.txt": "def x():\n    pass\n"})
    if added != 0 or files["notes.txt"] != "def x():\n    pass\n":
        failures.append("non-py file was modified")
    return failures


def _check_entry_point_cases():
    failures = []
    for name, files, expected, needles in ENTRY_POINT_CASES:
        out, added = ensure_entry_point(dict(files))
        if added != expected:
            failures.append("%s: added=%d expected=%d" % (name, added, expected))
            continue
        for path, original in files.items():
            if added == 0 and out[path] != original:
                failures.append("%s: mutated a file it should not touch" % name)
            for needle in needles:
                if needle not in out[path]:
                    failures.append("%s: missing %r" % (name, needle))
            if added:
                compile(out[path], path, "exec")

    files, _ = ensure_entry_point({"notes.txt": _CLICK})
    if files["notes.txt"] != _CLICK:
        failures.append("non-py file was modified")

    once, _ = ensure_entry_point({"csv_to_json.py": _CLICK})
    twice, added2 = ensure_entry_point(once)
    if added2 != 0 or twice["csv_to_json.py"] != once["csv_to_json.py"]:
        failures.append("idempotence: second pass added=%d" % added2)
    return failures


def main(argv: list[str] | None = None):
    # This suite takes no options; the argument exists so bench.py can dispatch
    # to every suite uniformly.
    annotation_failures = _check_annotation_cases()
    entry_point_failures = _check_entry_point_cases()

    if annotation_failures:
        print("annotation floor: FAIL (%d)" % len(annotation_failures))
        for line in annotation_failures:
            print("  - %s" % line)
    else:
        print("annotation floor: %d/%d cases pass"
              % (len(ANNOTATION_CASES), len(ANNOTATION_CASES)))

    if entry_point_failures:
        print("entry-point guard: FAIL (%d)" % len(entry_point_failures))
        for line in entry_point_failures:
            print("  - %s" % line)
    else:
        print("entry-point guard: %d/%d cases pass"
              % (len(ENTRY_POINT_CASES), len(ENTRY_POINT_CASES)))

    if annotation_failures or entry_point_failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
