#!/usr/bin/env python3
"""A refund desk in LangGraph that can say who approved the refund.

    pip install langgraph
    python3 example.py > record.jsonl
    python3 ../../scripts/testimony_validate.py record.jsonl

Fifty lines of ordinary LangGraph, plus six lines of recorder. The graph is
deliberately dull: it forms a belief about a customer, proposes a refund, and
pauses for a person. That is the shape most human-in-the-loop agents already
have, which is the point. Nothing here is specific to any memory product.

Run it and the record reaches TR-4. Delete the approver argument and it stops
at TR-2, which is the honest state of every such graph today.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt
from typing_extensions import TypedDict

from testimony_langgraph import Recorder


class State(TypedDict, total=False):
    ticket: int
    amount: int
    refunded: bool


def assess(state: State) -> State:
    # A real agent would reason here. What matters for the record is that the
    # belief it lands on is written down with what it rested on.
    return {"amount": 4200}


def gate(state: State) -> State:
    # The payload names the action. That name is what the risk table is keyed
    # on, and the table belongs to the operator, not to the model.
    ok = interrupt({"action": "issue_refund",
                    "args": {"ticket": state["ticket"],
                             "amount": state["amount"]}})
    return {"refunded": bool(ok)}


def build():
    g = StateGraph(State)
    g.add_node("assess", assess)
    g.add_node("gate", gate)
    g.add_edge(START, "assess")
    g.add_edge("assess", "gate")
    g.add_edge("gate", END)
    return g.compile(checkpointer=InMemorySaver())


def main(path="-") -> int:
    graph = build()
    config = {"configurable": {"thread_id": "ticket-41"}}

    rec = Recorder(
        agent={"id": "support-agent", "kind": "agent"},
        # Risk comes from here, not from the model. An action missing from this
        # table raises rather than defaulting.
        risk={"issue_refund": "high", "send_receipt": "low"},
        risk_source="registry",
    )

    ev = rec.cite("api", "billing://orders/8812",
                  digest="sha256:" + "0" * 64)
    rec.believe("customer:acme", "eligible_for_refund", evidence=[ev])

    rec.invoke(graph, {"ticket": 41}, config)

    # The identity comes from the caller's authentication layer. LangGraph
    # cannot supply it, this adapter will not invent it, and that is the whole
    # difference between this record and the one the same graph produces
    # without it.
    rec.approve(graph, config,
                approver={"id": "troy@example.com", "kind": "human",
                          "name": "T. Clifford", "role": "owner"},
                identity_source="auth-session")

    rec.write(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "-"))
