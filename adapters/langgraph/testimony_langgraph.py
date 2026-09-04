"""Emit a Testimony Record from a LangGraph human-in-the-loop flow.

    pip install langgraph
    # copy this file next to your graph. There is nothing else to install.

    from testimony_langgraph import Recorder

    rec = Recorder(
        agent={"id": "support-agent", "kind": "agent"},
        risk={"issue_refund": "high", "send_email": "medium"},
    )
    rec.invoke(graph, {"ticket": 41}, config)          # runs until an interrupt
    rec.approve(graph, config,                          # a person, from your auth
                approver={"id": "troy@example.com", "kind": "human"},
                identity_source="auth-session")
    rec.write("record.jsonl")

    python3 testimony_validate.py record.jsonl          # Conformance: TR-4

The specification: https://datatracker.ietf.org/doc/draft-clifford-testimony-record/

WHAT THIS CANNOT DO, WHICH IS THE POINT.

LangGraph pauses a graph with interrupt() and resumes it with
Command(resume=value). The resume payload says which interrupt it answers and
carries a value. It has no field for who answered, and no principal is modelled
anywhere on that boundary, so any code holding the thread can resume it,
including the process that raised the pause.

That is not a defect in LangGraph. It is a memory and orchestration library and
it never claimed to be an authorisation layer. But it means an approval flow
built on interrupt() produces, by default, a record in which a run where an
engineer read the arguments and decided is indistinguishable from one where a
script resumed everything automatically.

This adapter does not fix that by inventing an approver, because the identity
does not exist anywhere for it to find. It fixes it by refusing to write an
approval unless the caller supplies an identity from their own authentication
layer, and by making the omission visible instead of silent: resume the graph
without going through approve() or refuse() and the record still says exactly
what happened, it simply does not reach TR-3.

The three things it will not do, each of which the specification says a reader
cannot otherwise detect:

  * It will not classify risk from anything the model produced. Risk comes from
    a table you own, and an action missing from that table raises rather than
    defaulting, because a default risk class is a guess wearing a policy's
    clothes.
  * It will not accept an identity_source the proposing model could have
    written.
  * It will not let the acting agent approve its own action.

Copyright 2026 Michael Brandon Clifford. MIT licensed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys

SPEC = "testimony-record/0.2"
RISK = ("low", "medium", "high")

# Identity that the proposing model could have written is not identity. This is
# the same list the reference validator refuses, kept here so the adapter fails
# at emit time rather than leaving the caller to discover it at validation.
UNTRUSTED = {"model", "plan", "request", "request-body", "prompt", "agent"}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canon(entry: dict) -> str:
    return json.dumps({k: v for k, v in entry.items() if not k.startswith("_")},
                      sort_keys=True, separators=(",", ":"))


class SelfApproval(Exception):
    """The approver and the proposer are the same principal."""


class UntrustedIdentity(Exception):
    """The approver's identity came from somewhere the model can write."""


class UnclassifiedAction(Exception):
    """The action is not in the risk table, and guessing is not allowed."""


class Recorder:
    """Accumulates a Testimony Record while a LangGraph graph runs.

    The recorder holds no state belonging to the graph. It observes the public
    surface only: invoke, get_state, and Command(resume=...). Nothing is
    monkeypatched, so a LangGraph upgrade that keeps those three working keeps
    this working.
    """

    def __init__(self, *, agent: dict, risk, acts: bool = True,
                 risk_source: str = "registry"):
        if not isinstance(agent, dict) or "id" not in agent:
            raise ValueError("agent must be an actor object with an id")
        if risk_source.lower() in UNTRUSTED:
            raise UntrustedIdentity(
                "risk_source %r names something the proposing model can write; "
                "a risk class the model chose is not a gate" % risk_source)
        self.agent = dict(agent)
        self.agent.setdefault("kind", "agent")
        self._risk = risk
        self.risk_source = risk_source
        self.entries: list[dict] = []
        self._n = 0
        self._pending: dict | None = None   # the decision awaiting a verdict

        self._add("scope", acts=bool(acts),
                  declared_by={"id": "testimony-langgraph", "kind": "system"})

    # ── record construction ──────────────────────────────────────────────────

    def _id(self, prefix: str) -> str:
        self._n += 1
        return "%s_%d" % (prefix, self._n)

    def _add(self, type_: str, **fields) -> str:
        eid = fields.pop("id", None) or self._id(type_[0])
        entry = {"spec": SPEC, "type": type_, "id": eid, "at": _now()}
        entry.update(fields)
        self.entries.append(entry)
        return eid

    def cite(self, kind: str, source: str, *, digest: str | None = None,
             excerpt: str | None = None) -> str:
        """Record where something came from. Content is withheld by default: a
        citation with a digest lets the holder of the source show it unchanged
        without the record becoming a second copy of it."""
        e: dict = {"kind": kind, "source": source}
        if digest:
            e["digest"] = digest
        if excerpt is not None:
            e["excerpt"] = str(excerpt)[:4096]
        else:
            e["redacted"] = True
        return self._add("evidence", **e)

    def believe(self, subject: str, proposition: str, *, evidence=None,
                polarity: str = "affirm", state: str = "believed_true") -> str:
        """State a belief. `evidence` may be empty, and an empty list is an
        assertion that nothing supports this, which must stay expressible."""
        return self._add("belief", subject=subject, proposition=proposition,
                         polarity=polarity, state=state,
                         asserted_by=dict(self.agent),
                         evidence=list(evidence or []))

    # ── the gate ─────────────────────────────────────────────────────────────

    def _risk_for(self, action: str) -> str:
        cls = self._risk(action) if callable(self._risk) else self._risk.get(action)
        if cls not in RISK:
            raise UnclassifiedAction(
                "no risk class for action %r. Add it to the risk table. This "
                "adapter will not default, because a default is a guess and the "
                "whole point of the class is that the model did not choose it."
                % action)
        return cls

    def invoke(self, graph, payload, config, **kw):
        """Run the graph. Any interrupt it stops on becomes a decision entry.

        The interrupted node is expected to call interrupt() with a mapping
        carrying an "action" key, which is what the risk table is keyed on:

            interrupt({"action": "issue_refund", "args": {"amount": 4200}})

        Anything else raises, because an action this adapter cannot name is an
        action it cannot classify.
        """
        result = graph.invoke(payload, config, **kw)
        for it in getattr(graph.get_state(config), "interrupts", ()) or ():
            self._propose(it)
        return result

    def _propose(self, it) -> None:
        value = getattr(it, "value", None)
        if not isinstance(value, dict) or "action" not in value:
            raise UnclassifiedAction(
                "interrupt payload must be a mapping with an 'action' key; got "
                "%r. The action name is what the risk table is keyed on."
                % (value,))
        action = str(value["action"])
        self._pending = {
            "action_type": action,
            "risk_class": self._risk_for(action),
            "risk_source": self.risk_source,
            "proposed_by": dict(self.agent),
            "interrupt_id": getattr(it, "id", None),
            "args": value.get("args"),
        }

    def approve(self, graph, config, *, approver: dict, identity_source: str,
                resume=True, **kw):
        """Permit the pending action and resume the graph.

        `approver` must be a person and `identity_source` must name where their
        identity came from. Both are required because neither can be recovered
        afterwards, and a record that cannot say who approved is the failure
        this adapter exists to remove.
        """
        d = self._require_pending()
        self._check_approver(approver, identity_source, d)

        did = self._add("decision", action_type=d["action_type"],
                        risk_class=d["risk_class"], risk_source=d["risk_source"],
                        proposed_by=d["proposed_by"], verdict="permitted",
                        executed=True, args=d["args"])
        aid = self._add("approval", decision=did, approver=dict(approver),
                        identity_source=identity_source, method="langgraph-resume")
        # The decision points back at its approval so a reader does not have to
        # scan the file to find out whether a high-risk action had one.
        for e in self.entries:
            if e["id"] == did:
                e["approval"] = aid
        self._pending = None

        from langgraph.types import Command
        return graph.invoke(Command(resume=resume), config, **kw)

    def refuse(self, graph, config, *, reason: str, approver: dict | None = None,
               identity_source: str | None = None, resume=False, **kw):
        """Refuse the pending action, with a reason, and resume the graph so it
        can take the refusal path. A refusal is recorded with the same standing
        as a permission; a system that only records what it did is a receipt."""
        d = self._require_pending()
        if not reason:
            raise ValueError("a refusal without a reason is not a refusal")
        if approver is not None:
            self._check_approver(approver, identity_source or "", d)

        did = self._add("decision", action_type=d["action_type"],
                        risk_class=d["risk_class"], risk_source=d["risk_source"],
                        proposed_by=d["proposed_by"], verdict="refused",
                        executed=False, reason=reason, args=d["args"])
        if approver is not None:
            self._add("approval", decision=did, approver=dict(approver),
                      identity_source=identity_source, method="langgraph-resume")
        self._pending = None

        from langgraph.types import Command
        return graph.invoke(Command(resume=resume), config, **kw)

    def _require_pending(self) -> dict:
        if self._pending is None:
            raise RuntimeError(
                "no pending action. Call invoke() and let the graph reach an "
                "interrupt before approving or refusing.")
        return self._pending

    def _check_approver(self, approver: dict, identity_source: str, d: dict):
        if not isinstance(approver, dict) or "id" not in approver:
            raise ValueError("approver must be an actor object with an id")
        if approver.get("kind", "human") != "human":
            raise ValueError(
                "an approver must be a person; kind was %r" % approver.get("kind"))
        src = str(identity_source or "").lower()
        if not src or src in UNTRUSTED:
            raise UntrustedIdentity(
                "identity_source %r is empty or names something the proposing "
                "model can write. Take the identity from your authenticated "
                "session, not from the resume payload." % identity_source)
        if approver.get("id") == d["proposed_by"].get("id"):
            raise SelfApproval(
                "approver %r is the principal that proposed the action. An "
                "agent's own credential signing off its own action satisfies "
                "every other requirement and is worth nothing." % approver["id"])

    # ── output ───────────────────────────────────────────────────────────────

    def integrity(self) -> str:
        """Anchor the record. The digest covers every entry written so far, so
        any later alteration of the file is detectable by anyone holding this
        value. It does not prove the whole file was not rewritten by whoever
        produced it; that needs an external anchor, and this scheme does not
        claim to be one."""
        covered = [e["id"] for e in self.entries]
        digest = hashlib.sha256(
            "\n".join(_canon(e) for e in self.entries).encode()).hexdigest()
        return self._add("integrity", scheme="hash-chain",
                         digest="sha256:" + digest, covers=covered)

    def record(self) -> list[dict]:
        if self._pending is not None:
            raise RuntimeError(
                "an action is still pending a verdict. Call approve() or "
                "refuse() before writing the record, or the file will describe "
                "a gate that never closed.")
        if not any(e["type"] == "integrity" for e in self.entries):
            self.integrity()
        return list(self.entries)

    def warnings(self) -> list[str]:
        """What this record will not demonstrate, said out loud."""
        out = []
        decisions = [e for e in self.entries if e["type"] == "decision"]
        approvals = {e.get("decision") for e in self.entries
                     if e["type"] == "approval"}
        if not decisions:
            out.append(
                "no decisions recorded: the graph never reached an interrupt, so "
                "this record cannot demonstrate a gate")
        for d in decisions:
            if d["risk_class"] == "high" and d.get("executed") and \
                    d["id"] not in approvals:
                out.append(
                    "decision %s is high risk and executed with no approval "
                    "entry; the record will not reach TR-3" % d["id"])
        return out

    def write(self, path) -> str:
        entries = self.record()
        text = "\n".join(json.dumps(e, sort_keys=False) for e in entries) + "\n"
        if path in ("-", None):
            sys.stdout.write(text)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        for w in self.warnings():
            print("warning: " + w, file=sys.stderr)
        return text
