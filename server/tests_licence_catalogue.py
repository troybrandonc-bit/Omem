"""What is sold, what is gated, and what the page says, kept to one answer.
Run: python3 tests_licence_catalogue.py

Three places describe the paid components: the gates in the code, the catalogue
`/v1/licence` serves, and the pricing page a buyer reads. They drift apart in a
particular direction, and it is always the same one: a component ships, the gate
goes in, and nobody updates the two places a customer would look. The feature
then exists, is charged for, and is invisible to the person paying.

That had already happened once when this file was written. `approval_queue` was
gated in api.py and absent from the catalogue.

The pricing page gets the harder rule. It once advertised tiers with a checkout
that was never wired up, and the fix was to say only what is true. So a
self-serve claim is allowed only when there is a link to serve it, and the test
enforces that rather than trusting whoever edits the page next.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import licence as LICENCE      # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:240])


def source(*parts):
    return io.open(os.path.join(ROOT, *parts), encoding="utf-8").read()


print("== every gate is a feature somebody can read about ==")
gated = set()
for name in sorted(os.listdir(HERE)):
    if not name.endswith(".py") or name.startswith("tests_"):
        continue
    gated |= set(re.findall(r'LICENCE\.has\("([a-z_]+)"\)', source("server", name)))
check("the code gates at least one feature", bool(gated), gated)
missing = sorted(gated - set(LICENCE.FEATURES))
check("nothing is gated that the catalogue does not name", not missing,
      "gated and undocumented: %s" % missing)
extra = sorted(set(LICENCE.FEATURES) - gated)
check("nothing is advertised that no code gates", not extra,
      "named in the catalogue and gating nothing: %s" % extra)
for f, desc in LICENCE.FEATURES.items():
    check("%s is described in a sentence, not a label" % f,
          len(desc) > 30 and " " in desc, desc)

# The tool that mints licences validates features against this same catalogue,
# so a default it cannot satisfy makes the tool unusable with its own defaults.
# That was true when this was written: the default named auditor_export, which
# no code gates, so `sign_licence.py --customer X` simply errored.
signer = source("scripts", "sign_licence.py")
# Matched over the whole declaration rather than up to the next comma: the
# default is `",".join(sorted(FEATURES))`, which contains one.
_default = re.search(r'"--features",\s*default=(.{0,60})', signer, re.S)
check("the signing tool's default features come from the catalogue",
      _default is not None and "FEATURES" in _default.group(1),
      repr(_default.group(1)[:40]) if _default else "no --features default")
check("the signing tool records what it issued",
      "--ledger" in signer and "token_sha256" in signer)
check("and records a digest of the token, not the token itself",
      '"token_sha256"' in signer and '"token": token' not in signer)

print("\n== every paid component sits behind the licence boundary ==")
ee = os.path.join(HERE, "ee")
mods = sorted(f for f in os.listdir(ee) if f.endswith(".py")
              and f != "__init__.py")
check("the ee package has components in it", bool(mods), mods)
for m in mods:
    text = source("server", "ee", m)
    check("%s says a commercial licence is required" % m,
          "Commercial licence required" in text)
check("the ee package states the core stays MIT",
      "always will be" in source("server", "ee", "__init__.py"))
check("and that its absence is not an error",
      "works exactly as the open version" in source("server", "ee", "__init__.py"))

print("\n== the pricing page says only what is true ==")
page = source("web", "app", "(marketing)", "pricing", "page.tsx")
flat = " ".join(page.split())

for f in LICENCE.FEATURES:
    words = f.replace("_", " ")
    check("the page mentions %s" % f, words in flat.lower(), words)

# The page once advertised tiers with a checkout that did not exist. A
# self-serve claim is now allowed only when something can serve it.
link = re.search(r'STRIPE_LINK\s*=\s*"([^"]*)"', page)
check("the page declares where a checkout link would go", link is not None,
      "no STRIPE_LINK constant")
has_link = bool(link and link.group(1).strip())
if has_link:
    check("the link is a real URL", link.group(1).startswith("https://"),
          link.group(1))
else:
    # No link, so nothing on the page may imply one can be used.
    for claim in ("buy now", "subscribe", "start free trial", "checkout now"):
        check("with no link, the page does not say %r" % claim,
              claim not in flat.lower())
    check("and it says how a licence is actually obtained",
          "invoice" in flat.lower() or "conversation" in flat.lower())

print("\n== a licence names what it unlocks and when it stops ==")
st = LICENCE.status()
check("an unlicensed install says so plainly", st["licensed"] is False, st)
check("and still publishes the catalogue, so a buyer can see what exists",
      set(st["catalogue"]) == set(LICENCE.FEATURES), st.get("catalogue"))
check("an unlicensed install claims no features", st["features"] == [], st)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
