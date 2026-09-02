"""The public site cannot ship a page nobody can read.
Run: python3 tests_marketing_routes.py

`web/lib/routes.ts` decides whether a path gets the marketing shell or the
dashboard shell. A public page missing from that array gets the dashboard one,
whose first render is a loading state, so the page's entire server HTML becomes
"Connecting to the OMEM server" — to Google, to every LLM crawler following
llms.txt, and to any reader whose JavaScript has not arrived yet.

That is not hypothetical. /spec/testimony-record, its implementations page,
/agent-audit-check and /vendor-review each shipped without being added, and
each served roughly ninety characters of chrome for weeks while sitting in the
sitemap being offered for indexing. The comment in routes.ts predicted it
exactly ("a route added to the public site and not to this array would quietly
get the app chrome") and a comment cannot fail a build.

So the page tree is the source of truth and this suite is the check: every
directory under web/app/(marketing) that has a page must be covered by
MARKETING_ROUTES, and must be listed in the sitemap. Add a page, add two lines,
and the build tells you which two.

The third file that goes stale the same way, web/public/llms-full.txt, is
guarded separately by `python scripts/gen_llms_full.py --check`, because
proving it needs the pages themselves rather than their paths.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARKETING = os.path.join(ROOT, "web", "app", "(marketing)")

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


def array_from(path, name):
    """The string literals of a `const NAME = [...]` in a TypeScript file."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"(?:const|let)\s+%s\s*(?::[^=]+)?=\s*\[(.*?)\]" % name, src, re.S)
    if not m:
        return None
    return re.findall(r"[\"']([^\"']*)[\"']", m.group(1))


def public_routes():
    """Every route the marketing page tree actually serves.

    Route groups "(name)" contribute no segment, and a dynamic "[slug]" has no
    fixed URL to list anywhere, so both are skipped.
    """
    found = []
    for dirpath, _dirs, files in os.walk(MARKETING):
        if "page.tsx" not in files:
            continue
        rel = os.path.relpath(dirpath, MARKETING).replace(os.sep, "/")
        if rel == ".":
            found.append("/")
            continue
        parts = [p for p in rel.split("/") if not p.startswith("(")]
        if any(p.startswith("[") for p in parts):
            continue
        found.append("/" + "/".join(parts))
    return sorted(found)


routes_ts = os.path.join(ROOT, "web", "lib", "routes.ts")
sitemap_ts = os.path.join(ROOT, "web", "app", "sitemap.ts")

check("web/lib/routes.ts exists", os.path.exists(routes_ts))
check("web/app/sitemap.ts exists", os.path.exists(sitemap_ts))
check("web/app/(marketing) exists", os.path.isdir(MARKETING))
if FAIL:
    print("\n%d passed, %d failed" % (PASS, FAIL))
    sys.exit(1)

marketing = array_from(routes_ts, "MARKETING_ROUTES")
sitemap = array_from(sitemap_ts, "ROUTES")
pages = public_routes()

check("MARKETING_ROUTES parses", marketing is not None)
check("the sitemap's ROUTES parses", sitemap is not None)
check("the page tree has a real number of public pages", len(pages) >= 15, len(pages))

print("== every public page gets the marketing shell ==")
for route in pages:
    covered = route == "/" or any(route.startswith(r) for r in (marketing or []))
    check(route, covered,
          "not covered by MARKETING_ROUTES, so it renders the dashboard's "
          "loading state as its entire server HTML")

print("== every public page is in the sitemap ==")
listed = {r if r else "/" for r in (sitemap or [])}
for route in pages:
    check(route, route in listed or (route == "/" and "" in (sitemap or [])),
          "missing from web/app/sitemap.ts, so it is left to be found by luck")

print("== nothing in MARKETING_ROUTES has lost its page ==")
for r in (marketing or []):
    check(r, any(p == r or p.startswith(r + "/") for p in pages),
          "no page under web/app/(marketing) serves this prefix any more")

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
