"""OMEM learns who a person works for. Run: python3 tests_learn_employment.py

Every party in the extractor's _subject_for() collapses to a COMPANY. An email
from sarah@acme.com became memories about company:acme, and Sarah was never a
node at all. The one exception was a third party named in a body ("Sarah
reports to David"), which is the rarer case by far.

So the person OMEM was actually corresponding with did not exist in the graph,
and works_at -- the relation in the vocabulary, in graph.py's own docstring
example, and offered to the LLM -- was never produced by anything
deterministic. The extractor emitted three of the eight relations: uses,
managed_by, reports_to.

Both ends were already resolved from the same address and the link between
them was thrown away.

WHAT THIS IS, EXACTLY. It is an inference, not something a person said. An
address is strong evidence of employment and is not a statement of it. So it
is recorded with dkind="inference" -- the first thing OMEM concludes rather
than transcribes -- and /why shows it as such. It stays defeasible: the same
human writing later from another company produces a competing works_at that
contradiction and supersession handle like any other belief.

WHAT IT MUST NOT DO. Claim that Support, noreply or a mailing list is a person;
invent an employer from a gmail address; or fire on the owner's own colleagues,
whose org chart needs configured identity to be about anyone. Most of this
suite is those refusals, because a relation layer that accumulates junk nodes
is worse than one that stays empty.
"""
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sdk", "python"))
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_learn_employment.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
import graph as _graph  # noqa: E402
from extraction import infer_employment, _looks_like_person  # noqa: E402
from email_analysis import parse_participants  # noqa: E402
from connectors import GmailTransport  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


# This suite's own signup address. tests_p5_graph.py owns troy@kronos.com, and
# under PostgreSQL every suite shares one database, so reusing it would 409.
# The DOMAIN is deliberately still kronos.com: direction, the internal check and
# the free-mail rules all key off it, and the existing suites share it happily.
OWNER = "employ@kronos.com"
IDENT = {"company_name": "Kronos", "domains": ["kronos.com"], "emails": [OWNER]}


def pp_for(frm):
    return parse_participants({"from": frm, "to": OWNER, "subject": "hi",
                               "body": "hello"}, IDENT)


print("== who counts as a person at a company ==")
YES = [("Sarah Chen <sarah@acme.com>", "a named person"),
       ("Jean-Luc Picard <jl@acme.com>", "a hyphenated name"),
       ("Maria de Souza Lima <m@acme.com>", "a name with a particle"),
       ("Ana María Rodríguez <a@acme.com>", "a name with accents")]
for frm, why in YES:
    check("learns from " + why, infer_employment(pp_for(frm)) is not None, frm)

NO = [("sarah@acme.com", "no display name, so nobody presented a name"),
      ("Sarah Chen <sarah@gmail.com>", "free-mail is not an employer"),
      ("Acme Support <support@acme.com>", "a role account"),
      ("Sarah Chen <noreply@acme.com>", "a person name on a noreply address"),
      ("Acme <hello@acme.com>", "a company signing its own mail"),
      ("Customer Success Team <cs@acme.com>", "a team, not a human"),
      ("Bob <bob@kronos.com>", "our own colleague")]
for frm, why in NO:
    got = infer_employment(pp_for(frm))
    check("refuses: " + why, got is None, got)

check("and outbound mail infers nothing (we have their address, not their name)",
      infer_employment(parse_participants(
          {"from": "Troy <%s>" % OWNER, "to": "sarah@acme.com",
           "subject": "hi", "body": "hello"}, IDENT)) is None)

# The name test is Unicode-aware on purpose: an ASCII-only rule would quietly
# work for English names and refuse most others.
check("the name rule is not ASCII-only",
      _looks_like_person("Ana María Rodríguez")
      and _looks_like_person("Björn Müller"))

print("== end to end: an ordinary email teaches it ==")
srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
BASE = "http://127.0.0.1:%d" % PORT


def call(m, path, body=None, key=None):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    r = urllib.request.Request(
        BASE + path, method=m,
        data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


acct = call("POST", "/v1/signup", {"email": OWNER})[1]
KEY, PID = acct["api_key"]["secret"], acct["project"]["id"]
call("POST", "/v1/identity?project=%s" % PID,
     {"company_name": "Kronos", "domains": ["kronos.com"], "emails": [OWNER]}, KEY)
P = api.PROJECTS[PID]


def msg(mid, frm, subj, body, ts):
    raw = "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n%s\r\n" % (frm, OWNER, subj, body)
    return {"id": mid, "threadId": mid, "internalDate": str(ts),
            "raw": base64.urlsafe_b64encode(raw.encode()).decode()}


MAILBOX = [
    msg("m1", "Sarah Chen <sarah@acme.com>", "Contract",
        "We have decided to renew the annual contract.", 1000),
    # A role account at the same company must not become a second person.
    msg("m2", "Acme Billing <billing@acme.com>", "Invoice",
        "We have decided to renew the annual contract.", 2000),
    # The same person writing again. This fires on EVERY inbound mail, so if it
    # created a fresh relation each time a busy mailbox would bury real memory
    # under thousands of copies of one fact.
    msg("m3", "Sarah Chen <sarah@acme.com>", "Plans",
        "We have decided to upgrade the plan.", 3000),
]


class T(GmailTransport):
    def list_messages(self, token, cursor):
        return (MAILBOX, "done")


api.GMAIL_TRANSPORT_FACTORY = lambda conn: T()
_, beg = call("POST", "/v1/oauth/gmail/begin?project=%s" % PID, {"name": "G"}, KEY)
CID = beg["connector_id"]
call("POST", "/v1/oauth/gmail/callback?project=%s" % PID,
     {"connector_id": CID, "account": OWNER}, KEY)
call("POST", "/v1/connectors/%s/poll?project=%s" % (CID, PID), {}, KEY)
call("POST", "/v1/ingest/process?project=%s" % PID, {}, KEY)

PERSON = "person:sarah_chen@acme"
# The connector writes as connector:<kind>, not agent:<kind>. Memories are
# agent-scoped, so recalling as the wrong agent returns an empty pack rather
# than an error -- worth pinning rather than hardcoding a guess.
AGENT = "connector:gmail"


def edges_of(entity):
    """Scoped to this project: reaching past the API into shared storage
    without a project filter reads another suite's rows."""
    return [dict(r) for r in api.STORE.db.execute(
        "SELECT * FROM memory_edges WHERE project_id=? AND (src=? OR dst=?)",
        (PID, entity, entity))]

st, ents = call("GET", "/v1/entities?project=%s" % PID, None, KEY)
ids = [e["id"] for e in (ents.get("data") or ents.get("entities") or [])]
check("the person became an entity", PERSON in ids, ids[:12])
check("and the role account did not", "person:acme_billing@acme" not in ids, ids[:12])

rows = edges_of(PERSON)
check("an edge links the person to the company", len(rows) == 1, rows)
if rows:
    check("directed person -> company, named works_at",
          (rows[0]["src"], rows[0]["relation"], rows[0]["dst"])
          == (PERSON, "works_at", "company:acme"), rows[0])

st, al = call("GET", "/v1/assertions?project=%s" % PID, None, KEY)
emp = [a for a in al.get("data", [])
       if a["proposition"].startswith("rel_works_at")]
check("two mails from her yield ONE relation, not one per message",
      len(emp) == 1, [a["proposition"] for a in emp])
check("and one edge, not one per message", len(rows) == 1, rows)
if emp:
    check("carrying BOTH entities as subjects",
          sorted(emp[0]["subjects"]) == ["company:acme", PERSON],
          emp[0]["subjects"])

print("== it is recorded as a conclusion, not as something said ==")
if emp:
    st, w = call("GET", "/v1/assertions/%s/why?viewer=%s" % (emp[0]["id"], AGENT),
                 None, KEY)
    check("/why answers for it", st == 200, w)
    blob = json.dumps(w)
    check("the derivation kind is inference, not extraction",
          '"inference"' in blob, blob[:260])
    check("and it is grounded in the message it came from",
          w.get("grounded") is True or '"GROUNDED"' in blob, blob[:260])
    check("the evidence says what was actually observed",
          "sarah@acme.com" in blob, blob[:260])

print("== the graph round-trips ==")
# The live projection and the boot rebuild must agree, or restarting rewrites
# history that as_of reads. Same invariant as tests_graph_live_projection.
d = _graph.rebuild_projection(api.STORE.db, P)
check("a rebuild reconciles nothing", d["reconciled"] == 0, d)
check("and drops nothing", d["dropped_dangling"] == 0, d)

print("== and this is what it was for: recall reaches the company ==")
# Name the PERSON and never the company. Passing "person:sarah_chen@acme"
# would prove nothing: the id contains "acme", so recall resolves the company
# straight out of the context string and reaches it without any edge at all.
st, pack = call("POST", "/v1/recall?project=%s" % PID,
                {"agent": AGENT, "context": "what has Sarah Chen agreed to",
                 "limit": 8}, KEY)
check("the context does not mention the company", "acme" not in
      "what has Sarah Chen agreed to".lower())
mems = pack.get("memories", [])
renew = [m for m in mems if "company:acme" in (m.get("subjects") or [])
         and not m["proposition"].startswith("rel_")]
check("asking about the person surfaces the company's memories", bool(renew),
      str(mems)[:240])
check("and says it travelled the relation to get there",
      any("reached through the memory graph" in (m.get("why_included") or "")
          for m in renew),
      str([m.get("why_included") for m in renew])[:240])
check("naming the path, so the reader can check it",
      any("works_at" in (m.get("path") or "") for m in renew),
      str([m.get("path") for m in renew])[:240])

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
