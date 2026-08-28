"""OMEM Python SDK. Ergonomic wrapper over the HTTP API.

Every method maps 1:1 onto existing OMEM operations/queries. No new semantics.

    from omem import Memory
    mem = Memory(api_key="omem_sk_...", base_url="http://127.0.0.1:8787")
    mem.remember(agent="support", about="customer:123",
                 claim="prefers_annual_billing", because=["ticket:8842"])
    mem.believes(about="customer:123", claim="prefers_annual_billing")  # -> "BELIEVED_TRUE"
    mem.why("a_...")            # provenance chain
    mem.conflicts()            # current contradictions, with evidence
    mem.contradict("prefers_annual_billing", "prefers_monthly_billing")
    mem.timeline()             # events, in order

Two claims conflict only when they are declared opposed. `X` and `not:X` are
paired automatically; contradict() covers everything else. OMEM does not infer
opposition from wording, which is what lets a belief state be reproduced without
a model in the loop.

Agent-bound keys. A key minted with an `agent_id` carries its own identity, so
you omit `agent=` and the binding fills it in:

    POST /v1/keys {"name": "support key", "agent_id": "agent:support-bot"}

A bound key cannot act as a different agent. That holds for writes as well as
reads: naming another agent in remember() is a 403, not a silently accepted
claim with somebody else's name on it. Attribution is the thing why() reports,
so a forgeable one would make the provenance chain worth nothing.

An UNBOUND key keeps the older behaviour and may name any agent freely, which is
what a single trusted process writing for several agents needs.
"""
# `project: str | None` in the Memory signature below is PEP 604, which is a
# TypeError on the Python 3.9 this package claims to support. Deferring
# annotations makes them lazy strings that are never evaluated, so the union
# syntax stays readable and 3.9 stays supported. Removing this line puts the
# package back to crashing on import for every 3.9 user.
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error

__version__ = "0.2.10"


class OmemError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.reason_code = (body.get("error") or {}).get("reason_code")
        super().__init__((body.get("error") or {}).get("message") or str(body))


class Memory:
    def __init__(self, api_key: str, base_url: str = "http://127.0.0.1:8787",
                 project: str | None = None, max_retries: int = 2):
        self.api_key = api_key
        self.base = base_url.rstrip("/")
        self.project = project
        self.max_retries = max_retries

    # -- transport with retry on 5xx/network --
    def _req(self, method, path, body=None):
        url = f"{self.base}{path}"
        if self.project and "project=" not in path:
            url += ("&" if "?" in url else "?") + f"project={self.project}"
        data = json.dumps(body).encode() if body is not None else None
        last = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                payload = json.loads(e.read() or b"{}")
                if e.code >= 500 and attempt < self.max_retries:
                    time.sleep(0.2 * (attempt + 1)); continue
                raise OmemError(e.code, payload)
            except urllib.error.URLError as e:
                last = e
                if attempt < self.max_retries:
                    time.sleep(0.2 * (attempt + 1)); continue
                raise OmemError(0, {"error": {"message": str(last)}})

    # -- ergonomic verbs (map to primitives/queries) --
    def ensure_agent(self, agent, kind="system", label=None):
        """Idempotently register an agent so it can make assertions. The engine
        rejects assertions from unknown agents (R_NO_AGENT) as an integrity
        guarantee; this SDK smooths that over so an integrator's first
        remember()/observe() call just works. Safe to call repeatedly."""
        try:
            return self._req("POST", "/v1/agents", {"id": agent, "kind": kind, "label": label})
        except OmemError as e:
            # Already registered / benign conflict -> treat as success. Anything
            # else is a real error worth surfacing.
            if e.status in (200, 201, 409):
                return {}
            raise

    def ensure_entity(self, entity, type="thing", label=None):
        """Idempotently register a subject entity. The engine rejects assertions
        about unknown subjects (R_DANGLING); this ensures the subject exists so a
        first remember() about a new entity just works. Safe to call repeatedly."""
        try:
            return self._req("POST", "/v1/entities", {"id": entity, "type": type, "label": label})
        except OmemError as e:
            if e.status in (200, 201, 409):
                return {}
            raise

    def remember(self, agent, about, claim, because=None, confidence=None, label=None,
                 auto_create=True, scope=None):
        """Create a grounded belief.

        auto_create (default True): ensure the agent and subject entities exist
        first, auto-registering them if needed, so a first-time remember() about a
        new agent/entity works out of the box. Set auto_create=False for strict
        behavior, the engine then rejects unknown agents/subjects with
        R_NO_AGENT / R_DANGLING (useful to catch typos or enforce an explicit
        entity lifecycle).

        scope (default None => org): cross-agent visibility. None/"org" makes the
        fact organisational (every agent in the project can recall it).
        "agent:<id>" keeps it private to one agent, "team:<id>" shares it with a
        team, "user:<id>" scopes it to an end-user. Sharing later is also possible
        via share().

        because: OPTIONAL list of *recorded* antecedent ids this belief derives
        from (not free text, use `label` for a human note). Unknown antecedents
        are rejected (R_DANGLING) regardless of auto_create."""
        subjects = [about] if isinstance(about, str) else list(about)
        if auto_create:
            self.ensure_agent(agent)
            for s in subjects:
                self.ensure_entity(s)
        body = {"agent": agent, "subjects": subjects, "proposition": claim,
                "assertion_time": "now", "because": list(because or []),
                "confidence": confidence, "label": label}
        if scope is not None:
            body["scope"] = scope
        return self._req("POST", "/v1/assertions", body)

    def believes(self, about, claim) -> str:
        subjects = [about] if isinstance(about, str) else list(about)
        r = self._req("POST", "/v1/queries/proposition-state",
                      {"subjects": subjects, "proposition": claim})
        return r["state"]

    def about(self, entity, page=None, page_size=50):
        """All open beliefs whose subject includes this entity (paginated)."""
        r = self._req("GET", "/v1/assertions")
        items = [a for a in r.get("data", []) if entity in a.get("subjects", [])]
        if page is not None:
            start = page * page_size
            return items[start:start + page_size]
        return items

    def why(self, assertion_id):
        return self._req("GET", f"/v1/assertions/{assertion_id}/why")

    # -- managed agent DX: ingestion proposes, the engine decides --
    def observe(self, agent, interaction, source=None, scope=None):
        """Feed a raw interaction; OMEM decides what becomes memory.
        interaction: {"text": ..., "speaker": ..., "audience": ..., "topic": ..., "thread_id": ...}
        (only "text" is required). Returns the memories formed, each with
        evidence, engine state, and any superseded prior beliefs."""
        if isinstance(interaction, str):
            interaction = {"text": interaction}
        return self._req("POST", "/v1/observe",
                         {"agent": agent, "interaction": interaction,
                          "source": source, "scope": scope})

    def learn(self, agent, text, about=None, source=None):
        """Turn free text into candidate facts via the ingestion extractor,
        record valid primitives, and return the engine-determined states."""
        return self._req("POST", "/v1/learn",
                         {"agent": agent, "text": text, "about": about, "source": source})

    def recall(self, about=None, *, agent=None, context=None, task=None,
               user=None, entities=None, as_of=None, limit=10, max_chars=None):
        """Two forms.
        recall(about="customer:123") -> legacy entity lookup (scope-filtered
        when agent= is passed).
        recall(agent=..., context=..., task=...) -> intelligent recall: OMEM
        extracts the entities, retrieves candidates, applies scope rules and
        engine belief state, and returns a compact MemoryPack (memories with
        status/why/provenance, excluded-with-reasons, real latencies)."""
        if context is not None or task is not None or entities is not None:
            return self._req("POST", "/v1/recall", {
                "agent": agent, "context": context, "task": task, "user": user,
                "about": about, "entities": entities, "as_of": as_of,
                "limit": limit, "max_chars": max_chars})
        return self._req("POST", "/v1/recall", {"about": about, "agent": agent,
                                                "user": user})

    def brief(self, *, agent=None, context=None, task=None, about=None,
              user=None, entities=None, as_of=None, limit=12, max_chars=None):
        """The situation brief: "what do I need to know about this?" Returns
        current_facts / relationships / conflicts / patterns sections, each
        item priority-ranked and fully explained, bounded and deterministic.
        Composes recall + graph + conflict reasoning; the engine decides all
        belief state."""
        return self._req("POST", "/v1/brief", {
            "agent": agent, "context": context, "task": task, "about": about,
            "user": user, "entities": entities, "as_of": as_of,
            "limit": limit, "max_chars": max_chars})

    def graph(self, entity, depth=1, viewer=None):
        """The memory graph around an entity: nodes + directed relationship
        edges, each edge backed by an open engine assertion. Scope-safe:
        edges the viewer may not see do not exist in the response."""
        q = f"&depth={depth}" + (f"&viewer={viewer}" if viewer else "")
        return self._req("GET", f"/v1/memory/graph?entity={entity}{q}")

    def conflicts(self, viewer=None):
        """Open contradictions with each side's real evidence (observations,
        agents, authority, recency) and a deterministic recommendation, or
        'unresolved' when evidence is tied. The engine's truth state is never
        altered by this analysis.

        Two claims conflict only if they are declared mutually exclusive. Claims
        named `X` and `not:X` are declared automatically; anything else needs
        contradict(). If this list is empty when you expected a conflict, check
        contradictions() first."""
        q = f"?viewer={viewer}" if viewer else ""
        return self._req("GET", f"/v1/memory/conflicts{q}")

    def contradict(self, claim_a, claim_b):
        """Declare two claims mutually exclusive, so asserting both about the
        same subject is a contradiction rather than two unrelated facts.

            mem.contradict("prefers_annual_billing", "prefers_monthly_billing")

        OMEM never infers this from wording. Deciding that two sentences
        disagree is exactly the judgment call that makes a memory
        irreproducible, so the vocabulary of what can conflict is yours and the
        engine only applies it. The cost is this one line per opposed pair; the
        return is that a belief state is the same answer today and in a year,
        with no model involved in reaching it.

        You do not need it for simple negation: `X` and `not:X` are paired for
        you the first time either is stored."""
        return self._req("POST", "/v1/contradictions",
                         {"token_a": claim_a, "token_b": claim_b})

    def contradictions(self):
        """The declared mutually-exclusive pairs for this project."""
        return self._req("GET", "/v1/contradictions")

    def share(self, assertion_id, scope, granted_by=None):
        """Explicitly promote a memory's visibility (org, team:<id>,
        agent:<id>, user:<id>). Attribution and provenance never change."""
        return self._req("POST", "/v1/memory/share",
                         {"assertion_id": assertion_id, "scope": scope,
                          "granted_by": granted_by})

    def set_team(self, team_id, agents):
        return self._req("POST", "/v1/teams", {"team_id": team_id, "agents": agents})

    def _recall_legacy(self, about):
        """Return real memories about a subject. State comes from the engine."""
        return self._req("POST", "/v1/recall", {"about": about})

    def agent(self, agent_id):
        return Agent(self, agent_id)

    def conflict_pairs(self):
        """The bare contradicting assertion-id pairs, straight from the engine.

        Renamed from a second `conflicts` defined here, which silently shadowed
        the documented one above: Python keeps the last definition, so every
        caller got these bare pairs and the evidence-and-recommendation analysis
        was unreachable from this SDK entirely. Two methods, two names, both
        available."""
        return self._req("GET", "/v1/conflicts").get("conflicts", [])

    def timeline(self):
        return self._req("GET", "/v1/timeline").get("events", [])

    # -- automatic memory: connect a source instead of remembering manually --
    def connect_gmail(self, name="Gmail", authority=0.8):
        return self._req("POST", "/v1/oauth/gmail/begin", {"name": name, "authority": authority})

    def sources(self):
        return self._req("GET", "/v1/connectors").get("data", [])

    def health(self):
        return self._req("GET", "/v1/intelligence").get("memory_health", {})

    # -- self-healing subsystem: OMEM provides the infra, the agent (or an LLM)
    #    provides reasoning. See Healing below. --
    @property
    def healing(self):
        return Healing(self)


class Healing:
    """Self-healing surface. The developer does not write a self-healing framework;
    they report failures (or submit a plan) and OMEM handles memory, policy,
    execution, verification, and history. High-risk actions still require explicit
    approval and permission. OMEM decides, not the caller."""

    def __init__(self, memory):
        self.m = memory

    def report(self, component, error_type, message="", severity="error", context=None):
        """Record a failure; get back the failure record + prior-memory summary."""
        return self.m._req("POST", "/v1/healing/failures", {
            "component": component, "error_type": error_type, "message": message,
            "severity": severity, "context": context or {}})

    def handle(self, error, plan=None, approved_by=None):
        """Run the autonomous recovery loop for a failure. `error` is
        {component, error_type, message?, context?}. Optionally submit a `plan`
        (e.g. produced by an LLM). OMEM still runs it through policy + verify.
        Returns a structured result (recovered/failed/denied/throttled/escalated)."""
        body = {"error": error}
        if plan is not None:
            body["plan"] = plan
        if approved_by is not None:
            body["approved_by"] = approved_by
        return self.m._req("POST", "/v1/healing/handle", body)

    def failures(self, component=None):
        path = "/v1/healing/failures" + (f"?component={component}" if component else "")
        return self.m._req("GET", path).get("data", [])

    def failure(self, failure_id):
        return self.m._req("GET", f"/v1/healing/failures/{failure_id}")

    def health(self):
        """Aggregated component health for the project."""
        return self.m._req("GET", "/v1/healing/health")

    def report_health(self, component, status, reason="", metadata=None):
        return self.m._req("POST", "/v1/healing/health", {
            "component": component, "status": status, "reason": reason, "metadata": metadata or {}})

    def snapshot(self, label, kind="state", payload=None):
        return self.m._req("POST", "/v1/healing/snapshots", {
            "label": label, "kind": kind, "payload": payload or {}})


class Agent:
    """Agent-scoped convenience wrapper. Pure sugar over Memory; no new semantics."""
    def __init__(self, memory, agent_id):
        self._m = memory
        self.id = agent_id

    def observe(self, interaction, source=None, scope=None):
        return self.memory.observe(self.agent_id, interaction, source=source, scope=scope)

    def learn(self, text, about=None, source=None):
        return self._m.learn(self.id, text, about=about, source=source)

    def recall(self, about):
        return self._m.recall(about)

    def brief(self, *, context=None, task=None, about=None, user=None,
              entities=None, as_of=None, limit=12, max_chars=None):
        return self._m.brief(agent=self.id, context=context, task=task,
                             about=about, user=user, entities=entities,
                             as_of=as_of, limit=limit, max_chars=max_chars)

    def remember(self, about, claim, because=None, confidence=None, label=None):
        return self._m.remember(self.id, about, claim, because, confidence, label)

    def believes(self, about, claim):
        return self._m.believes(about, claim)

    def why(self, assertion_id):
        return self._m.why(assertion_id)


from .runtime import (wrap, WrappedAgent, RuntimeAdapter, GenericAdapter,  # noqa: E402
                      MessagesAdapter, RuntimeResult, OmemRuntimeError,
                      render_envelope)
