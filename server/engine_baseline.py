"""The frozen engine's expected hashes, and the check against them.

WHAT WAS WRONG. Nineteen test suites ended on a check that the reasoning engine
is byte-identical to a baseline, and read that baseline from
`/tmp/engine_hashes_before.txt`. Nothing in the repository created that file, no
CI step wrote it, and .gitignore did not mention it. On any machine that did not
happen to have one, all nineteen suites crashed with FileNotFoundError at their
final line, after every real assertion in them had already passed. On a machine
that did have one, it had been produced by hand at some unrecorded moment, so
agreeing with it proved nothing in particular.

An integrity check that cannot fail meaningfully is worse than none, because it
occupies the place where a real one would go.

WHAT IT IS NOW. The baseline lives in the repository, next to the code it
describes, and is therefore reviewed like code. Changing the engine now requires
changing a checked-in file in the same commit, which is exactly the moment
someone should be asked to justify it, and `python3 engine_baseline.py --update`
is the deliberate act that does it.

WHAT THE CHECK IS FOR. Not to stop the engine ever changing: the reference
implementation was quadratic and had to be fixed. It is to stop it changing
ACCIDENTALLY, and to make a deliberate change visible in a diff. A change to
these files is a change to what the product believes, and the surrounding suites
plus tests_engine_equivalence.py are what say the belief did not move.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(HERE, "omem_engine")
BASELINE_PATH = os.path.join(ENGINE_DIR, "ENGINE_HASHES.txt")


def current_hashes():
    """sha256 of every engine module, keyed by filename, in a stable order."""
    out = {}
    for name in sorted(os.listdir(ENGINE_DIR)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(ENGINE_DIR, name), "rb") as fh:
            out[name] = hashlib.sha256(fh.read()).hexdigest()
    return out


def baseline_hashes():
    """The recorded baseline. Missing file is an error, not an empty dict.

    Returning {} would make the comparison vacuously true and reintroduce the
    check that cannot fail, which is the whole defect this replaced.
    """
    if not os.path.isfile(BASELINE_PATH):
        raise FileNotFoundError(
            f"{BASELINE_PATH} is missing. It is part of the repository; restore it "
            "from version control, or run `python3 engine_baseline.py --update` if "
            "you deliberately changed the engine.")
    out = {}
    with open(BASELINE_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            digest, name = line.split()
            out[os.path.basename(name)] = digest
    return out


def verify():
    """(ok, detail). detail names what moved, so a failure is actionable."""
    current, base = current_hashes(), baseline_hashes()
    changed = sorted(f for f in set(current) | set(base) if current.get(f) != base.get(f))
    if not changed:
        return True, ""
    parts = []
    for f in changed:
        if f not in base:
            parts.append(f"{f} (new)")
        elif f not in current:
            parts.append(f"{f} (deleted)")
        else:
            parts.append(f)
    return False, "changed: " + ", ".join(parts)


def write_baseline():
    lines = [
        "# sha256 of every module in omem_engine/, the frozen reasoning core.",
        "#",
        "# Regenerate with: python3 engine_baseline.py --update",
        "# Do that only for a deliberate engine change, in the same commit as the",
        "# change, and say in the message what moved and what proves the semantics",
        "# did not. tests_engine_equivalence.py is that proof for the current one.",
        "",
    ]
    for name, digest in current_hashes().items():
        lines.append(f"{digest}  {name}")
    with open(BASELINE_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return BASELINE_PATH


if __name__ == "__main__":
    if "--update" in sys.argv:
        print(f"wrote {write_baseline()}")
        sys.exit(0)
    ok, detail = verify()
    print("engine matches baseline" if ok else f"ENGINE CHANGED: {detail}")
    sys.exit(0 if ok else 1)
