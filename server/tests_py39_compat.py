"""The package must import on the oldest Python it claims to support.

`pyproject.toml` says `requires-python = ">=3.9"` and the README says "Python 3.9
or newer", but 0.2.0 shipped with `project: str | None` in the `Memory` signature.
PEP 604 unions are evaluated at class-definition time and are a TypeError before
3.10, so `pip install omem-infrastructure` crashed on import for every 3.9 user.

CI does catch it, but only in the wheel job, as a sixty-second timeout followed by
a traceback four frames deep. This catches it in the suite, on any Python, in
milliseconds, and says what to do about it.

The fix is never to rewrite the annotation. It is `from __future__ import
annotations`, which defers every annotation to a string that is never evaluated.
Run: python3 tests_py39_compat.py
"""
from __future__ import annotations

import ast
import io
import os
import sys

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    ok = bool(cond)
    passed += ok
    failed += (not ok)
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else f"  <<< {detail}"))


HERE = os.path.dirname(os.path.abspath(__file__))
# Everything that ends up in the wheel: the SDK package, and this server tree,
# which hatch_build.py copies to omem/_server/.
TARGETS = [os.path.join(HERE, "..", "sdk", "python", "omem"), HERE]
SKIP_DIRS = ("__pycache__", "_server", "_dashboard", ".hypothesis", "omem_engine")


class _Unions(ast.NodeVisitor):
    """Collects `X | Y` appearing in an annotation position."""

    def __init__(self):
        self.hits = []
        self._depth = 0

    def _ann(self, node):
        if node is None:
            return
        self._depth += 1
        self.visit(node)
        self._depth -= 1

    def visit_AnnAssign(self, node):
        self._ann(node.annotation)
        if node.value:
            self.visit(node.value)

    def _fn(self, node):
        args = node.args
        for a in list(args.args) + list(args.kwonlyargs) + list(getattr(args, "posonlyargs", [])):
            self._ann(a.annotation)
        for extra in (args.vararg, args.kwarg):
            if extra:
                self._ann(extra.annotation)
        self._ann(node.returns)
        for child in node.body + node.decorator_list:
            self.visit(child)

    visit_FunctionDef = _fn
    visit_AsyncFunctionDef = _fn

    def visit_BinOp(self, node):
        if self._depth and isinstance(node.op, ast.BitOr):
            self.hits.append(node.lineno)
        self.generic_visit(node)


def _defers_annotations(tree) -> bool:
    return any(
        isinstance(n, ast.ImportFrom)
        and n.module == "__future__"
        and any(a.name == "annotations" for a in n.names)
        for n in tree.body)


def scan():
    offenders = []
    scanned = 0
    for target in TARGETS:
        target = os.path.normpath(target)
        if not os.path.isdir(target):
            continue
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if not f.endswith(".py"):
                    continue
                p = os.path.join(root, f)
                try:
                    tree = ast.parse(io.open(p, encoding="utf-8").read())
                except (OSError, SyntaxError):
                    continue
                scanned += 1
                if _defers_annotations(tree):
                    continue
                v = _Unions()
                v.visit(tree)
                if v.hits:
                    offenders.append((os.path.relpath(p, HERE), v.hits))
    return scanned, offenders


def main():
    print("== PEP 604 unions require Python 3.10 unless annotations are deferred ==")
    scanned, offenders = scan()
    check(f"scanned {scanned} modules", scanned > 0, "found nothing to scan")
    detail = "; ".join(f"{p} lines {h}" for p, h in offenders)
    check("no module uses `X | Y` in an annotation without deferring annotations",
          not offenders,
          detail + "  -> add `from __future__ import annotations` to each")

    # The SDK is the one a user imports first, so assert the mechanism directly
    # rather than trusting the scan.
    sdk = os.path.normpath(os.path.join(HERE, "..", "sdk", "python"))
    if sdk not in sys.path:
        sys.path.insert(0, sdk)
    try:
        import omem
        ann = omem.Memory.__init__.__annotations__.get("project")
        check("Memory.__init__ annotations are lazy strings, not evaluated types",
              isinstance(ann, str), f"got {type(ann).__name__}: {ann!r}")
    except ImportError as e:
        check("the omem SDK is importable", False, str(e))

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
