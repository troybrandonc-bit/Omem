"""Mem0 (OSS) on the stand, through its own add/search/get_all path.

Mem0's design: raw text goes in, an LLM extracts what to remember, updates
reconcile against what exists. That pipeline IS the system, so events are fed
as the natural-language `text` of each event through add(), corrections
included, and holdings come back from get_all + search. Nothing is spoon-fed
in structured form: a structured side-channel would measure the benchmark's
own parsing, not Mem0.

Consequences, stated up front rather than discovered in the numbers:

  * needs a configured LLM (OPENAI_API_KEY by default), so this adapter
    refuses to construct without one instead of producing empty non-results.
  * entity scoping is by user_id, and both people in the shared_name scenario
    arrive as text about "Sarah Chen"; Mem0 has no entity ids to keep them
    apart, so identity probes run against name-keyed retrieval and measure
    exactly that.
  * `state`, `conflicts`, and `rules` are not in its design: probes needing
    them report UNSUPPORTED.
"""
import os

from . import Adapter, AdapterUnavailable

UID = "witness"


class Mem0Adapter(Adapter):
    name = "mem0"
    capabilities = frozenset({"holdings", "history", "provenance"})

    def __init__(self):
        if not os.environ.get("OPENAI_API_KEY"):
            raise AdapterUnavailable(
                "mem0's default pipeline needs OPENAI_API_KEY; refusing to "
                "run it degraded and call the numbers Mem0's")
        try:
            from mem0 import Memory
        except ImportError:
            raise AdapterUnavailable("pip install mem0ai")
        self.m = Memory()
        self.m.delete_all(user_id=UID)

    def _add(self, event):
        self.m.add(event["text"], user_id=UID,
                   metadata={"event_id": event["id"]})

    # Every event kind goes through the same door, because that is the only
    # door the system has: corrections and rules are sentences to it.
    tell = retract = update = rule = _add

    def _all(self):
        got = self.m.get_all(user_id=UID)
        rows = got.get("results", got) if isinstance(got, dict) else got
        out = []
        for r in rows:
            meta = r.get("metadata") or {}
            src = [meta["event_id"]] if meta.get("event_id") else []
            out.append({"text": r.get("memory", ""), "sources": src})
        return out

    def holdings(self, about):
        return self._all()

    def history(self, about):
        return self._all()
