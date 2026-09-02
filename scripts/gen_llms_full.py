#!/usr/bin/env python3
"""Build web/public/llms-full.txt from the pages llms.txt links.

llms.txt promises "the full text of every doc, guide, and comparison page".
It was assembled by hand, so it drifted: by 2 Sep 2026 it carried 13 sections
and llms.txt linked 23 pages, missing the entire specification, the readiness
check, the vendor-review answers, the licence page, pricing, the objective and
three of the four comparisons. An index that promises the whole site and
delivers half of it is worse than no index, because an assistant reading it
concludes the missing half does not exist.

So it is generated, from the single source that already decides what belongs:
the links in llms.txt. Add a page there and it appears here; the section title
is the link label, which is where the existing titles came from anyway.

Stdlib only, like every script here.

    python scripts/gen_llms_full.py                  # from the live site
    python scripts/gen_llms_full.py --from-dir web/out
    python scripts/gen_llms_full.py --check          # exit 1 if stale

REFUSES TO WRITE A PAGE IT CANNOT READ. A client-rendered page whose server
HTML is a loading state extracts to nothing, and quietly writing that nothing
into the file is exactly the failure this script exists to end. If a page comes
back as chrome, this says which page and exits 1 rather than shipping a file
that says "Connecting to the OMEM server" where a specification should be.
"""
import argparse
import html
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, "web", "public", "llms.txt")
TARGET = os.path.join(ROOT, "web", "public", "llms-full.txt")
BASE = "https://infrastructure.omem-cloud.com"

HEADER = (
    "# OMEM: full documentation and guides\n"
    "> The complete text of OMEM's docs, guides, and comparison pages in one "
    "file, for AI assistants. Index: %s/llms.txt\n" % BASE
)

# Linked from llms.txt but not pages: the schema, this file, and anything off
# the site. Nothing here has prose to extract.
SKIP = ("/llms-full.txt", ".json", ".jsonl", ".xml", ".txt")

# Under this many characters a page did not render its content, whatever the
# HTTP status said.
MIN_CHARS = 400


def links(index_text):
    """(label, url) for every OMEM page llms.txt links, in file order."""
    out = []
    seen = set()
    for label, url in re.findall(r"^- \[([^\]]+)\]\((https://[^)]+)\)", index_text, re.M):
        if not url.startswith(BASE):
            continue
        if url.endswith(SKIP):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((label, url))
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "omem-llms-full/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def read_export(directory, url):
    """The same page out of a static export, so this can run without network."""
    path = url[len(BASE):].strip("/")
    for candidate in (os.path.join(directory, path, "index.html"),
                      os.path.join(directory, path + ".html"),
                      os.path.join(directory, "index.html") if not path else None):
        if candidate and os.path.exists(candidate):
            with open(candidate, encoding="utf-8", errors="replace") as f:
                return f.read()
    raise IOError("no exported file for %s under %s" % (url, directory))


def text_of(doc):
    """The readable page: no chrome, headings kept as markdown."""
    for tag in ("script", "style", "svg", "footer", "nav"):
        doc = re.sub(r"<%s.*?</%s>" % (tag, tag), " ", doc, flags=re.S | re.I)

    for n in (1, 2, 3, 4):
        doc = re.sub(r"<h%d[^>]*>" % n, "\n\n" + "#" * n + " ", doc, flags=re.I)
        doc = re.sub(r"</h%d>" % n, "\n\n", doc, flags=re.I)
    doc = re.sub(r"</(p|li|tr|div|section|blockquote)>", "\n", doc, flags=re.I)
    doc = re.sub(r"<li[^>]*>", "- ", doc, flags=re.I)
    doc = re.sub(r"<br[^>]*>", "\n", doc, flags=re.I)
    doc = re.sub(r"<[^>]+>", "", doc)
    doc = html.unescape(doc)

    # Site chrome ends at the mobile nav toggle. Fall back to the skip link for
    # a page that renders no toggle.
    cut = doc.rfind("Open menu")
    if cut == -1:
        cut = doc.find("Skip to content")
        cut = cut + len("Skip to content") if cut != -1 else -1
    else:
        cut += len("Open menu")
    if cut != -1:
        doc = doc[cut:]

    lines = []
    for raw in doc.splitlines():
        line = " ".join(raw.split())
        if line and line.strip("- ") == "":      # a rule, not a list item
            continue
        if not line and lines and not lines[-1]:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def build(get):
    with open(INDEX, encoding="utf-8") as f:
        index_text = f.read()

    sections, unreadable = [], []
    for label, url in links(index_text):
        body = text_of(get(url))
        if len(body) < MIN_CHARS or "Connecting to the OMEM server" in body:
            unreadable.append((label, url, len(body)))
            continue
        sections.append("# %s\nSource: %s\n\n%s" % (label, url, body))

    if unreadable:
        print("These pages served no content, so nothing was written:\n")
        for label, url, n in unreadable:
            print("  %-46s %s  (%d chars)" % (label, url, n))
        print("\nA page that renders only in the browser has no server HTML for a\n"
              "crawler either. Check web/lib/routes.ts: a public route missing from\n"
              "MARKETING_ROUTES renders the dashboard's loading state instead of the\n"
              "page. Fix that first; this file is downstream of it.")
        return None

    return HEADER + "\n---\n\n" + "\n\n---\n\n".join(sections) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir", default=None,
                    help="read a static export (web/out) instead of the live site")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed file is not what this would write")
    args = ap.parse_args()

    get = (lambda u: read_export(args.from_dir, u)) if args.from_dir else fetch
    built = build(get)
    if built is None:
        return 1

    if args.check:
        with open(TARGET, encoding="utf-8") as f:
            current = f.read()
        if current == built:
            print("llms-full.txt is current (%d sections)" % built.count("\nSource: "))
            return 0
        print("llms-full.txt is stale. Run: python scripts/gen_llms_full.py")
        return 1

    with open(TARGET, "w", encoding="utf-8", newline="\n") as f:
        f.write(built)
    print("wrote %s (%d sections, %d KB)"
          % (os.path.relpath(TARGET, ROOT), built.count("\nSource: "), len(built) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
