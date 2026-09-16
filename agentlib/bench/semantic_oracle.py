"""Executed semantic oracle for a generated project (stage 4).

Two independent sources of truth, deliberately kept apart:

  * DESIGN-derived invariants are computed from the generated tree itself
    (models + repositories + the service signature set): a create/get
    round-trip per entity, the element type of every repository listing and
    of every ``list_<E>`` / ``get_<E>s`` service method. They never read the
    specification.

  * SPEC-derived invariants are written per project from the prompt's own
    statements, with concrete data ("after borrow then return,
    available_copies is back to 2"). They never read the implementation.

Because the two families are produced from disjoint inputs, a body cannot be
tuned to satisfy both by construction -- and every invariant is EXECUTED
against the generated package, not pattern-matched in its source.

Usage:
    python3 -m agentlib.bench.semantic_oracle --project library_system
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import sys
import tempfile
import traceback
from pathlib import Path

_DESIGN = "design"
_SPEC = "spec"

# Top-level module names a generated project defines. They are cached in
# ``sys.modules`` under bare names, so loading a SECOND project in the same
# process would silently reuse the FIRST one's ``models`` (expenses' Budget
# imported from library_system's models.py).
_PROJECT_MODULE_NAMES = ("models", "database", "exceptions", "cli")

# Project directories this process has put on ``sys.path``, newest last.
_LOADED_PROJECT_DIRS = []


def _is_project_module(name):
    base = name.split(".")[0]
    return (
        base in _PROJECT_MODULE_NAMES
        or base.endswith("_repository")
        or base.endswith("_service")
    )


def _model_fields(models_py: Path) -> dict:
    """{Class: [ {name, type, nullable, has_default} ]} read from models.py AST.

    Reading the AST (not the imported class) keeps the invariant independent
    of the runtime module surface and works whether or not the file uses
    ``from __future__ import annotations``.
    """
    out = {}
    tree = ast.parse(models_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields = []
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign) or not isinstance(
                stmt.target, ast.Name
            ):
                continue
            anno = ast.unparse(stmt.annotation)
            base = anno.replace("Optional[", "").replace("]", "").split("|")[0]
            base = base.strip().lower()
            nullable = "Optional" in anno or "None" in anno
            default_none = (
                isinstance(stmt.value, ast.Constant) and stmt.value.value is None
            )
            fields.append({
                "name": stmt.target.id,
                "type": base,
                "nullable": nullable,
                "has_default": stmt.value is not None and not default_none,
            })
        if fields:
            out[node.name] = fields
    return out


def _snake(name):
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _camel(name):
    return "".join(p.capitalize() for p in name.split("_") if p)


class _DbHandle:
    """A database HANDLE that survives a database swap.

    Repositories capture the object they are handed at construction time.
    Invariants need an empty table set between them, so the underlying
    Database must be replaceable without rebuilding every repository — this
    handle forwards each attribute access to whichever instance is current.
    """

    def __init__(self, project):
        self._project = project

    def __getattr__(self, name):
        return getattr(self._project.database_now(), name)


class _Project:
    """A loaded generated project plus a fresh temp SQLite database factory."""

    def __init__(self, project_dir: Path):
        self.dir = project_dir
        for required in ("models.py", "database.py"):
            if not (project_dir / required).is_file():
                raise SystemExit(
                    "%s is not a generated project: %s is missing"
                    % (project_dir, required)
                )
        # Isolate this project from any previously loaded one: drop the
        # generated module namespace and the other project's directory, then
        # put this one first on the path.
        for cached in list(sys.modules):
            if _is_project_module(cached):
                del sys.modules[cached]
        while _LOADED_PROJECT_DIRS:
            stale = _LOADED_PROJECT_DIRS.pop()
            try:
                sys.path.remove(stale)
            except ValueError:
                pass
        _LOADED_PROJECT_DIRS.append(str(project_dir))
        sys.path.insert(0, str(project_dir))
        self.models = importlib.import_module("models")
        self.database = importlib.import_module("database")
        try:
            self.exceptions = importlib.import_module("exceptions")
        except Exception:  # noqa: BLE001 - a project may have no exceptions
            self.exceptions = None
        self.repos = {}
        for path in sorted(project_dir.glob("*_repository.py")):
            self.repos[path.stem] = importlib.import_module(path.stem)
        self.service_module = None
        for path in sorted(project_dir.glob("*_service.py")):
            try:
                self.service_module = importlib.import_module(path.stem)
            except Exception:  # noqa: BLE001
                self.service_module = None
            break
        self.fields = _model_fields(project_dir / "models.py")
        self._created = {}
        self._db = None
        self._seq = 0
        self._db_handle = _DbHandle(self)

    def db(self):
        """The stable handle every repository and service is built with."""
        return self._db_handle

    def database_now(self):
        """The shared Database, created on first use.

        The generated ``Database.connect()`` opens a FRESH ``sqlite3.connect``
        per call, so ``":memory:"`` would give every connection its own empty
        database. All repositories and the service must therefore share a
        single instance backed by a single temp file — otherwise a row written
        through one repository is invisible to the next.
        """
        if self._db is None:
            self._db = self.database.Database(
                tempfile.mktemp(prefix="oracle_", suffix=".db")
            )
        return self._db

    def fresh_db(self):
        """Swap in an EMPTY database and forget memoized parent rows.

        Invariants must not observe rows another invariant wrote: a report
        that legitimately sums the whole table would otherwise include that
        noise and look as if it ignored its filter parameter.
        """
        self._db = None
        self._created = {}
        self._seq = 0

    def repo_for(self, cls_name):
        """(repository instance, repository class) for an entity, else (None, None)."""
        mod = self.repos.get(_snake(cls_name) + "_repository")
        if mod is None:
            return None, None
        repo_cls = getattr(mod, cls_name + "Repository", None)
        if repo_cls is None:
            return None, None
        return repo_cls(self.db()), repo_cls

    def service(self):
        if self.service_module is None:
            return None
        for name in dir(self.service_module):
            obj = getattr(self.service_module, name)
            if isinstance(obj, type) and name.endswith("Service"):
                return obj(self.db())
        return None

    def make(self, cls_name, repo, overrides=None):
        """Create one row of ``cls_name`` through its repository; return its id.

        Required (non-nullable, non-id, no-default) fields are synthesized by
        declared type; an FK column is satisfied by creating the referenced
        entity first (memoized, so a round-trip creates each parent once).
        """
        overrides = dict(overrides or {})
        cls = getattr(self.models, cls_name)
        kwargs = {}
        for f in self.fields.get(cls_name, []):
            name = f["name"]
            if name == "id" or f["nullable"] or f["has_default"]:
                continue
            if name in overrides:
                kwargs[name] = overrides.pop(name)
                continue
            if name.endswith("_id"):
                ref = _camel(name[: -len("_id")])
                if ref in self.fields:
                    kwargs[name] = self._parent_id(ref)
                    continue
            kwargs[name] = self._synthesize(f["type"])
        kwargs.update(overrides)
        return repo.create(cls(**kwargs))

    def _synthesize(self, decl_type):
        """A DISTINCT value for a declared primitive type.

        The values must differ per call: the generated schema carries UNIQUE
        constraints (``categories.name``, ``budgets(category_id, month)``), so
        a repeated constant makes the second row of an entity fail with
        IntegrityError and masks the invariant under test. Dates are ISO
        STRINGS because the generated repositories read SQLite back as
        strings (the deterministic renderer stores them that way).
        """
        self._seq += 1
        seq = self._seq
        if decl_type == "int":
            return seq
        if decl_type == "float":
            return float(seq) + 0.5
        if decl_type == "bool":
            return True
        if decl_type == "date":
            return "2024-01-%02d" % ((seq % 28) + 1)
        if decl_type == "datetime":
            return "2024-01-%02dT00:00:00" % ((seq % 28) + 1)
        return "oracle-%d" % seq

    def _parent_id(self, ref_cls):
        if ref_cls in self._created:
            return self._created[ref_cls]
        repo, _ = self.repo_for(ref_cls)
        if repo is None:
            return None
        rid = self.make(ref_cls, repo)
        self._created[ref_cls] = rid
        return rid


# ---------------------------------------------------------------------------
# DESIGN-derived invariants
# ---------------------------------------------------------------------------

def _required_arity(fn):
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    return [
        p for p in list(sig.parameters.values())[1:]
        if p.default is p.empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]


def design_invariants(proj: _Project):
    """[(id, family, fn)] derived from the generated tree alone."""
    out = []
    for cls_name in sorted(proj.fields):
        repo, _ = proj.repo_for(cls_name)
        if repo is None:
            continue

        def _roundtrip(proj=proj, cls_name=cls_name, repo=repo):
            rid = proj.make(cls_name, repo)
            row = repo.get_by_id(rid)
            assert row is not None, "%s.get_by_id(%r) returned None" % (
                cls_name, rid)
            assert type(row).__name__ == cls_name, (
                "%s.get_by_id returned a %s, not a %s"
                % (cls_name, type(row).__name__, cls_name))

        out.append(("%s: create -> get_by_id round-trip" % cls_name,
                    _DESIGN, _roundtrip))

        def _list_type(proj=proj, cls_name=cls_name, repo=repo):
            proj.make(cls_name, repo)
            rows = repo.get_all()
            assert isinstance(rows, list), (
                "%s.get_all() returned %s, not a list"
                % (cls_name, type(rows).__name__))
            for r in rows:
                assert type(r).__name__ == cls_name, (
                    "%s.get_all() yielded a %s, not a %s"
                    % (cls_name, type(r).__name__, cls_name))

        out.append(("%s: get_all() yields entity instances" % cls_name,
                    _DESIGN, _list_type))

    # A service listing NAMING an entity must yield that entity: this is the
    # design's own expectation, and it is what catches a listing wired to a
    # different repository (list_author() returning books).
    svc = proj.service()
    if svc is not None:
        for cls_name in sorted(proj.fields):
            for meth in ("list_" + _snake(cls_name),
                         "list_" + _snake(cls_name) + "s",
                         "get_" + _snake(cls_name) + "s"):
                fn = getattr(svc, meth, None)
                if fn is None:
                    continue
                args = [None] * len(_required_arity(fn) or [])
                try:
                    result = fn(*args)
                except Exception:  # noqa: BLE001 - raising listings are the
                    # other gates' business, not this invariant's
                    continue
                if not isinstance(result, list) or not result:
                    continue
                if isinstance(result[0], dict):
                    continue
                snap = list(result)
                svc_name = type(svc).__name__

                def _assert_elem(snap=snap, cls_name=cls_name, meth=meth,
                                 svc_name=svc_name):
                    for r in snap:
                        assert type(r).__name__ == cls_name, (
                            "%s.%s() yielded a %s, not a %s"
                            % (svc_name, meth, type(r).__name__, cls_name))

                out.append(("%s.%s() yields %s instances" % (
                    svc_name, meth, cls_name), _DESIGN, _assert_elem))
                break
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_one(iid, family, fn, proj=None):
    if proj is not None:
        proj.fresh_db()
    try:
        fn()
        return {"id": iid, "family": family, "status": "pass"}
    except Exception as exc:  # noqa: BLE001 - a failed invariant IS the result
        return {
            "id": iid,
            "family": family,
            "status": "fail",
            "detail": "%s: %s" % (type(exc).__name__, exc),
            "where": traceback.format_exc().strip().splitlines()[-3:],
        }


def run(project_dir, verbose=False):
    """Execute every invariant against the generated project.

    Returns ``{"project", "status", "total", "passed", "tests": [...]}``.
    """
    project_dir = Path(project_dir)
    proj = _Project(project_dir)
    tests = [
        _run_one(i, f, fn, proj) for i, f, fn in design_invariants(proj)
    ]
    from .spec_invariants import REGISTRY

    builder = REGISTRY.get(project_dir.name)
    if builder is None:
        raise SystemExit(
            "no spec invariants registered for project %r" % project_dir.name
        )
    for iid, fn in builder(proj):
        tests.append(_run_one(iid, _SPEC, fn, proj))
    failed = [t for t in tests if t["status"] != "pass"]
    return {
        "project": project_dir.name,
        "status": "pass" if not failed else "fail",
        "total": len(tests),
        "passed": len(tests) - len(failed),
        "tests": tests,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--generated", type=Path, default=Path("generated"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    res = run(args.generated / args.project, verbose=True)
    for t in res["tests"]:
        print(
            "  %-4s [%-6s] %s%s"
            % (
                "PASS" if t["status"] == "pass" else "FAIL",
                t["family"],
                t["id"],
                "" if t["status"] == "pass" else "  ->  " + t.get("detail", ""),
            )
        )
    print("%s: %d/%d invariant(s) hold" % (
        res["project"], res["passed"], res["total"]))
    if args.json:
        args.json.write_text(
            json.dumps(res, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return 0 if res["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
