"""P4 conflict reasoning. The frozen engine preserves contradictions; this
layer makes them USEFUL: for a conflicted pair it assembles each side's real
evidence and produces a deterministic, explainable recommendation, while the
engine's truth state remains untouched and both sides remain retrievable.

──────────────────────────────────────────────────────────────────────────────
P4 RECOMMENDATION POLICY (explicit intelligence-layer policy, documented here
because the frozen model deliberately does not rank open contradictions):

  Given two OPEN conflicting assertions, compare in strict order:
  1. RECENCY      the side asserted at the later logical time wins, newer
                  direct information supersedes older inference in practice
                  even when no formal supersession was recorded.
  2. CORROBORATION if asserted at the same logical time, the side with more
                  independent support (1 + reinforcement rows + distinct
                  agents beyond the learner) wins.
  3. AUTHORITY    if still tied, the side whose learning/reinforcing agents
                  include a connector with higher stored authority (the real
                  `connectors.authority` column) wins. Runtime agents without
                  a connector row contribute no authority weight.
  4. UNRESOLVED   a full tie yields NO recommendation. OMEM does not guess.

  Every recommendation lists the reasons actually applied. No numeric
  confidence is fabricated at any point: counts are counts, times are times,
  authority is the stored connector value.
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from consolidation import reinforcement_rows


def _authority_of(db, project_id: str, agent_id: str) -> float | None:
    r = db.execute("SELECT MAX(authority) a FROM connectors "
                   "WHERE project_id=? AND agent_id=?", (project_id, agent_id)).fetchone()
    return r["a"] if r and r["a"] is not None else None


def _side(p, db, aid: str) -> dict | None:
    a = p.engine.store.assertion(aid)
    if a is None:
        return None
    reinf = reinforcement_rows(db, p.id, aid)
    agents = [a.agent] + [r["observed_by"] for r in reinf]
    distinct_agents = sorted(set(agents))
    auths = [x for x in (_authority_of(db, p.id, ag) for ag in distinct_agents)
             if x is not None]
    meta = p.labels.get(aid)
    return {
        "assertion": aid,
        "proposition": a.proposition,
        "content": (meta.get("label") if isinstance(meta, dict) else None)
                   or f"{', '.join(sorted(a.subjects))}: {a.proposition}",
        "subjects": sorted(a.subjects),
        "learned_by": a.agent,
        "asserted_at": a.assertion_time,
        "supporting_observations": 1 + len(reinf),
        "reinforced_by": [r["observed_by"] for r in reinf],
        "distinct_agents": distinct_agents,
        "last_reinforced_ts": max((r["ts"] for r in reinf), default=None),
        "max_source_authority": max(auths) if auths else None,
        "inspect": f"/v1/memory/chain?assertion={aid}",
    }


def analyze_pair(p, db, pair) -> dict | None:
    """Deterministic conflict analysis for one engine-reported pair."""
    a_id, b_id = sorted(pair)
    A, B = _side(p, db, a_id), _side(p, db, b_id)
    if A is None or B is None:
        return None
    reasons: list[str] = []
    winner = None
    if A["asserted_at"] != B["asserted_at"]:
        winner = A if A["asserted_at"] > B["asserted_at"] else B
        reasons.append(
            f"asserted more recently (t={winner['asserted_at']}) than the "
            f"conflicting side (t={(B if winner is A else A)['asserted_at']})")
    else:
        sa, sb = A["supporting_observations"], B["supporting_observations"]
        if sa != sb:
            winner = A if sa > sb else B
            reasons.append(
                f"more independent support ({max(sa, sb)} vs {min(sa, sb)} observations)")
        else:
            aa = A["max_source_authority"] or 0.0
            ab = B["max_source_authority"] or 0.0
            if aa != ab:
                winner = A if aa > ab else B
                reasons.append(
                    f"higher stored source authority ({max(aa, ab)} vs {min(aa, ab)})")
    if winner is not None and len(winner["distinct_agents"]) > 1:
        reasons.append(f"corroborated by {len(winner['distinct_agents'])} agents")
    return {
        "sides": [A, B],
        "recommendation": None if winner is None else {
            "assertion": winner["assertion"],
            "proposition": winner["proposition"],
            "reasons": reasons,
        },
        "note": ("both sides remain preserved and retrievable; the engine's "
                 "contradiction state is unchanged" if winner is not None else
                 "evidence is tied. OMEM does not guess; both sides preserved"),
    }


def conflicts_overview(p, db, scopes, viewer: str | None = None,
                       acting_user: str | None = None, limit: int = 50) -> list[dict]:
    """All open conflicts, scope-safe: a pair is listed only when the viewer
    may see BOTH sides. A half-visible pair would leak the hidden side's
    existence. Control-plane reads (no viewer) see everything."""
    T = p.now()
    teams = scopes.teams_of(p.id, viewer) if viewer else set()
    out, seen = [], set()
    for pair in p.engine.conflicts(T):
        key = tuple(sorted(pair))
        if key in seen:
            continue
        seen.add(key)
        if viewer is not None:
            if not all(scopes.visible(scopes.of(p.id, aid), viewer, teams, acting_user)
                       for aid in key):
                continue
        an = analyze_pair(p, db, key)
        if an is not None:
            out.append(an)
        if len(out) >= limit:
            break
    return out
