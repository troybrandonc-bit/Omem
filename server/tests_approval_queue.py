"""The queue holds an action without dropping it or doing it.
Run: python3 tests_approval_queue.py

The free gate is synchronous: the approver is already there. An organisation
approves nothing that way. The action is proposed at 02:00, the person who may
approve it is asleep, and something has to hold it.

What these tests are mostly about is the ways a hold can go wrong. An item
nobody came to must end as a refusal rather than as silence, because a record
showing a proposal and then nothing cannot answer whether the thing ran. A
policy has to be re-read when the decision is made, because the reason policies
change is that somebody's authority was revoked. And every rule the free gate
enforces about who may approve has to survive the approval arriving an hour
later instead of in the same request.

Copyright 2026 Michael Brandon Clifford. Commercial licence required for
production use. See ee/LICENSE.
"""
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ee import approval_policy as POLICY   # noqa: E402
from ee import approval_queue as Q         # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:240])


def refuses(name, fn, fragment=""):
    try:
        fn()
        check(name, False, "it was allowed")
    except Q.QueueError as e:
        check(name, (fragment in str(e)) if fragment else True,
              "wrong reason: %s" % e)
    except Exception as e:                                   # noqa: BLE001
        check(name, False, "raised %s: %s" % (type(e).__name__, e))


db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
Q.ensure_schema(db)

P = "proj_1"
AGENT = "agent:refunder"
T0 = 1_760_000_000.0


def held(**kw):
    kw.setdefault("action_type", "issue_refund")
    kw.setdefault("risk_class", "high")
    kw.setdefault("proposed_by", AGENT)
    kw.setdefault("now", T0)
    return Q.hold(db, P, **kw)


print("== an action can be held ==")
it = held(payload={"amount": "38.60 EUR"}, reason="customer asked")
check("it starts pending", it["state"] == Q.PENDING, it["state"])
check("it remembers what was proposed and by whom",
      it["action_type"] == "issue_refund" and it["proposed_by"] == AGENT)
check("it carries the payload", it["payload"]["amount"] == "38.60 EUR")
check("it has a deadline", it["expires_at"] > it["created"])
check("it appears in the queue", [x["id"] for x in
                                  Q.pending(db, P, now=T0)] == [it["id"]])

refuses("an item that never expires is refused",
        lambda: held(ttl_seconds=0), "must expire")
refuses("an item needing nobody is refused", lambda: held(needs=0), "no approvals")
refuses("an item with no proposer is refused",
        lambda: held(proposed_by=" "), "who proposed it")

print("\n== the proposer cannot approve their own action ==")
allowed = [x["id"] for x in Q.pending(db, P, principal=AGENT, now=T0)]
check("it is not offered to the agent that proposed it", allowed == [], allowed)
refuses("and deciding anyway is refused",
        lambda: Q.decide(db, it["id"], AGENT, "approve", "auth-session", now=T0),
        "cannot be the proposer")

print("\n== a decision names the person and where the name came from ==")
refuses("an unnamed caller cannot settle anything",
        lambda: Q.decide(db, it["id"], "  ", "approve", "auth-session", now=T0),
        "authenticated principal")
refuses("a decision with no identity source is refused",
        lambda: Q.decide(db, it["id"], "sam@acme.com", "approve", "", now=T0),
        "where the approver's identity came from")
refuses("an invented verdict is refused",
        lambda: Q.decide(db, it["id"], "sam@acme.com", "maybe", "auth-session",
                         now=T0),
        "approve or refuse")

got = Q.decide(db, it["id"], "sam@acme.com", "approve", "auth-session",
               reason="net of the balance", now=T0 + 60)
check("an approval settles a one-approver item", got["state"] == Q.APPROVED,
      got["state"])
check("and the act records who and how",
      Q.acts(db, it["id"])[0]["principal"] == "sam@acme.com"
      and Q.acts(db, it["id"])[0]["identity_source"] == "auth-session")
refuses("the same item cannot be settled twice",
        lambda: Q.decide(db, it["id"], "dana@acme.com", "approve",
                         "auth-session", now=T0 + 90),
        "already approved")

print("\n== nobody approving is a refusal, not a silence ==")
old = held(reason="nobody will come", ttl_seconds=3600)
gone = Q.sweep(db, P, now=T0 + 3601)
check("the deadline passes and the item is swept",
      [g["id"] for g in gone] == [old["id"]], gone)
after = Q.get(db, old["id"])
check("its state is expired", after["state"] == Q.EXPIRED, after["state"])
check("and it says why, in a sentence",
      "nobody approved it within" in (after["settled_reason"] or ""),
      after["settled_reason"])
check("an expired item is not in the queue",
      old["id"] not in [x["id"] for x in Q.pending(db, P, now=T0 + 3601)])
refuses("and it cannot be approved after the fact",
        lambda: Q.decide(db, old["id"], "sam@acme.com", "approve",
                         "auth-session", now=T0 + 4000),
        "already expired")

print("\n== policy is re-read when the decision is made ==")
# The reason a policy changes is usually that somebody's authority was
# revoked. A queue that filters on read and trusts on write can be walked
# through by anybody holding a stale item id.
pol = POLICY.parse({"default": "deny", "rules": [
    {"action_type": "issue_refund", "approvers": ["finance@acme.com"]}]})
allow = lambda a, r, p, n: POLICY.evaluate(pol, a, r, str(p), str(n))  # noqa: E731

live = held(reason="policy applies to this one")
seen = [x["id"] for x in Q.pending(db, P, principal="finance@acme.com",
                                   policy_check=allow, now=T0)]
check("the queue offers it to the person the policy names",
      live["id"] in seen, seen)
seen = [x["id"] for x in Q.pending(db, P, principal="sam@acme.com",
                                   policy_check=allow, now=T0)]
check("and not to somebody the policy does not name", live["id"] not in seen)
refuses("who is refused if they try with an id they kept",
        lambda: Q.decide(db, live["id"], "sam@acme.com", "approve",
                         "auth-session", policy_check=allow, now=T0),
        "policy")
ok = Q.decide(db, live["id"], "finance@acme.com", "approve", "oidc",
              policy_check=allow, now=T0 + 5)
check("the named approver settles it", ok["state"] == Q.APPROVED, ok["state"])

print("\n== two approvers means two people ==")
two = held(needs=2, reason="over the threshold")
first = Q.decide(db, two["id"], "sam@acme.com", "approve", "auth-session",
                 now=T0 + 1)
check("one approval does not settle it", first["state"] == Q.PENDING,
      first["state"])
refuses("and the same person cannot supply the second",
        lambda: Q.decide(db, two["id"], "sam@acme.com", "approve",
                         "auth-session", now=T0 + 2),
        "already decided")
second = Q.decide(db, two["id"], "dana@acme.com", "approve", "oidc",
                  now=T0 + 3)
check("a second, different person settles it",
      second["state"] == Q.APPROVED, second["state"])
check("and both are on the record", len(Q.acts(db, two["id"])) == 2)

print("\n== one refusal settles it ==")
# Requiring everybody to refuse would keep an action live while somebody who
# has already objected waits for colleagues, which is the wrong default in the
# dangerous direction.
no = held(needs=2, reason="two needed, one objects")
out = Q.decide(db, no["id"], "sam@acme.com", "refuse", "auth-session",
               reason="the balance is disputed", now=T0 + 1)
check("a single refusal settles a two-approver item",
      out["state"] == Q.REFUSED, out["state"])
check("and the reason is the one that was given",
      out["settled_reason"] == "the balance is disputed", out["settled_reason"])

print("\n== the queue can produce a record ==")
entries = Q.as_entries(db, Q.get(db, two["id"]))
kinds = [e["type"] for e in entries]
check("an approved item is a decision and its approvals",
      kinds == ["decision", "approval", "approval"], kinds)
d = entries[0]
check("the decision is permitted and executed",
      d["verdict"] == "permitted" and d["executed"] is True, d)
check("it points at an approval that is present",
      d["approval"] == entries[1]["id"])
check("the approvers are people, not the agent",
      all(e["approver"]["kind"] == "human" for e in entries[1:]))
check("the identity source travels from the act, not from here",
      [e["identity_source"] for e in entries[1:]] == ["auth-session", "oidc"])
check("the risk class does not come from the proposing model",
      d["risk_source"] == "registry")

ref = Q.as_entries(db, Q.get(db, no["id"]))
check("a refused item is one decision, refused and not executed",
      len(ref) == 1 and ref[0]["verdict"] == "refused"
      and ref[0]["executed"] is False, ref)
check("and it says why it was refused",
      ref[0]["reason"] == "the balance is disputed", ref[0].get("reason"))

exp = Q.as_entries(db, Q.get(db, old["id"]))
check("an expired item is a refusal in the record too",
      exp[0]["verdict"] == "refused" and "nobody approved it within"
      in exp[0]["reason"], exp[0])

print("\n== the record the queue produces actually validates ==")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import testimony_validate as tv            # noqa: E402
import json                                # noqa: E402

# The scope entry has to precede the items, and T0 is a fixed epoch, so the
# date is derived from it rather than written out and left to drift.
_scope_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0 - 60))
body = ([{"spec": tv.SPEC, "type": "scope", "id": "s1",
          "at": _scope_at, "acts": True}]
        + Q.as_entries(db, Q.get(db, two["id"])))
rep = tv.validate("\n".join(json.dumps(e) for e in body))
check("a queue-produced record reaches TR-3", rep.level == "TR-3",
      [c["check"] for c in rep.checks if not c["ok"]])

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
