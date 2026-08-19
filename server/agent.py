"""A complete example agent showing the product loop.

Before responding, the agent QUERIES OMEM for what it already believes about the
customer (and the source behind that belief). After the conversation, new
information re-enters the ingestion pipeline as a source record, so a future
agent turn has it in context. The agent never writes engine state directly; it
goes through the same connector/ingestion path as any other source.
"""
from __future__ import annotations
import json
import time


class SupportAgent:
    def __init__(self, project, ingestor):
        self.p = project
        self.ingestor = ingestor
        self._conv_connector = None

    # -- READ: query memory before deciding --
    def handle(self, customer_local: str, message: str) -> dict:
        eid = f"customer:{customer_local}"
        T = self.p.now()
        recalled = []
        source = None
        for a in self.p.engine.store.assertions():
            if eid in a.subjects:
                state = self.p.engine.proposition_state(list(a.subjects), a.proposition, T)
                if state == "BELIEVED_TRUE":
                    recalled.append(a.proposition)
                    if source is None:
                        src = self.ingestor.source_for_assertion(self.p.id, a.id)
                        if src:
                            source = json.loads(src["payload"]).get("subject") or src["external_id"]
        memory_used = ", ".join(recalled) if recalled else "no prior memory"
        # a real agent would feed memory_used into its LLM prompt; here we just
        # surface the decision inputs so the loop is inspectable.
        answer = self._compose(customer_local, message, recalled)
        return {"answer": answer, "memory_used": memory_used, "source": source,
                "recalled": recalled}

    def _compose(self, customer, message, recalled):
        if "billing" in message.lower() and "prefers_annual_billing" in recalled:
            return (f"Happy to help with billing. I can see {customer} is on annual "
                    f"billing already, so I'll adjust the annual plan rather than switch cadence.")
        if recalled:
            return f"Before we continue, I have context on file: {', '.join(recalled)}."
        return "I don't have prior context yet; could you tell me a bit more?"

    # -- WRITE: conversation re-enters the pipeline as a source --
    def learn(self, customer_local: str, utterance: str):
        """The customer said something new. Turn the utterance into a source
        record via a conversation connector so it flows through extraction ->
        engine like any other source (full provenance, dedup, contradiction)."""
        if self._conv_connector is None:
            self._conv_connector = self.ingestor.add_connector(
                self.p.id, "support_inbox", "Conversation capture",
                {"items": []}, agent_id="connector:conversation", authority=0.6)
        # append the utterance as a new inbox item and poll just it
        conn = self.ingestor.connector(self._conv_connector["id"])
        cfg = json.loads(conn["config"])
        cfg["items"].append({"customer": customer_local, "subject": "conversation",
                             "body": utterance, "at": "now"})
        self.ingestor.db.execute("UPDATE connectors SET config=? WHERE id=?",
                                 (json.dumps(cfg), conn["id"]))
        self.ingestor.db.commit()
        self.ingestor.poll_connector(conn["id"])
