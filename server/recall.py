"""Intelligent recall + memory scopes. Everything here sits ABOVE the frozen
engine: retrieval FINDS candidates, the decision layer RANKS them with
explainable signals, and the engine remains the sole authority on belief state
(every status in a pack comes from engine queries at the requested time).

    OBSERVE -> MEMORY FORMATION -> RECALL -> MEMORY PACK -> AGENT

Scopes
------
A memory belongs to exactly one scope row (memory_scopes):
    org            organisational knowledge (every agent in the project)
    team:<id>      a named team (membership in team_members)
    agent:<id>     private to one agent
    user:<id>      tied to one end-user; visible when the caller is acting
                   for that user (recall(..., user="customer:123"))
No scope row = "org": connector-ingested knowledge (the company's own mailbox)
and everything created before scopes existed is organisational by design.
observe() writes agent-private rows BY DEFAULT; sharing is an explicit
promotion that changes visibility only, attribution (which agent learned it,
from where, when) is engine-side and immutable.

Determinism
-----------
Given identical inputs and identical memory state, a pack is byte-identical:
every ranking signal is deterministic and ties break on assertion id. No LLM
participates in recall; a model may (later) help interpret context, but it can
never decide belief state or scope.
"""
from __future__ import annotations
import re
import time

SCOPES_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_scopes(
  project_id TEXT NOT NULL, assertion_id TEXT NOT NULL, scope TEXT NOT NULL,
  granted_by TEXT, created REAL NOT NULL,
  PRIMARY KEY(project_id, assertion_id));
CREATE INDEX IF NOT EXISTS scopes_scope ON memory_scopes(project_id, scope);
CREATE TABLE IF NOT EXISTS team_members(
  project_id TEXT NOT NULL, team_id TEXT NOT NULL, agent_id TEXT NOT NULL,
  PRIMARY KEY(project_id, team_id, agent_id));
"""

_SCOPE_RE = re.compile(r"^(org|team:[a-z0-9_.@-]{1,64}|agent:[a-z0-9_.@:-]{1,80}"
                       r"|user:[a-z0-9_.@:-]{1,80})$")


def valid_scope(s: str) -> bool:
    return bool(s and _SCOPE_RE.match(s))


class ScopeStore:
    def __init__(self, db):
        self.db = db
        self.db.executescript(SCOPES_SCHEMA)
        self.db.commit()

    def set(self, project_id: str, assertion_id: str, scope: str,
            granted_by: str | None = None):
        if not valid_scope(scope):
            raise ValueError(f"invalid scope {scope!r}")
        self.db.execute(
            "INSERT OR REPLACE INTO memory_scopes VALUES(?,?,?,?,?)",
            (project_id, assertion_id, scope, granted_by, time.time()))
        self.db.commit()

    def of(self, project_id: str, assertion_id: str) -> str:
        r = self.db.execute(
            "SELECT scope FROM memory_scopes WHERE project_id=? AND assertion_id=?",
            (project_id, assertion_id)).fetchone()
        return r["scope"] if r else "org"

    def bulk(self, project_id: str) -> dict[str, str]:
        return {r["assertion_id"]: r["scope"] for r in self.db.execute(
            "SELECT assertion_id, scope FROM memory_scopes WHERE project_id=?",
            (project_id,))}

    def teams_of(self, project_id: str, agent_id: str) -> set[str]:
        return {r["team_id"] for r in self.db.execute(
            "SELECT team_id FROM team_members WHERE project_id=? AND agent_id=?",
            (project_id, agent_id))}

    def set_team(self, project_id: str, team_id: str, agents: list[str]):
        self.db.execute("DELETE FROM team_members WHERE project_id=? AND team_id=?",
                        (project_id, team_id))
        for a in agents:
            self.db.execute("INSERT OR REPLACE INTO team_members VALUES(?,?,?)",
                            (project_id, team_id, a))
        self.db.commit()

    def visible(self, scope: str, viewer_agent: str | None,
                viewer_teams: set[str], acting_user: str | None) -> bool:
        """The single visibility rule, used by EVERY read path. Conservative:
        an unknown scope form is invisible."""
        if scope == "org":
            return True
        if scope.startswith("agent:"):
            # Both spellings, because two of them are in the wild.
            #
            # This used to be `scope == f"agent:{viewer_agent}"`. A viewer is
            # resolved as "agent:bob", so that built "agent:agent:bob" and only
            # matched a scope that had been written the same doubled way. The
            # observe path DID write it doubled (`f"agent:{agent}"` over an
            # already-prefixed agent), so private-by-default worked and nobody
            # noticed.
            #
            # What did not work was the documented form. POST /v1/memory/share
            # and `scope` on POST /v1/assertions both store exactly what the
            # caller sends, and the validator tells callers to send
            # "agent:<id>". That produced a memory no one could read, including
            # the agent it was scoped to: a write-only hole with no error.
            #
            # It failed CLOSED, so nothing leaked. It just meant the feature
            # silently did not work through the public API.
            if viewer_agent is None:
                return False
            bare = viewer_agent[6:] if viewer_agent.startswith("agent:") else viewer_agent
            return scope == f"agent:{bare}" or scope == f"agent:agent:{bare}"
        if scope.startswith("team:"):
            return scope.split(":", 1)[1] in viewer_teams
        if scope.startswith("user:"):
            return acting_user is not None and scope == f"user:{acting_user}"
        return False


    def explain_visibility(self, scope: str, viewer_agent, viewer_teams,
                           acting_user) -> dict:
        """Why this caller may or may not read a memory with this scope.

        `why` has always answered where a belief came from and never why the
        caller was allowed to retrieve it. Both were computed; only one was
        returned. For a system whose argument is that every access can be
        reviewed, "who was permitted, and under which rule" belongs in the same
        place as provenance.

        The verdict comes from visible() rather than being recomputed here. An
        explanation that derives its own answer can disagree with the rule it
        claims to describe, and then there are two behaviours and no way to
        know from the outside which one actually ran. This function only
        supplies the sentence.
        """
        verdict = self.visible(scope, viewer_agent, viewer_teams, acting_user)
        if scope == "org":
            rule = "organisation scope: readable by every agent in the project"
        elif scope.startswith("agent:"):
            rule = ("agent scope: the viewer is the agent it belongs to"
                    if verdict else
                    "agent scope: private to another agent" if viewer_agent
                    else "agent scope: no viewer identity was resolved, so nothing agent-scoped is readable")
        elif scope.startswith("team:"):
            rule = ("team scope: the viewer is a member of that team" if verdict
                    else "team scope: the viewer is not a member of that team")
        elif scope.startswith("user:"):
            rule = ("user scope: the acting user matches" if verdict else
                    "user scope: acting for a different user" if acting_user
                    else "user scope: no acting user was supplied, so nothing user-scoped is readable")
        else:
            rule = "unrecognised scope form, treated as invisible"
        return {"scope": scope, "viewer": viewer_agent,
                "acting_user": acting_user,
                "viewer_teams": sorted(viewer_teams or []),
                "visible": verdict, "rule": rule}


# ── context understanding (deterministic; no model required) ────────────────
_WORD = re.compile(r"[a-z0-9][a-z0-9_@.-]{2,}")


def extract_context_entities(text: str, p, explicit: list[str] | None = None) -> list[str]:
    """Which known entities does this context concern? Deterministic: explicit
    ids first, then known entity ids/labels/email-locals found in the text.
    OMEM's job, the developer never pre-extracts ids."""
    found: list[str] = []
    seen = set()

    def add(eid):
        if eid and eid not in seen:
            seen.add(eid)
            found.append(eid)

    for e in (explicit or []):
        add(e)
    low = (text or "").lower()
    if not low:
        return found
    for eid, meta in sorted(p.labels.items()):
        if ":" not in eid:
            continue
        kind, local = eid.split(":", 1)
        if kind in ("agent",):
            continue
        if eid in low:
            add(eid)
            continue
        label = meta.get("label") if isinstance(meta, dict) else meta
        name = (label or "").lower() if isinstance(label, str) else ""
        if name and len(name) >= 3 and name in low:
            add(eid)
            continue
        if len(local) >= 3 and re.search(r"\b" + re.escape(local.replace("_", " ").replace("-", " ")) + r"\b",
                                          low.replace("_", " ").replace("-", " ")):
            add(eid)
    return found[:12]


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


# ── candidate retrieval: FINDS, never decides ───────────────────────────────
class CandidateRetriever:
    """Multiple bounded sources; each tags why it surfaced a candidate. New
    strategies (indexed / vector) plug in here without touching the decision
    layer."""

    MAX_CANDIDATES = 200

    def __init__(self, p, db=None):
        self.p = p
        self.db = db  # when present, use the P7 index instead of scanning

    def retrieve(self, entities: list[str], context_tokens: set[str]) -> dict[str, list[str]]:
        """assertion_id -> [source tags]. Deterministic; identical results
        whether served from the index or the scan (proven by equivalence
        tests). The index only NARROWS candidates; the decision stage still
        re-validates every id against the engine."""
        if self.db is not None:
            try:
                return self._retrieve_indexed(entities, context_tokens)
            except Exception:
                pass  # any index issue: fall back to the authoritative scan
        return self._retrieve_scan(entities, context_tokens)

    def _order(self, ids):
        """Newest-first by (−assertion_time, id), matching the scan's sort."""
        out = []
        for aid in ids:
            a = self.p.engine.store.assertion(aid)
            if a is not None:
                out.append(a)
        out.sort(key=lambda a: (-a.assertion_time, a.id))
        return out

    def _retrieve_indexed(self, entities, context_tokens):
        import candidate_index as _ci
        ents = set(entities)
        cap = self.MAX_CANDIDATES
        # union the two indexed sources, then apply the SAME tagging rules the
        # scan used, in the SAME newest-first order.
        ent_ids = _ci.candidates_by_entities(self.db, self.p.id, list(ents), cap)
        tok_ids = _ci.candidates_by_tokens(self.db, self.p.id, list(context_tokens), cap) \
            if context_tokens else []
        merged = self._order(list(dict.fromkeys(ent_ids + tok_ids)))
        out: dict[str, list[str]] = {}
        for a in merged:
            if len(out) >= cap:
                break
            tags = []
            if ents & set(a.subjects):
                tags.append("entity")
            else:
                prop_toks = set((a.proposition or "").replace("_", " ").split())
                if context_tokens and len(prop_toks & context_tokens) >= 1:
                    tags.append("lexical")
            if tags:
                out[a.id] = tags
        if not out:
            for a in self._order(_ci.newest(self.db, self.p.id, 10)):
                out[a.id] = ["recent"]
        return out

    def _retrieve_scan(self, entities, context_tokens):
        out: dict[str, list[str]] = {}
        ents = set(entities)
        assertions = sorted(self.p.engine.store.assertions(),
                            key=lambda a: (-a.assertion_time, a.id))
        for a in assertions:
            if len(out) >= self.MAX_CANDIDATES:
                break
            tags = []
            if ents & set(a.subjects):
                tags.append("entity")
            prop_toks = set((a.proposition or "").replace("_", " ").split())
            if context_tokens and len(prop_toks & context_tokens) >= 1 and "entity" not in tags:
                tags.append("lexical")
            if tags:
                out[a.id] = tags
        # recency source: only when nothing else matched anything (cold start),
        # a small window of the newest memories - never a database dump
        if not out:
            for a in assertions[:10]:
                out[a.id] = ["recent"]
        return out


# How far recall follows relations. The graph has supported two hops since it
# was written (MAX_DEPTH), the traversal endpoint honoured it, and recall asked
# for one -- so "Sarah works at Acme, Acme supplies Globex" never reached
# Globex from Sarah. Two hops is where a memory graph starts being worth
# having; it is also where precision starts to cost something, which is why
# nearer entities outrank further ones in _tier() below and every included
# memory states the path it was reached by.
RECALL_DEPTH = 2


def _render_path(path: list) -> str:
    """The whole chain, in the order it was walked, e.g.

        person:sarah works_at→ company:acme then company:acme supplies→ company:globex

    Two things this gets right that the previous single-edge rendering did not.

    It reads from what the caller ASKED about, outward. Traversal is
    undirected, so a chain can walk against an edge; rendering edges in their
    stored direction produced a path that began at a node nobody mentioned and
    ran backwards.

    The arrow still points along the edge as it was ASSERTED, so walking
    against one renders "company:acme ←works_at person:sarah" rather than
    silently reversing the claim. Reading order follows the walk; the arrow
    keeps telling the truth about the relation.
    """
    if not path:
        return ""
    parts = []
    for e in path:
        frm, to = e.get("from", e["src"]), e.get("to", e["dst"])
        parts.append(f"{frm} {e['relation']}→ {to}" if frm == e["src"]
                     else f"{frm} ←{e['relation']} {to}")
    return " then ".join(parts)


# ── decision layer: explainable, deterministic ──────────────────────────────
def build_memory_pack(p, db, scope_store: ScopeStore, *,
                      agent: str | None, context: str = "", task: str = "",
                      user: str | None = None, entities: list[str] | None = None,
                      as_of=None, limit: int = 10, max_chars: int | None = None,
                      source_lookup=None, extras_lookup=None,
                      conflict_analyzer=None) -> dict:
    t0 = time.perf_counter()
    T = as_of if as_of is not None else p.now()
    ctx_text = f"{context}\n{task}"
    ents = extract_context_entities(ctx_text, p, explicit=([user] if user else []) + (entities or []))
    toks = _tokens(ctx_text)

    related: list[str] = []
    rel_paths: dict[str, str] = {}
    rel_hops: dict[str, int] = {}
    if ents:
        try:
            import graph as _g
            hops = _g.neighbors(db, p, ents, depth=RECALL_DEPTH, T=T,
                                scopes=scope_store, viewer=agent,
                                teams=scope_store.teams_of(p.id, agent) if agent else set(),
                                user=user)
            for e, info in sorted(hops.items()):
                related.append(e)
                rel_hops[e] = info.get("hops", 1)
                rel_paths[e] = _render_path(info.get("path") or [info["via"]])
        except Exception:
            related = []
            rel_hops = {}
    t1 = time.perf_counter()
    candidates = CandidateRetriever(p, db=db).retrieve(ents + related, toks)
    # Semantic candidate source (opt-in via OMEM_SEMANTIC_RECALL, default on):
    # surfaces memories whose MEANING matches the context even without shared
    # tokens/entities. These are merged as additional candidates tagged
    # "semantic"; they go through the identical scope-filter, engine validation,
    # and deterministic ranking below - this only WIDENS the candidate set, it
    # never changes belief state or ranking authority. Bounded and fail-open.
    import os as _os
    if _os.environ.get("OMEM_SEMANTIC_RECALL", "1") == "1" and ctx_text.strip():
        try:
            import semantic_recall as _sr
            sem = _sr.SemanticRetriever(p).retrieve(ctx_text, exclude=set(candidates.keys()))
            for aid, sim in sem.items():
                candidates.setdefault(aid, []).append("semantic")
        except Exception:
            pass  # semantic retrieval is additive; never break base recall
    t2 = time.perf_counter()

    scopes = scope_store.bulk(p.id)
    teams = scope_store.teams_of(p.id, agent) if agent else set()
    included, excluded, seen_props = [], [], set()
    # P8: compute the coreference partition at T ONCE and reuse it for every
    # candidate's proposition_state (the frozen engine otherwise rebuilds it
    # per candidate - the O(n²) bottleneck). Byte-identical to per-call engine
    # queries (tests_p8_partition_equiv.py). Fall back to direct engine calls
    # on any error - the engine stays authoritative.
    try:
        import partition_view as _pv
        _pview = _pv.PartitionView(p.engine, T)
    except Exception:
        _pview = None
    # P7: conflicts only for the candidate assertions we may actually include,
    # not the whole project. conflict_narrow reuses the engine's own predicates
    # (same-referent + declared-contradiction), so the pairs are byte-identical
    # to filtering the full engine.conflicts(T) to these candidates (proven in
    # tests_p7_conflict_equiv.py). Falls back to the full call on any error -
    # the engine stays the sole authority either way.
    try:
        import conflict_narrow as _cnarrow
        conflicts_at_T = list(_cnarrow.conflicts_for(p.engine, list(candidates.keys()), T,
                                                     pview=_pview))
    except Exception:
        conflicts_at_T = list(p.engine.conflicts(T))

    # Learning loop: utility scores from accumulated feedback + recall usage.
    # Feeds the ranker as a soft tie-break WITHIN a tier, so memories that have
    # proven useful drift ahead of equally-tiered ones. Bucketed + id-tiebroken,
    # so ranking stays deterministic and reproducible. Fail-open.
    _utility = {}
    try:
        import os as _os2
        if _os2.environ.get("OMEM_UTILITY_RANKING", "1") == "1":
            import learning as _learn
            _utility = _learn.utility_scores(db, p.id)
    except Exception:
        _utility = {}

    # Effective confidence per candidate: the stated number plus independent
    # corroboration (confidence.py owns the arithmetic), computed once for
    # the whole candidate set. The FIELDS always ship in the pack; the RANK
    # effect sits behind a flag like utility, and both fail open -- a missing
    # score removes nuance, never memories.
    _conf_cache: dict = {}
    try:
        import confidence as _confmod
        _csupport = (_confmod.bulk_support(db, p.id, list(candidates))
                     if db is not None else {})
        for _caid in candidates:
            _ca = p.engine.store.assertion(_caid)
            if _ca is None:
                continue
            _cs, _cr = _confmod.effective(_ca.confidence, _csupport.get(_caid, 0))
            _conf_cache[_caid] = (_cs, _cr, _confmod.bucket(_cs))
    except Exception:
        _conf_cache = {}
    import os as _os3
    _conf_rank = _os3.environ.get("OMEM_CONFIDENCE_RANKING", "1") == "1"

    def _tier(aid, tags):
        a = p.engine.store.assertion(aid)
        if a is None:
            return (9, 0, 0, aid)
        if a.proposition.startswith("pattern_") or \
                any(s.startswith("cohort:") for s in a.subjects):
            t = 2   # generalized knowledge: useful, but specifics come first
        elif extras_lookup and (extras_lookup(aid) or {}).get("mclass") == "relational":
            t = 1
        else:
            t = 0   # specific facts and exceptions outrank the general rule
        # utility bucket orders within a tier (useful memories first), before
        # the entity/recency tie-breaks; ties still ultimately break on id.
        try:
            import learning as _learn2
            u = _learn2.utility_rank_key(_utility.get(aid, 0.0))
        except Exception:
            u = 0
        # Distance from what was actually asked about. A memory whose subject is
        # named in the context is hop 0; one reached through a relation is 1 or
        # 2. Without this every entity-tagged memory ranked the same, so raising
        # traversal to two hops would let a fact about a supplier's supplier
        # displace a fact about the customer in front of you.
        # Only subjects we actually matched count. Defaulting an unmatched
        # subject to 0 would make an assertion about [hop-2 entity, someone
        # unrelated] rank as though it were direct.
        _d = [0 if s in ents else rel_hops[s]
              for s in a.subjects if s in ents or s in rel_hops]
        hop = min(_d) if _d else 0
        # Better-supported memories outrank equally-placed ones, BEFORE
        # recency: a corroborated older fact beats an unsupported newer one.
        # Bucketed (confidence.bucket), so a hundredth of a point cannot
        # reorder anything and the sort stays reproducible.
        cb = _conf_cache.get(aid, (0, None, 0))[2] if _conf_rank else 0
        return (t, u, "entity" not in tags, hop, -cb, -a.assertion_time, aid)

    ordered = sorted(candidates.items(), key=lambda kv: _tier(kv[0], kv[1]))
    for aid, tags in ordered:
        a = p.engine.store.assertion(aid)
        if a is None:
            continue
        scope = scopes.get(aid, "org")
        if not scope_store.visible(scope, agent, teams, user):
            excluded.append({"id": aid, "reason": "outside the caller's scope"})
            continue
        if ents and "entity" not in tags and not (set(a.subjects) & set(ents)):
            # The context names specific entities; a memory about a DIFFERENT
            # entity that merely shares wording is noise for this task.
            excluded.append({"id": aid,
                             "reason": "concerns a different entity than the current context"})
            continue
        if getattr(a, "is_retraction", False) or a.proposition == "__retracted__":
            continue
        state = (_pview.proposition_state(list(a.subjects), a.proposition)
                 if _pview is not None
                 else p.engine.proposition_state(list(a.subjects), a.proposition, T))
        if not p.engine.ledger.is_open_at(a, T):
            excluded.append({"id": aid, "reason": "superseded or retracted, not current belief",
                             "proposition": a.proposition})
            continue
        extras = (extras_lookup(aid) if extras_lookup else None) or {}
        if extras.get("mclass") == "transient" and extras.get("ttl") is not None \
                and (T - a.assertion_time) > extras["ttl"]:
            # DECAY affects retrieval only: the assertion stays open in the
            # engine, history and as_of remain intact.
            excluded.append({"id": aid,
                             "reason": "expired transient context (canonical history preserved)"})
            continue
        dedup_key = (tuple(sorted(a.subjects)), a.proposition)
        if dedup_key in seen_props:
            excluded.append({"id": aid, "reason": "duplicate of an included memory"})
            continue
        seen_props.add(dedup_key)
        prov_ids, grounded = p.engine.provenance(aid)
        conf = []
        for pair in conflicts_at_T:
            if aid in pair:
                other_id = [x for x in pair if x != aid][0]
                oa = p.engine.store.assertion(other_id)
                if oa is not None:
                    conf.append({"assertion": other_id, "proposition": oa.proposition,
                                 "agent": oa.agent})
        why = []
        if a.proposition.startswith("pattern_"):
            why.append("general knowledge from repeated organisational experience, "
                       "specific facts about the entities in context take precedence")
        if "entity" in tags:
            direct = sorted(set(a.subjects) & set(ents))
            if direct:
                why.append(f"directly concerns {', '.join(direct)}")
            else:
                # The NEAREST related subject, not the alphabetically first.
                # With two-hop traversal an assertion can touch entities at
                # different distances, and explaining it by the further one
                # contradicts the ranking that put it here.
                via = sorted(set(a.subjects) & set(related),
                             key=lambda r: (rel_hops.get(r, 9), r))
                for r in via[:1]:
                    why.append(f"reached through the memory graph: {rel_paths.get(r, r)}")
        if "lexical" in tags:
            why.append("relates to the current context wording")
        if "recent" in tags:
            why.append("recent memory (no direct match in context)")
        supported = 1 + int(extras.get("reinforcements") or 0)
        if supported > 1:
            why.append(f"supported by {supported} independent observations")
        conflict_analysis = None
        if conf and conflict_analyzer is not None:
            conflict_analysis = conflict_analyzer((aid, conf[0]["assertion"]))
            if conflict_analysis and conflict_analysis.get("recommendation"):
                rec = conflict_analysis["recommendation"]
                why.append("best-supported side of an open conflict"
                           if rec["assertion"] == aid else
                           "conflicted. A better-supported opposing memory exists")
        kind = ("GENERAL_PATTERN" if a.proposition.startswith("pattern_")
                or any(s.startswith("cohort:") for s in a.subjects)
                else "CONFLICTING_FACT" if conf else "SPECIFIC_FACT")
        src = source_lookup(aid) if source_lookup else None
        _c = _conf_cache.get(aid)
        included.append({
            "kind": kind,
            "conflict_analysis": conflict_analysis,
            "id": aid,
            "confidence": _c[0] if _c else None,
            "confidence_because": _c[1] if _c else None,
            "subjects": sorted(a.subjects),
            "proposition": a.proposition,
            "content": ((lambda L: L.get("label") if isinstance(L, dict) else L)(
                            p.labels.get(aid) or {}) or
                        f"{', '.join(sorted(a.subjects))}: {a.proposition.replace('_', ' ')}"),
            "status": state,
            "since": a.assertion_time,
            "learned_by": a.agent,
            "scope": scope,
            "source": src,
            "grounded": grounded == "GROUNDED" or grounded is True,
            "provenance_count": len(prov_ids),
            "path": next((rel_paths[r] for r in
                          sorted(set(a.subjects) & set(related),
                                 key=lambda r: (rel_hops.get(r, 9), r))
                          if r in rel_paths), None),
            "learned_at": a.assertion_time,
            "event_time": getattr(a, "event_time", None),
            "memory_class": extras.get("mclass"),
            "supported_by": 1 + int(extras.get("reinforcements") or 0),
            "why_included": "; ".join(why) or "matched retrieval",
            "conflicts": conf,
            "inspect": f"/v1/assertions/{aid}/why",
        })
        if len(included) >= max(1, min(50, int(limit))):
            break
    if max_chars is not None and max_chars > 0:
        import json as _json
        kept, used = [], 0
        for m in included:
            sz = len(_json.dumps(m))
            if used + sz > max_chars and kept:
                excluded.append({"id": m["id"],
                                 "reason": "trimmed by the pack size budget (lower relevance rank)"})
                continue
            kept.append(m)
            used += sz
        included = kept
    t3 = time.perf_counter()
    return {
        "memories": included,
        "context": {"agent": agent, "entities": ents, "as_of": T,
                    "task": (task or "")[:200] or None, "user": user},
        "excluded": excluded[:25],
        "stats": {"candidates": len(candidates), "included": len(included),
                  "excluded": len(excluded),
                  "latency_ms": {
                      "context": round((t1 - t0) * 1000, 2),
                      "candidates": round((t2 - t1) * 1000, 2),
                      "decision": round((t3 - t2) * 1000, 2),
                      "total": round((t3 - t0) * 1000, 2)}},
    }
