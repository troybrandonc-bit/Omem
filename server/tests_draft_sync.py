"""The Internet-Draft says what the validator does. Run: python3 tests_draft_sync.py

There are now two normative statements of this format: scripts/testimony_validate.py,
which decides what passes, and spec/draft-clifford-testimony-record-00.md, which is
what the IETF and anyone implementing from paper will read. A specification that
disagrees with its own reference implementation is worse than no specification,
because the disagreement is invisible until somebody has already built the wrong
thing and been told their record is invalid.

The first draft of that document got three things wrong within an hour of being
written: it omitted `proposed_by` from decision, omitted `subject` and `proposition`
from conflict, and invented `held_from` and `held_until`, which exist nowhere. All
three were caught by reading the validator afterwards. This suite is that reading,
made automatic, so the fourth mistake is caught by CI rather than by a stranger who
implemented the draft and could not work out why.

What is checked is the machine-checkable overlap: entry types, required members,
enumerated values, and the untrusted identity sources. Prose is not checked and
cannot be. The point is that no field name, type name or allowed value can be added
to, removed from, or renamed in one file without the other failing.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import testimony_validate as tv  # noqa: E402

DRAFT = os.path.join(ROOT, "spec", "draft-clifford-testimony-record-00.md")

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:300])


def sections(text):
    """The draft's entry-type sections, as {type name: body}.

    Each is a level-2 heading under 'Entry Types' whose title is the type name,
    which is also why the headings are lower case in that document.
    """
    body = text.split("\n# Entry Types\n", 1)
    if len(body) < 2:
        return {}
    body = body[1].split("\n# ", 1)[0]
    out, name, buf = {}, None, []
    for line in body.splitlines():
        m = re.match(r"^## (\S+)\s*$", line)
        if m:
            if name:
                out[name] = "\n".join(buf)
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf)
    return out


def defs(section):
    """The section's definition list, as {member name: its definition text}.

    A term line is followed by one or more lines starting ': ', and may name
    several members at once ('engine, engine_version:'), in which case both
    names get the same text.
    """
    out, terms, buf = {}, [], []

    def flush():
        for t in terms:
            out[t] = "\n".join(buf)

    lines = section.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(": ") or (buf and line.startswith("  ")):
            buf.append(line)
            continue
        if buf:
            flush()
            terms, buf = [], []
        stripped = line.strip()
        if stripped.endswith(":") and i + 1 < len(lines) and \
                lines[i + 1].startswith(": "):
            terms = [p.strip().strip("`") for p in stripped[:-1].split(",")]
            terms = [p for p in terms if re.fullmatch(r"[a-z_]+", p)]
    if buf:
        flush()
    return out


def main():
    if not os.path.exists(DRAFT):
        print("SKIP: no draft at " + DRAFT)
        return 0

    with open(DRAFT, encoding="utf-8") as f:
        text = f.read()

    print("entry types")
    secs = sections(text)
    check("the draft defines a section per entry type",
          set(secs) == tv.TYPES,
          "draft has %s, validator has %s" % (sorted(secs), sorted(tv.TYPES)))

    # The type list also appears inline, in the 'type' member's definition. A
    # reader implementing from the draft copies that line, so it has to be the
    # same set as the sections below it rather than an older version of them.
    m = re.search(r"^type:\n:\s*One of (.+?)\.\s*$", text, re.M | re.S)
    inline = set(re.findall(r"`([a-z]+)`", m.group(1))) if m else set()
    check("the inline type list matches the validator", inline == tv.TYPES,
          "inline %s" % sorted(inline))

    documented = {t: defs(sec) for t, sec in secs.items()}

    print("\nrequired members")
    for t, required in sorted(tv.REQUIRED.items()):
        missing = [f for f in required if f not in documented.get(t, {})]
        check("%s documents every member the validator requires" % t,
              not missing, "undocumented: %s" % missing)

    print("\nno invented members")
    # Members the draft defines that the validator has never heard of. The
    # validator only names required and conditionally-checked members, so
    # anything optional has to be listed here deliberately. That list is the
    # point: adding to it is a decision, and adding to the draft alone is not.
    OPTIONAL = {
        "scope": {"declared_by"},
        "belief": {"evidence"},
        "evidence": {"digest", "excerpt", "redacted"},
        "conflict": {"resolution"},
        "decision": {"risk_source", "reason", "inputs", "approval"},
        "approval": {"identity_source", "method"},
        "integrity": {"engine", "engine_version", "covers"},
    }
    for t in sorted(secs):
        known = set(tv.REQUIRED.get(t, ())) | OPTIONAL.get(t, set())
        unknown = set(documented.get(t, {})) - known
        check("%s defines no member that exists nowhere else" % t,
              not unknown, "invented: %s" % sorted(unknown))

    print("\nenumerated values")
    for (t, field), allowed in sorted(tv.ENUMS.items()):
        body = documented.get(t, {}).get(field, "")
        quoted = set(re.findall(r"`([a-z_\-]+)`", body))
        check("%s.%s lists exactly the allowed values" % (t, field),
              quoted == allowed,
              "draft %s, validator %s" % (sorted(quoted), sorted(allowed)))

    print("\nactor kinds and untrusted sources")
    m = re.search(r"^Actor:\n(.+?)(?=\n\S)", text, re.M | re.S)
    kinds = set(re.findall(r"`([a-z]+)`", m.group(1))) if m else set()
    check("the Actor definition names id, kind and the four kinds",
          kinds == {"id", "kind", "agent", "human", "system", "connector",
                    "name", "role"},
          sorted(kinds))

    # The validator refuses a risk class or an identity that came from anything
    # the proposing model can write. The draft has to say which those are, or an
    # implementer picks a value that reads as fine and is rejected.
    named = {w for w in tv.UNTRUSTED_SOURCES
             if re.search(r"\b%s\b" % re.escape(w.replace("-", " ")), text)
             or re.search(r"\b%s\b" % re.escape(w), text)}
    check("every untrusted identity source is named somewhere in the draft",
          named == tv.UNTRUSTED_SOURCES,
          "unnamed: %s" % sorted(tv.UNTRUSTED_SOURCES - named))

    print("\nversion and levels")
    check("the draft specifies the version the validator specifies",
          ("`%s`" % tv.SPEC) in text, tv.SPEC)
    for lvl in tv.LEVELS:
        check("%s has its own section" % lvl,
              re.search(r"^## %s: " % re.escape(lvl), text, re.M) is not None)
    # 0.1 is still accepted by the validator, and the draft has to say so, or a
    # reader concludes those records became invalid when this document appeared.
    check("the draft accounts for the earlier version the validator accepts",
          "testimony-record/0.1" in text)

    print("\nsubmission hygiene")
    # An I-D with no security or IANA section is returned by the submission
    # tool, and these two are the ones authors forget.
    for heading in ("Security Considerations", "IANA Considerations",
                    "Privacy Considerations"):
        check("the draft has a %s section" % heading,
              re.search(r"^# %s\s*$" % re.escape(heading), text, re.M) is not None)
    check("the draft carries no em dashes", "\u2014" not in text)

    # The author address is archived forever and IANA would list it as the
    # contact for the media type. The first version of this draft carried a
    # .com address beside a .org website, which is a dead contact on a document
    # nobody can edit afterwards.
    email = re.search(r"^\s*email: (\S+@(\S+))\s*$", text, re.M)
    uri = re.search(r"^\s*uri: https?://(?:www\.)?(\S+?)/?\s*$", text, re.M)
    check("the author's email domain matches the author's website",
          bool(email and uri) and email.group(2) == uri.group(1),
          "email %s, uri %s" % (email and email.group(2), uri and uri.group(1)))
    iana = re.findall(r"<(\S+@\S+)>", text)
    check("the IANA contact is the author's address",
          bool(email) and set(iana) == {email.group(1)},
          "in the draft: %s" % sorted(set(iana)))
    # Every reference defined in the front matter has to be cited, or xml2rfc
    # warns and the citation is dead weight in a document people will read.
    defined = set(re.findall(r"^  ([A-Za-z0-9\-\.]+):\s*$", text, re.M))
    cited = set(re.findall(r"\{\{([A-Za-z0-9\-\.]+)\}\}", text))
    # RFC 2119 and 8174 are cited by the bcp14 boilerplate, not by hand.
    unused = defined - cited - {"RFC2119", "RFC8174"}
    check("every reference the draft defines is cited", not unused,
          "unused: %s" % sorted(unused))

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
