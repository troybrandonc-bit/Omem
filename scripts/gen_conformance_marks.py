#!/usr/bin/env python3
"""Generate the Testimony Record conformance marks.

    python3 scripts/gen_conformance_marks.py

Writes web/public/badge/testimony-record-tr{1..4}.svg, the marks an
implementation displays once its record reaches that level. They are plain
static SVG so a README can hotlink them from the canonical domain without
anything running.

The mark is the part of the standard that is owned. Anyone may implement the
specification without asking, but the name and these marks identify records
that actually pass, which is why they live at a fixed address here rather than
being redrawn by each implementer.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
import os

INK = "#171614"
ACCENT = "#4F46E5"
LEVELS = {
    1: "recorded",
    2: "explained",
    3: "gated",
    4: "verifiable",
}
# Verdana 11px, the width every badge renderer assumes. Measured per string
# rather than estimated, so the text is never clipped or adrift.
WIDTHS = {"testimony record": 103, "TR-1": 30, "TR-2": 30, "TR-3": 30, "TR-4": 30}

TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" \
role="img" aria-label="testimony record: {label}">
  <title>testimony record: {label} ({word})</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#fff" stop-opacity=".08"/>
    <stop offset="1" stop-opacity=".08"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{left}" height="20" fill="{ink}"/>
    <rect x="{left}" width="{right}" height="20" fill="{accent}"/>
    <rect width="{total}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,Geneva,sans-serif" \
font-size="11">
    <text x="{lx}" y="14">testimony record</text>
    <text x="{rx}" y="14" font-weight="bold">{label}</text>
  </g>
</svg>
"""


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(os.path.dirname(here), "web", "public", "badge")
    os.makedirs(out_dir, exist_ok=True)
    pad = 10
    left = WIDTHS["testimony record"] + pad * 2
    for n, word in LEVELS.items():
        label = f"TR-{n}"
        right = WIDTHS[label] + pad * 2
        svg = TEMPLATE.format(
            total=left + right, left=left, right=right, ink=INK, accent=ACCENT,
            lx=left // 2, rx=left + right // 2, label=label, word=word)
        path = os.path.join(out_dir, f"testimony-record-tr{n}.svg")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        print(f"wrote {os.path.relpath(path, os.path.dirname(here))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
