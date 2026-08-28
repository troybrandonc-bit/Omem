"""OMEM notices two entities are one person. Run: python3 tests_identity_resolution.py

The frozen engine has had coreference from the start -- merge, split, a
referent partition every query reduces subject sets through -- and nothing
above it ever proposed a merge. person:sarah_chen (named in a message body)
sat next to person:sarah_chen@acme (who wrote the mail), each holding half
the beliefs about one human, and only a caller who noticed the duplication
and called /v1/coreference by hand could join them.

resolution.py is the missing proposer. Decisive evidence (the same full name
in the same organisation -- the identity rule formation itself already
applies within one path) merges through the ordinary op path, attributed and
derivable. Suggestive evidence ("Sarah" against "Sarah Chen" at acme) becomes
a proposal that records NOTHING in the engine until a caller approves it.

Most of this suite is refusals, because an identity layer that guesses is
worse than none: never across organisations, never without one, never on
conflicting or role-word names, never when ambiguous, never re-proposing a
rejection, and -- above all -- never re-merging a pair a split separated.
A split is a person saying "these are different"; the machine does not
relitigate it, not even through its own approval queue.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_identity_resolution.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
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


OWNER = "resolve@kronos.com"

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
P = api.PROJECTS[PID]
AGENT = "agent:test"
call("POST", "/v1/agents?project=%s" % PID, {"id": AGENT, "kind": "system"}, KEY)


def ent(eid, label):
    kind = "organization" if eid.startswith("company:") else "person"
    st, r = call("POST", "/v1/entities?project=%s" % PID,
                 {"id": eid, "type": kind, "label": label}, KEY)
    check("entity %s created" % eid, st == 201, r)


def assert_(subjects, prop):
    st, r = call("POST", "/v1/assertions?project=%s" % PID,
                 {"agent": AGENT, "subjects": subjects, "proposition": prop}, KEY)
    check("assertion %s recorded" % prop, st == 201, r)
    return r.get("id")


def partition():
    st, r = call("GET", "/v1/coreference/partition?project=%s" % PID, None, KEY)
    return [set(c) for c in r.get("partition", [])]


def same_class(a, b):
    return any(a in c and b in c for c in partition())


def state_of(subjects, prop):
    st, r = call("POST", "/v1/queries/proposition-state?project=%s" % PID,
                 {"subjects": subjects, "proposition": prop}, KEY)
    return r.get("state")


print("== the world before: two ids for one person, and lookalikes ==")
ent("company:acme", "acme.com")
ent("company:globex", "globex.com")
# one human, two formation paths
ent("person:sarah_chen@acme", "Sarah Chen")
ent("person:sarah_chen", "Sarah Chen")
# a different human with the same name at another company
ent("person:sarah_chen@globex", "Sarah Chen")
# a different human with the same given name at the SAME company
ent("person:sarah_miller@acme", "Sarah Miller")
# suggestive, unambiguous: David and David Kim, both at acme
ent("person:david_kim@acme", "David Kim")
ent("person:david", "David")
# suggestive, to be rejected: Lisa and Lisa Park
ent("person:lisa_park@acme", "Lisa Park")
ent("person:lisa", "Lisa")
# ambiguous: Anna could be Anna Lee or Anna Wong
ent("person:anna_lee@acme", "Anna Lee")
ent("person:anna_wong@acme", "Anna Wong")
ent("person:anna", "Anna")
# no organisation anywhere near these two
ent("person:jane_doe", "Jane Doe")
ent("person:jane", "Jane")
# a role account wearing a company's name
ent("person:acme_billing@acme", "Acme Billing")
ent("person:acme_billing", "Acme Billing")

# anchors: live edges place the suffix-less ids inside acme. Deliberately not
# all works_at -- managed_by and involves anchor a person to an organisation's
# orbit just as well, and the anchor must be relation-agnostic.
assert_(["person:sarah_chen", "company:acme"], "rel_works_at_acme")
assert_(["person:sarah_chen@acme", "company:acme"], "rel_works_at_acme")
assert_(["company:acme", "person:david"], "rel_involves_david")
assert_(["company:acme", "person:lisa"], "rel_managed_by_lisa")
assert_(["company:acme", "person:anna"], "rel_involves_anna")

# the belief that makes the merge worth having: stored about ONE of the ids
assert_(["person:sarah_chen"], "prefers_annual_billing")
check("before any merge, the alias knows nothing",
      state_of(["person:sarah_chen@acme"], "prefers_annual_billing") == "UNKNOWN")

print("== a dry run records nothing anywhere ==")
st, dry = call("POST", "/v1/memory/resolve?project=%s" % PID, {"apply": False}, KEY)
check("dry run answers", st == 200, dry)
check("it says what WOULD merge",
      any(sorted(m["pair"]) == ["person:sarah_chen", "person:sarah_chen@acme"]
          for m in dry.get("merged", [])), dry.get("merged"))
check("but the partition is untouched",
      not same_class("person:sarah_chen", "person:sarah_chen@acme"))
st, props = call("GET", "/v1/memory/merge-proposals?project=%s" % PID, None, KEY)
check("and no proposal was written", props.get("count") == 0, props)

print("== the real pass: decisive merges, suggestive proposals, refusals ==")
st, r1 = call("POST", "/v1/memory/resolve?project=%s" % PID, {}, KEY)
check("resolve answers", st == 200, r1)
merged_pairs = [sorted(m["pair"]) for m in r1.get("merged", [])]
check("same full name at the same organisation merged",
      ["person:sarah_chen", "person:sarah_chen@acme"] in merged_pairs, merged_pairs)
check("and it is the ONLY merge -- everything else refused or proposed",
      len(merged_pairs) == 1, merged_pairs)
check("the engine partition now holds one referent",
      same_class("person:sarah_chen", "person:sarah_chen@acme"))
check("Sarah Chen at globex was NOT pulled in",
      not same_class("person:sarah_chen", "person:sarah_chen@globex"))
check("Sarah Miller was NOT pulled in",
      not same_class("person:sarah_chen@acme", "person:sarah_miller@acme"))

reasons = " | ".join(x["reason"] for x in r1.get("refused", []))
check("refused across organisations", "different organisations" in reasons, reasons)
check("refused with no organisation anchor", "no organisation anchors" in reasons, reasons)
check("refused the ambiguous Anna", "ambiguous" in reasons, reasons)
check("Anna merged with neither candidate",
      not same_class("person:anna", "person:anna_lee@acme")
      and not same_class("person:anna", "person:anna_wong@acme"))
blob = json.dumps(r1)
check("role names were never candidates at all", "acme_billing" not in blob, blob[:200])
check("and the role pair stayed separate",
      not same_class("person:acme_billing", "person:acme_billing@acme"))

prop_pairs = [sorted(x["pair"]) for x in r1.get("proposed", [])]
check("David/David Kim became a proposal, not a merge",
      ["person:david", "person:david_kim@acme"] in prop_pairs, prop_pairs)
check("and the proposal alone changed no engine state",
      not same_class("person:david", "person:david_kim@acme"))

print("== this is what it was for: beliefs cross the merge ==")
check("asking the alias now finds the belief",
      state_of(["person:sarah_chen@acme"], "prefers_annual_billing") == "BELIEVED_TRUE")

cor_id = next(m["coreference"] for m in r1["merged"]
              if sorted(m["pair"]) == ["person:sarah_chen", "person:sarah_chen@acme"])
st, why = call("GET", "/v1/assertions/%s/why?project=%s&viewer=%s"
               % (cor_id, PID, AGENT), None, KEY)
check("/why answers for the merge itself", st == 200, why)
wblob = json.dumps(why)
check("recorded as a conclusion, not something someone said",
      '"inference"' in wblob, wblob[:260])

print("== idempotent: a second pass changes nothing ==")
st, r2 = call("POST", "/v1/memory/resolve?project=%s" % PID, {}, KEY)
check("no new merges", len(r2.get("merged", [])) == 0, r2.get("merged"))
check("the merged pair is recognised, not re-merged",
      r2.get("already_merged", 0) >= 1, r2)
check("open proposals are reported, not duplicated",
      all(x.get("existing") for x in r2.get("proposed", [])), r2.get("proposed"))

print("== the queue: approve is a human's judgment under their name ==")
st, listing = call("GET", "/v1/memory/merge-proposals?project=%s&status=open"
                   % PID, None, KEY)
by_pair = {tuple(sorted((d["entity_a"], d["entity_b"]))): d
           for d in listing.get("data", [])}
david = by_pair.get(("person:david", "person:david_kim@acme"))
lisa = by_pair.get(("person:lisa", "person:lisa_park@acme"))
check("both proposals are in the queue", david is not None and lisa is not None,
      list(by_pair))

st, ap = call("POST", "/v1/memory/merge-proposals/%s/approve?project=%s"
              % (david["id"], PID), {"agent": AGENT}, KEY)
check("approve answers", st == 200, ap)
check("and now the pair is one referent",
      same_class("person:david", "person:david_kim@acme"))
cor2 = api.PROJECTS[PID].engine.store.assertion(ap.get("coreference", ""))
check("the coreference is attributed to the APPROVER, not the machine",
      cor2 is not None and cor2.agent == AGENT, getattr(cor2, "agent", None))
st, ap2 = call("POST", "/v1/memory/merge-proposals/%s/approve?project=%s"
               % (david["id"], PID), {"agent": AGENT}, KEY)
check("approving twice is refused", st == 409, ap2)

st, rj = call("POST", "/v1/memory/merge-proposals/%s/reject?project=%s"
              % (lisa["id"], PID), {"agent": AGENT}, KEY)
check("reject answers", st == 200, rj)
st, r3 = call("POST", "/v1/memory/resolve?project=%s" % PID, {}, KEY)
r3_reasons = " | ".join(x["reason"] for x in r3.get("refused", []))
check("a rejected pair is never proposed again",
      "previously rejected" in r3_reasons
      and not any("lisa" in json.dumps(x) for x in r3.get("proposed", [])),
      r3_reasons)
check("and Lisa stays separate",
      not same_class("person:lisa", "person:lisa_park@acme"))

print("== a split is final for the machine ==")
st, sp = call("POST", "/v1/coreference/split?project=%s" % PID,
              {"coreference_id": cor_id, "agent": AGENT}, KEY)
check("the merge can be undone by a person", st == 201, sp)
check("and the referents separate again",
      not same_class("person:sarah_chen", "person:sarah_chen@acme"))
st, r4 = call("POST", "/v1/memory/resolve?project=%s" % PID, {}, KEY)
check("the machine does NOT re-merge what a person split",
      len(r4.get("merged", [])) == 0, r4.get("merged"))
check("it says why", "a split recorded these as different people" in
      " | ".join(x["reason"] for x in r4.get("refused", [])), r4.get("refused"))

print("== replay: every identity decision reconstructs from the op log ==")
p2 = api.Project(PID, "replay")
for op in api.STORE.ops_for(PID):
    p2.clock = max(p2.clock, op["clock"])
    api.apply_op(p2, op["kind"], op["args"])
part2 = [set(c) for c in p2.engine.referent_partition(p2.now())]
check("the approved merge survives replay",
      any("person:david" in c and "person:david_kim@acme" in c for c in part2))
check("and the split survives replay too",
      not any("person:sarah_chen" in c and "person:sarah_chen@acme" in c
              for c in part2))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
