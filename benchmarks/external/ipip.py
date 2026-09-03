#!/usr/bin/env python3
"""The same fifty items, from a million people instead of twenty thousand.

`big5.py` runs on Open Psychometrics' older Big Five file: 19,719 responses.
The same project publishes the same instrument answered by 1,015,342 people,
and it carries the respondent's country, which the smaller file does not.

Two reasons that matters, and the second is the one nothing else can give.

Every figure the external benchmark reports rests on 19,668 usable responses
sampled 3,406 at a time. Fifty times the pool means installs can be given real
populations rather than 250 peers each, which is why no local prior has ever
existed in that harness at six subjects, and why the tier rule that keeps
borrowed knowledge from displacing local knowledge has never been exercised
against anything.

And the country column is the first real test available for the population
frame. Requiring a pooled pattern to hold across distinct populations was
built and measured only against synthetic frames; whether it does what it is
meant to when the populations are actually different people in actually
different places is untested.

MEMORY. A million respondents as sets of strings is two to four gigabytes and
does not fit on the machine this was written on. Each respondent is held as
two integers instead -- a bitmask of what they affirmed and one of what they
denied -- which is about 200 MB for the whole file, and sets are materialised
only for the few thousand a trial actually samples.

INDEPENDENCE. The file records how many responses came from each IP address.
Records sharing one are plausibly the same person answering twice, and
counting them separately inflates the support behind a pattern with evidence
that is not independent. This is the same objection the pooled bank makes with
POOLED_MIN_SOURCES and the same one that killed corroboration of agreeing
priors, so the default here is to keep only unique IPs and to say how many
that discards.
"""
from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://openpsychometrics.org/_rawdata/IPIP-FFM-data-8Nov2018.zip"
CACHE = os.path.join(HERE, "_ipip.zip")
MEMBER = "IPIP-FFM-data-8Nov2018/data-final.csv"

# Five factors, ten items each, so a pair drawn at random joins two items of
# one factor with probability 9/49 -- the same ground truth the smaller file
# provides, and the reason either is worth running.
FACTORS = ("EXT", "EST", "AGR", "CSN", "OPN")
MIN_ANSWERED = 20           # as in big5.py: enough of the instrument to use


def fetch(path: str = CACHE) -> str:
    """Download once. 151 MB compressed, 416 MB inside.

    Not committed, here or anywhere: this repository does not redistribute
    other people's survey responses."""
    if not os.path.exists(path):
        sys.stderr.write("downloading IPIP-FFM (151 MB) ...\n")
        urllib.request.urlretrieve(URL, path)
    return path


def load(limit: int | None = None, unique_ip: bool = True,
         path: str = CACHE) -> tuple[list, list, dict]:
    """Returns (rows, items, meta).

    rows are (held_mask, opposed_mask, country) with the masks over `items`.
    A neutral answer appears in neither, which is what makes it a silence
    rather than a missing value -- the property the whole experiment rests on.
    """
    fetch(path)
    z = zipfile.ZipFile(path)
    rows: list = []
    seen_ipc = dropped_ipc = dropped_thin = 0
    countries: dict = {}
    with z.open(MEMBER) as raw:
        f = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
        header = f.readline().rstrip("\r\n").split("\t")
        items = [h for h in header
                 if h[:3] in FACTORS and h[3:].isdigit()]
        idx = {h: header.index(h) for h in items}
        ipc_i = header.index("IPC") if "IPC" in header else None
        cty_i = header.index("country") if "country" in header else None
        for line in f:
            row = line.rstrip("\r\n").split("\t")
            if len(row) < len(header):
                continue
            if ipc_i is not None:
                try:
                    if unique_ip and int(row[ipc_i]) != 1:
                        dropped_ipc += 1
                        continue
                    seen_ipc += 1
                except ValueError:
                    pass
            held = opp = 0
            answered = 0
            for b, it in enumerate(items):
                try:
                    v = int(row[idx[it]])
                except (ValueError, IndexError):
                    continue
                if v >= 4:
                    held |= 1 << b
                    answered += 1
                elif 1 <= v <= 2:
                    opp |= 1 << b
                    answered += 1
                elif v == 3:
                    answered += 1       # a real silence, still an answer given
            if answered < MIN_ANSWERED:
                dropped_thin += 1
                continue
            cty = sys.intern(row[cty_i]) if cty_i is not None else ""
            countries[cty] = countries.get(cty, 0) + 1
            rows.append((held, opp, cty))
            if limit and len(rows) >= limit:
                break
    meta = {"dropped_shared_ip": dropped_ipc, "dropped_too_thin": dropped_thin,
            "countries": countries}
    return rows, items, meta


def expand(rows, items) -> list:
    """The (held, opposed) shape the miner and the install both expect.

    Called on a sample, never on the whole file. Fifty times the pool is only
    useful if it is not fifty times the memory."""
    out = []
    for held, opp, _cty in rows:
        h = {items[b] for b in range(len(items)) if held >> b & 1}
        o = {items[b] for b in range(len(items)) if opp >> b & 1}
        out.append((h, o))
    return out


def by_country(rows, minimum: int = 2000) -> dict:
    """Rows grouped by country, keeping the ones with enough people to mine.

    This is what makes a frame test possible: populations that are actually
    different rather than slices of one shuffled pool."""
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[2], []).append(r)
    return {k: v for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))
            if len(v) >= minimum}


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rows, items, meta = load(limit=limit)
    print("usable respondents : %d" % len(rows))
    print("items              : %d over %d factors" % (len(items), len(FACTORS)))
    print("dropped, shared IP : %d" % meta["dropped_shared_ip"])
    print("dropped, too thin  : %d" % meta["dropped_too_thin"])
    big = by_country(rows)
    print("countries with 2000+ : %d" % len(big))
    for c, v in list(big.items())[:8]:
        print("    %-6s %7d" % (c or "(blank)", len(v)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
