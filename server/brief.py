"""P6 situation brief — "what do I need to know about this situation?"

Composes the P1–P5 layers into ONE answer an agent can act on. It does not
re-derive truth: it calls the existing memory pack (candidates → decision →
scope → engine state), then organises the result into a task-shaped brief and
attaches a transparent PRIORITY SCORE assembled ONLY from state that actually
exists. Nothing here invents confidence, similarity, or trust numbers.

    build_situation_brief(...) →
        {
          about, context, as_of,
          summary            # counts, not prose fabrication
          sections: {
            current_facts    # SPECIFIC_FACT, believed now, most relevant first
            relationships    # graph-reached, with the path that reached them
            conflicts        # both sides + deterministic recommendation
            patterns         # generalised knowledge (lowest precedence)
          },
          priority_model     # the exact signals + weights used (auditable)
          excluded, stats
        }

PRIORITY MODEL (deterministic, documented; every term is real stored state):
    directness   +3  the memory's subjects intersect the context entities
    graph_hop    +1  reached via a relationship edge (1 hop) — still relevant,
                     but below a direct fact
    specificity  +2  SPECIFIC_FACT/CONFLICTING_FACT; generalisations get 0 so a
                     specific fact always outranks the pattern about it
    reinforcement +min(support-1, 3)  independent supporting observations, capped
    recency      tie-break only: later assertion_time first (never a score, so
                 a single recent memory can't outweigh a well-supported one)
    conflict_win +1  the best-supported side of an open conflict
The score orders WITHIN the engine-decided candidate set; it never changes any
belief state, and identical inputs yield an identical brief.
"""
from __future__ import annotations
import time

import recall as _recall

PRIORITY_WEIGHTS = {"directness": 3, "graph_hop": 1, "specificity": 2,
                    "reinforcement_cap": 3, "conflict_win": 1}


def _priority(item: dict, context_entities: set[str]) -> tuple[int, list[str]]:
    score = 0
    why = []
    subs = set(item.get("subjects") or [])
    if subs & context_entities:
        score += PRIORITY_WEIGHTS["directness"]
        why.append(f"directly concerns {', '.join(sorted(subs & context_entities))}")
    elif item.get("path"):
        score += PRIORITY_WEIGHTS["graph_hop"]
        why.append(f"reached via relationship: {item['path']}")
    if item.get("kind") in ("SPECIFIC_FACT", "CONFLICTING_FACT"):
        score += PRIORITY_WEIGHTS["specificity"]
    support = int(item.get("supported_by") or 1)
    if support > 1:
        inc = min(support - 1, PRIORITY_WEIGHTS["reinforcement_cap"])
        score += inc
        why.append(f"{support} independent supporting observations")
    ca = item.get("conflict_analysis")
    if ca and ca.get("recommendation") and ca["recommendation"]["assertion"] == item["id"]:
        score += PRIORITY_WEIGHTS["conflict_win"]
        why.append("best-supported side of an open conflict")
    return score, why


def build_situation_brief(p, db, scope_store, *, agent, context="", task="",
                          about=None, user=None, entities=None, as_of=None,
                          limit=12, max_chars=None, source_lookup=None,
                          extras_lookup=None, conflict_analyzer=None) -> dict:
    t0 = time.perf_counter()
    ents = list(entities or [])
    if isinstance(about, str) and about:
        ents = [about] + ents
    # reuse the whole P1–P5 decision pipeline (scope, engine state, graph hop,
    # conflict embedding). We ask for a generous candidate limit, then rank +
    # section + budget here.
    pack = _recall.build_memory_pack(
        p, db, scope_store, agent=agent, context=context, task=task, user=user,
        entities=ents, as_of=as_of, limit=max(limit * 3, 30),
        source_lookup=source_lookup, extras_lookup=extras_lookup,
        conflict_analyzer=conflict_analyzer)
    ctx_entities = set(pack["context"]["entities"])

    ranked = []
    for m in pack["memories"]:
        score, pwhy = _priority(m, ctx_entities)
        m = dict(m)
        m["priority"] = score
        m["priority_reasons"] = pwhy
        ranked.append(m)
    # deterministic: priority desc, then recency desc, then id
    ranked.sort(key=lambda m: (-m["priority"], -(m.get("since") or 0), m["id"]))

    sections = {"current_facts": [], "relationships": [], "conflicts": [], "patterns": []}
    seen_conflict_props = set()
    kept, used = [], 0
    for m in ranked:
        if len(kept) >= limit:
            break
        if max_chars:
            import json as _json
            sz = len(_json.dumps(m))
            if used + sz > max_chars and kept:
                pack["excluded"].append({"id": m["id"],
                                         "reason": "trimmed by situation-brief size budget"})
                continue
            used += sz
        kept.append(m)
        if m["kind"] == "GENERAL_PATTERN":
            sections["patterns"].append(m)
        elif m["kind"] == "CONFLICTING_FACT":
            key = (tuple(m["subjects"]), m["proposition"])
            sections["conflicts"].append(m)
        elif m.get("path") and not (set(m["subjects"]) & ctx_entities):
            sections["relationships"].append(m)
        else:
            sections["current_facts"].append(m)

    t1 = time.perf_counter()
    return {
        "about": about,
        "context": pack["context"],
        "task": (task or None),
        "summary": {
            "current_facts": len(sections["current_facts"]),
            "relationships": len(sections["relationships"]),
            "conflicts": len(sections["conflicts"]),
            "patterns": len(sections["patterns"]),
            "total_included": len(kept),
        },
        "sections": sections,
        "priority_model": {"weights": PRIORITY_WEIGHTS,
                           "note": "deterministic; ranks within engine-decided "
                                   "candidates; never alters belief state"},
        "excluded": pack["excluded"][:25],
        "stats": {**pack["stats"],
                  "brief_ms": round((t1 - t0) * 1000, 2)},
    }
