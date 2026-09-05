"""Actions waiting for a person, and what happens when nobody comes.

The MIT gate is synchronous. A plan arrives with an approver already attached,
and the gate says yes or no in one request. That works when the approver is
standing over the agent, and it is not how an organisation approves anything.
In an organisation the action is proposed at 02:00, the person who may approve
it is asleep, and something has to hold the action without either dropping it
or doing it.

This is that hold. `ee/approval_policy.py` already answers who may approve
what; this answers where the action waits meanwhile, who can see it, and what
its fate is if nobody acts.

WHAT IT REFUSES, WHICH IS MOST OF THE DESIGN.

**An expired item is refused, not forgotten.** A queue that quietly drops
whatever nobody got to is the worst possible audit answer: the record shows a
proposal and then nothing, and no one can say whether it ran. Expiry writes a
refusal with a reason, so the question "what happened to it" always has an
answer.

**Policy is re-checked when the decision is made, not when the list was
drawn.** A queue that filters on read and trusts on write can be walked
through by anybody who kept a stale item id, and policies change precisely
because somebody's authority was revoked.

**The principal decides, never a name in the request.** The approver is who the
authentication layer resolved. A name in a body is an assertion about a person
rather than a fact about one, and the whole value of the resulting record turns
on that distinction.

**The proposer cannot approve their own action**, however the name is spelled,
which is the free gate's rule and does not get weaker because the approval
arrived later.

**Nobody approves twice.** Where a policy needs two people, one person holding
two credentials is one person.

This module knows nothing about licensing and opens no sockets. The caller
decides whether the queue applies at all, which keeps the commercial concern
out of the mechanism and lets both be tested alone.

Copyright 2026 Michael Brandon Clifford. Commercial licence required for
production use. See LICENSE.
"""
from __future__ import annotations

import json
import time
import uuid

APPROVAL_QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_queue(
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  risk_class TEXT NOT NULL,
  risk_source TEXT NOT NULL,
  proposed_by TEXT NOT NULL,
  payload TEXT,
  reason TEXT,
  needs INTEGER NOT NULL DEFAULT 1,
  state TEXT NOT NULL,              -- pending | approved | refused | expired
  created REAL NOT NULL,
  expires_at REAL,
  settled REAL,
  settled_reason TEXT);
CREATE INDEX IF NOT EXISTS aq_pending ON approval_queue(project_id, state, created);
-- One row per person per item, so a second approval by the same principal is a
-- primary key violation rather than a policy that has to remember.
CREATE TABLE IF NOT EXISTS approval_queue_acts(
  item_id TEXT NOT NULL,
  principal TEXT NOT NULL,
  verdict TEXT NOT NULL,            -- approve | refuse
  reason TEXT,
  identity_source TEXT NOT NULL,
  ts REAL NOT NULL,
  PRIMARY KEY(item_id, principal));
CREATE INDEX IF NOT EXISTS aq_acts ON approval_queue_acts(item_id, ts);
"""

PENDING, APPROVED, REFUSED, EXPIRED = "pending", "approved", "refused", "expired"


class QueueError(ValueError):
    """Something the queue will not do, with the reason a caller can show."""


def ensure_schema(db):
    db.executescript(APPROVAL_QUEUE_SCHEMA)


def _row(r) -> dict:
    d = dict(r)
    d["payload"] = json.loads(d["payload"]) if d.get("payload") else {}
    return d


def hold(db, project_id: str, action_type: str, risk_class: str,
         proposed_by: str, risk_source: str = "registry", payload=None,
         reason: str = "", needs: int = 1, ttl_seconds: int = 86400,
         now: float | None = None) -> dict:
    """Put an action in the queue and return the item.

    `needs` is how many distinct principals must approve. `ttl_seconds` is how
    long before it expires into a refusal, and there is no option for never:
    an action that can wait forever is one nobody has to answer for.
    """
    if not action_type or not str(proposed_by).strip():
        raise QueueError("an item names the action and who proposed it")
    if needs < 1:
        raise QueueError("an item needing no approvals does not belong in a queue")
    if ttl_seconds <= 0:
        raise QueueError("an item must expire; a request that waits forever is "
                         "one nobody has to answer for")
    t = time.time() if now is None else now
    item = {
        "id": "aq_" + uuid.uuid4().hex[:16], "project_id": project_id,
        "action_type": action_type, "risk_class": risk_class,
        "risk_source": risk_source, "proposed_by": str(proposed_by),
        "payload": json.dumps(payload or {}), "reason": reason,
        "needs": int(needs), "state": PENDING, "created": t,
        "expires_at": t + ttl_seconds, "settled": None, "settled_reason": None,
    }
    db.execute(
        "INSERT INTO approval_queue(id,project_id,action_type,risk_class,"
        "risk_source,proposed_by,payload,reason,needs,state,created,expires_at,"
        "settled,settled_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        tuple(item[k] for k in (
            "id", "project_id", "action_type", "risk_class", "risk_source",
            "proposed_by", "payload", "reason", "needs", "state", "created",
            "expires_at", "settled", "settled_reason")))
    return _row(item)


def get(db, item_id: str) -> dict | None:
    r = db.execute("SELECT * FROM approval_queue WHERE id=?", (item_id,)).fetchone()
    return _row(r) if r else None


def acts(db, item_id: str) -> list:
    return [dict(r) for r in db.execute(
        "SELECT * FROM approval_queue_acts WHERE item_id=? ORDER BY ts",
        (item_id,))]


def sweep(db, project_id: str = "", now: float | None = None) -> list:
    """Expire what nobody came to, as refusals.

    Called before any listing or decision, so an expired item cannot be acted
    on by somebody whose page was open when the deadline passed.
    """
    t = time.time() if now is None else now
    q = ("SELECT * FROM approval_queue WHERE state=? AND expires_at IS NOT NULL "
         "AND expires_at <= ?")
    args = [PENDING, t]
    if project_id:
        q += " AND project_id=?"
        args.append(project_id)
    gone = [_row(r) for r in db.execute(q, tuple(args))]
    for it in gone:
        db.execute("UPDATE approval_queue SET state=?, settled=?, "
                   "settled_reason=? WHERE id=?",
                   (EXPIRED, t,
                    "nobody approved it within %d seconds of it being proposed"
                    % int(round(it["expires_at"] - it["created"])), it["id"]))
    return gone


def pending(db, project_id: str, principal: str = "", policy_check=None,
            now: float | None = None) -> list:
    """What is waiting, and for this principal what they may actually act on.

    `policy_check(action_type, risk_class, principal, name) -> (ok, why)` is
    ee.approval_policy.evaluate bound to the project's policy, or None when no
    policy applies. Filtering here is a courtesy to the reader; the decision is
    checked again in `decide`, because a policy can change while a page is
    open.
    """
    sweep(db, project_id, now)
    out = []
    for r in db.execute(
            "SELECT * FROM approval_queue WHERE project_id=? AND state=? "
            "ORDER BY created", (project_id, PENDING)):
        it = _row(r)
        if principal:
            allowed, why = _may(db, it, principal, policy_check)
            if not allowed:
                continue
            it["why_you"] = why
        out.append(it)
    return out


def _may(db, item: dict, principal: str, policy_check) -> tuple:
    """Whether this principal may settle this item, and why not when they can't.

    Every reason here is one a person should be shown. "You proposed this" is a
    better answer than an empty list, which is what a queue that silently
    filters gives them.
    """
    if not str(principal or "").strip():
        raise QueueError("an approval is settled by an authenticated principal, "
                         "not by an unnamed caller")
    if item["state"] != PENDING:
        return False, "this was already %s" % item["state"]
    if str(principal) == str(item["proposed_by"]):
        return False, ("you proposed this action, and the approver cannot be "
                       "the proposer")
    if any(a["principal"] == str(principal) for a in acts(db, item["id"])):
        return False, "you have already decided on this one"
    if policy_check is not None:
        ok, why = policy_check(item["action_type"], item["risk_class"],
                               principal, "")
        if not ok:
            return False, why or "the approval policy does not permit you to " \
                                 "approve this"
    return True, "you may approve this"


def decide(db, item_id: str, principal: str, verdict: str,
           identity_source: str, reason: str = "", policy_check=None,
           now: float | None = None) -> dict:
    """Approve or refuse, as this principal, and settle the item if that is enough.

    Returns the item as it now stands. Raises QueueError when this principal
    may not do this, with a reason meant to be shown to them.
    """
    if verdict not in ("approve", "refuse"):
        raise QueueError("a verdict is approve or refuse")
    if not str(identity_source or "").strip():
        raise QueueError("record where the approver's identity came from; a "
                         "name with no source is an assertion about a person "
                         "rather than a fact about one")
    t = time.time() if now is None else now
    sweep(db, "", t)

    item = get(db, item_id)
    if item is None:
        raise QueueError("no such item")
    allowed, why = _may(db, item, principal, policy_check)
    if not allowed:
        raise QueueError(why)

    db.execute("INSERT INTO approval_queue_acts(item_id,principal,verdict,"
               "reason,identity_source,ts) VALUES(?,?,?,?,?,?)",
               (item_id, str(principal), verdict, reason,
                str(identity_source), t))

    # One refusal settles it. Requiring everybody to refuse would mean an
    # action stays live while somebody who has already objected waits for
    # colleagues, which is the wrong default for the dangerous direction.
    if verdict == "refuse":
        db.execute("UPDATE approval_queue SET state=?, settled=?, "
                   "settled_reason=? WHERE id=?",
                   (REFUSED, t, reason or "refused by %s" % principal, item_id))
    else:
        yes = sum(1 for a in acts(db, item_id) if a["verdict"] == "approve")
        if yes >= item["needs"]:
            db.execute("UPDATE approval_queue SET state=?, settled=?, "
                       "settled_reason=? WHERE id=?",
                       (APPROVED, t, "approved by %d of %d required"
                        % (yes, item["needs"]), item_id))
    return get(db, item_id)


def as_entries(db, item: dict, spec: str = "testimony-record/0.2") -> list:
    """The item as Testimony Record entries: the decision, and each approval.

    A queue that cannot produce a record is a workflow tool. The identity
    source travels from the act rather than being asserted here, because that
    is the member an auditor will lean on hardest.
    """
    settled = item.get("settled") or item["created"]

    def at(ts):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

    out = []
    approvals = [a for a in acts(db, item["id"]) if a["verdict"] == "approve"]
    executed = item["state"] == APPROVED
    d = {"spec": spec, "type": "decision", "id": item["id"],
         "at": at(item["created"]), "action_type": item["action_type"],
         "risk_class": item["risk_class"], "risk_source": item["risk_source"],
         "proposed_by": {"id": item["proposed_by"], "kind": "agent"},
         "verdict": "permitted" if executed else "refused",
         "executed": bool(executed)}
    if not executed:
        d["reason"] = item.get("settled_reason") or "not approved"
    if executed and approvals:
        d["approval"] = "%s_a1" % item["id"]
    out.append(d)
    for i, a in enumerate(approvals, 1):
        out.append({"spec": spec, "type": "approval",
                    "id": "%s_a%d" % (item["id"], i), "at": at(a["ts"]),
                    "decision": item["id"],
                    "approver": {"id": a["principal"], "kind": "human"},
                    "identity_source": a["identity_source"],
                    **({"note": a["reason"]} if a.get("reason") else {})})
    return out
