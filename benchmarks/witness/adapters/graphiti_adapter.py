"""Graphiti (Zep's open-source engine) on the stand, through add_episode.

Graphiti ingests episodes of text, extracts a temporal knowledge graph with
an LLM, and invalidates edges when new information contradicts them. Events
are therefore fed as episode text, corrections included: edge invalidation on
contradiction is the system's own answer to retraction and supersession, and
that is what gets measured.

Needs a running Neo4j and an LLM key; refuses to construct without both.
`state`, `conflicts`, and `rules` are outside its query surface here, so
probes needing them report UNSUPPORTED.
"""
import os

from . import Adapter, AdapterUnavailable


class GraphitiAdapter(Adapter):
    name = "graphiti"
    capabilities = frozenset({"holdings", "history"})

    def __init__(self):
        if not os.environ.get("OPENAI_API_KEY"):
            raise AdapterUnavailable("graphiti's extraction needs OPENAI_API_KEY")
        if not os.environ.get("NEO4J_URI"):
            raise AdapterUnavailable(
                "set NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD to a running Neo4j")
        try:
            from graphiti_core import Graphiti
        except ImportError:
            raise AdapterUnavailable("pip install graphiti-core")
        import asyncio
        self._run = asyncio.get_event_loop().run_until_complete
        self.g = Graphiti(os.environ["NEO4J_URI"],
                          os.environ.get("NEO4J_USER", "neo4j"),
                          os.environ.get("NEO4J_PASSWORD", ""))
        self._run(self.g.build_indices_and_constraints())
        self._n = 0

    def _add(self, event):
        from datetime import datetime, timezone
        from graphiti_core.nodes import EpisodeType
        self._n += 1
        self._run(self.g.add_episode(
            name="event-%s" % event["id"], episode_body=event["text"],
            source=EpisodeType.text, source_description="witness benchmark",
            reference_time=datetime.now(timezone.utc)))

    tell = retract = update = rule = _add

    def _search(self, about, num=25):
        q = about if isinstance(about, str) else " ".join(about)
        results = self._run(self.g.search(q.replace("person:", "").replace(
            "company:", "").replace("_", " "), num_results=num))
        return [{"text": getattr(r, "fact", str(r)), "sources": []}
                for r in results]

    def holdings(self, about):
        # Graphiti marks superseded edges invalid rather than deleting them;
        # search returns current facts, which is its notion of holdings.
        return self._search(about)

    def history(self, about):
        return self._search(about)
