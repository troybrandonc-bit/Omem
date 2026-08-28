"""P5 memory graph. Relationships are ENGINE FACTS first, graph second:

    assertion  subjects=[person:sarah, company:acme]  prop=rel_works_at
        │ (truth, provenance, supersession, contradiction, frozen engine)
        ▼
    memory_edges row  person:sarah --works_at--> company:acme
        (direction + traversal index; a pure PROJECTION)

An edge is visible only while its assertion is OPEN at the queried time and
VISIBLE to the viewer's scope. Retraction/supersession make the edge vanish
from traversal automatically. The row is never deleted, truth stays in the
engine, and history remains reconstructable through as_of.

Traversal is bounded (depth ≤ MAX_DEPTH, fanout ≤ MAX_FANOUT per node,
MAX_NODES total) and deterministic (sorted expansion). The graph layer can
never override the engine: it holds no propositions of its own.
"""
from __future__ import annotations
import time

MAX_DEPTH = 2
MAX_FANOUT = 8
MAX_NODES = 40

GRAPH_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_edges(
  project_id TEXT NOT NULL, assertion_id TEXT NOT NULL,
  src TEXT NOT NULL, relation TEXT NOT NULL, dst TEXT NOT NULL,
  created REAL NOT NULL,
  PRIMARY KEY(project_id, assertion_id));
CREATE INDEX IF NOT EXISTS edges_src ON memory_edges(project_id, src);
CREATE INDEX IF NOT EXISTS edges_dst ON memory_edges(project_id, dst);
"""

# The relation vocabulary, in ONE place. It used to be spelled in five files
# that could not agree: this tuple, the LLM prompt (which offered five of the
# eight), the deterministic regexes, the consolidation hints, and the MCP tool
# prose. Every consumer now derives from this registry or is pinned to it by
# tests_relation_registry.py, so adding a relation is one edit here plus the
# prose updates that suite refuses to let drift.
#
# `reads` is how a directed edge is read aloud -- prompt and doc material,
# never parsed. Endpoint kinds in it are convention, not enforcement: type
# constraints on relations are constraints.py's job, declared per project.
RELATION_REGISTRY = {
    "works_at":   {"reads": "src works at dst (person -> organisation)"},
    "uses":       {"reads": "src uses dst (organisation -> product)"},
    "managed_by": {"reads": "src is managed by dst (account -> person)"},
    "reports_to": {"reads": "src reports to dst (person -> person)"},
    "partner_of": {"reads": "src is a partner of dst (organisation -> organisation)"},
    "supplies":   {"reads": "src supplies dst (organisation -> organisation)"},
    "owns":       {"reads": "src owns dst (organisation -> organisation)"},
    "involves":   {"reads": "src's orbit involves dst (organisation -> person)"},
}
RELATIONS = tuple(RELATION_REGISTRY)


def prompt_enum() -> str:
    """The relation alternatives for the extraction prompt, derived so the
    prompt can never again offer the model fewer relations than the graph
    accepts (it offered five of eight for two releases and nobody could see
    it from either file alone)."""
    return "|".join(f'"{r}"' for r in RELATIONS)


def record_edge(db, project_id: str, assertion_id: str, src: str,
                relation: str, dst: str):
    if relation not in RELATIONS:
        raise ValueError(f"unknown relation {relation!r}")
    db.execute("INSERT OR REPLACE INTO memory_edges VALUES(?,?,?,?,?,?)",
               (project_id, assertion_id, src, relation, dst, time.time()))
    db.commit()


def relation_of(proposition: str):
    """The relation this proposition names, or None. THE single decision point.

    Both the write-time projection and the boot rebuild ask this, so an edge
    that appears live and an edge that survives a restart can never disagree
    about what counts as a relation. They used to answer separately, and only
    the rebuild answered at all.
    """
    for r in RELATIONS:
        if proposition.startswith(f"rel_{r}") or proposition.startswith(r):
            return r
    return None


import re as _re_dir

_LOCAL_PUNCT = _re_dir.compile(r"[^\w]+", _re_dir.UNICODE)
_LOCAL_RUNS = _re_dir.compile(r"_+")


def _local_token(entity_id: str) -> str:
    """An entity's local part in proposition-token spelling: lowercase, every
    punctuation run (including @ and -) collapsed to _, matching what
    canonical_form does to the proposition the token sits inside."""
    local = entity_id.split(":", 1)[-1].lower()
    return _LOCAL_RUNS.sub("_", _LOCAL_PUNCT.sub("_", local)).strip("_")


def token_direction(subjects, proposition: str):
    """The (src, dst) the proposition itself proves, or None.

    Formation has always written relational propositions as
    rel_<relation>_<target-local> -- extract_relations, infer_employment and
    the rules engine all name the TARGET in the token -- which means most
    relational assertions carry, in engine truth, the one field the engine's
    subject set cannot: which end the relation points at. When the token's
    tail matches exactly one subject's local part, direction is DERIVED rather
    than taken on trust: a direct write is oriented correctly instead of
    falling back to sorted order (which pointed every SDK-written works_at at
    the person), and a rebuild can verify a stored row against it.

    A bare token (rel_works_at, with no target) proves nothing, and a tail
    matching both subjects proves nothing either; both return None and stay
    formation-on-trust, which is the honest limit rather than a guess.
    """
    rel = relation_of(proposition)
    if rel is None:
        return None
    subs = sorted(subjects or ())
    if len(subs) != 2:
        return None
    tail = None
    for prefix in (f"rel_{rel}_", f"{rel}_"):
        if proposition.startswith(prefix):
            tail = proposition[len(prefix):]
            break
    if not tail:
        return None
    hits = [s for s in subs if _local_token(s) == tail]
    if len(hits) != 1:
        return None
    dst = hits[0]
    src = subs[0] if dst == subs[1] else subs[1]
    return src, dst


def project_assertion(db, project_id: str, assertion_id: str,
                      subjects, proposition: str) -> bool:
    """Project one accepted assertion into the graph, at write time.

    The graph is a projection of engine state, and it was only ever built at
    boot (rebuild_projection) or on the ingest/observe path. An assertion
    written directly -- POST /v1/assertions, Memory.remember(), omem_remember
    -- created no edge at all, so a relation recorded that way was invisible to
    traversal until the process restarted. The candidate index has always been
    kept in lockstep on every write; this puts the graph on the same footing.

    Direction matches rebuild_projection exactly: the proposition token is
    authoritative when it names the target (token_direction), then an existing
    row (formation direction survives), then sorted order -- so a rebuild is a
    no-op over anything written here.
    """
    subs = sorted(subjects or ())
    if len(subs) < 2:
        return False
    rel = relation_of(proposition)
    if rel is None:
        return False
    td = token_direction(subs, proposition)
    if td is not None:
        src, dst = td
    else:
        row = db.execute("SELECT src, dst FROM memory_edges WHERE project_id=? "
                         "AND assertion_id=?", (project_id, assertion_id)).fetchone()
        src, dst = subs[0], subs[1]
        if row is not None and {row["src"], row["dst"]} == set(subs):
            src, dst = row["src"], row["dst"]
    record_edge(db, project_id, assertion_id, src, rel, dst)
    return True


def _live(p, aid: str, T) -> bool:
    a = p.engine.store.assertion(aid)
    if a is None:
        return False
    try:
        return bool(p.engine.ledger.is_open_at(a, T))
    except Exception:
        return False


def edges_of(db, p, entity: str, *, T=None, scopes=None, viewer=None,
             teams=None, user=None, limit: int = MAX_FANOUT) -> list[dict]:
    """Live, scope-visible edges touching one entity. Deterministic order."""
    T = T if T is not None else p.now()
    scope_map = scopes.bulk(p.id) if scopes else {}
    out = []
    for r in db.execute(
            "SELECT * FROM memory_edges WHERE project_id=? AND (src=? OR dst=?) "
            "ORDER BY src, relation, dst", (p.id, entity, entity)):
        if not _live(p, r["assertion_id"], T):
            continue
        if scopes is not None and viewer is not None:
            sc = scope_map.get(r["assertion_id"], "org")
            if not scopes.visible(sc, viewer, teams or set(), user):
                continue  # invisible edges do not exist for this viewer
        edge = {"assertion": r["assertion_id"], "src": r["src"],
                "relation": r["relation"], "dst": r["dst"]}
        out.append(edge)
        if len(out) >= limit:
            break
    # CONTRADICTION AWARENESS: annotate any edge whose assertion is in an open
    # conflict at T. The edge still renders (the assertion is open) but is
    # never presented as uncontested fact.
    if out:
        try:
            conflicted = {aid for pair in p.engine.conflicts(T) for aid in pair}
            for edge in out:
                if edge["assertion"] in conflicted:
                    edge["contradicted"] = True
        except Exception:
            pass
    return out


def neighbors(db, p, entities: list[str], *, depth: int = 1, T=None,
              scopes=None, viewer=None, teams=None, user=None) -> dict[str, dict]:
    """Bounded BFS. Returns {entity: {"via": edge, "path": [edge...], "hops": n}}
    for entities reached FROM the seed set (seeds excluded). Deterministic.

    `path` is the WHOLE chain from a seed, not just the edge that arrived. Only
    the arriving edge used to be kept, which is enough to say an entity is
    related and not enough to say why: a two-hop entity would be explained as
    though it were one hop away, naming a relation the reader cannot connect to
    anything they asked about. `via` stays as the last edge because subgraph()
    and older callers expect it.
    """
    depth = max(1, min(MAX_DEPTH, int(depth)))
    seen = {e: {"hops": 0} for e in entities}
    paths: dict[str, list] = {e: [] for e in entities}
    frontier = sorted(entities)
    found: dict[str, dict] = {}
    for hop in range(1, depth + 1):
        nxt = []
        for e in frontier:
            for edge in edges_of(db, p, e, T=T, scopes=scopes, viewer=viewer,
                                 teams=teams, user=user):
                other = edge["dst"] if edge["src"] == e else edge["src"]
                if other in seen or len(seen) >= MAX_NODES:
                    continue
                seen[other] = {"hops": hop}
                # BFS, so the first arrival is the shortest path. Sorted
                # expansion keeps which one that is deterministic.
                #
                # `from`/`to` record the direction of TRAVEL, which is not the
                # direction of the edge: traversal is undirected, so a chain can
                # walk against an edge. Without this a path renders in edge
                # order and reads backwards from whatever was asked about,
                # starting at a node the caller never mentioned.
                paths[other] = paths[e] + [dict(edge, **{"from": e, "to": other})]
                found[other] = {"via": edge, "path": paths[other], "hops": hop}
                nxt.append(other)
        frontier = sorted(nxt)
        if not frontier:
            break
    return found


def rebuild_projection(db, p) -> dict:
    """Rebuild memory_edges purely from engine state. The graph is a
    PROJECTION: every edge must be justified by a live multi-subject relational
    assertion. Returns a diff so restart/rebuild consistency is provable.

    An edge is (re)created for every assertion whose proposition starts 'rel_'
    (or 'works_at'/'uses'/... after canonicalisation) and has >=2 subjects.
    Rows with no backing assertion are dropped (dangling-reference cleanup).
    Idempotent: running twice yields identical rows.

    DIRECTION IS DERIVED WHERE THE TOKEN PROVES IT, AND ON TRUST WHERE IT
    CANNOT. The engine holds subjects as a set -- primitives.py: "order not
    observable", and trust.py compares them with frozenset -- so subject order
    carries no direction. But the PROPOSITION is engine truth too, and
    formation has always spelled relational propositions rel_<rel>_<target>:
    when that tail names exactly one subject (token_direction), the direction
    is derived from engine state, a reversed row is caught and repaired here,
    and reconcile reports it as drift.

    A bare token (rel_works_at, no target) proves nothing. For those,
    direction still comes from FORMATION (the ingest path knows it and passes
    it to record_edge) and is preserved whenever the stored row spans the same
    two subjects; sorted order is the last fallback. A bare-token row whose
    direction was corrupted survives, and reconcile reports the system clean,
    because there is genuinely nothing to check it against. Giving subjects an
    observable order would close that residue at the cost of an engine
    invariant, which is not a projection's trade to make."""
    existing = {r["assertion_id"]: (r["src"], r["relation"], r["dst"])
                for r in db.execute("SELECT * FROM memory_edges WHERE project_id=?", (p.id,))}
    rebuilt: dict[str, tuple] = {}
    for a in p.engine.store.assertions():
        if len(a.subjects) < 2:
            continue
        # A row is kept iff a real relational assertion backs it - OPEN OR
        # CLOSED. Temporal/open filtering happens per-query in _live() so that
        # as_of history (superseded edges at past times) is preserved. Rebuild
        # only removes DANGLING rows (no backing assertion at all).
        rel = relation_of(a.proposition)
        if rel is None:
            continue
        subs = sorted(a.subjects)
        # deterministic direction: token first (derived from engine truth, so
        # a reversed row is corrected), then the stored row (authoritative
        # formation direction for bare tokens), then sorted order.
        td = token_direction(subs, a.proposition)
        if td is not None:
            src, dst = td
        elif a.id in existing:
            src, _, dst = existing[a.id]
            if {src, dst} != set(subs):
                src, dst = subs[0], subs[1]
        else:
            src, dst = subs[0], subs[1]
        rebuilt[a.id] = (src, rel, dst)
    # apply
    added = removed = 0
    for aid, (src, rel, dst) in rebuilt.items():
        if existing.get(aid) != (src, rel, dst):
            db.execute("INSERT OR REPLACE INTO memory_edges VALUES(?,?,?,?,?,?)",
                       (p.id, aid, src, rel, dst, time.time()))
            added += 1
    for aid in existing:
        if aid not in rebuilt:
            db.execute("DELETE FROM memory_edges WHERE project_id=? AND assertion_id=?",
                       (p.id, aid))
            removed += 1
    db.commit()
    return {"edges": len(rebuilt), "reconciled": added, "dropped_dangling": removed}


def subgraph(db, p, entity: str, *, depth: int = 1, T=None, scopes=None,
             viewer=None, teams=None, user=None) -> dict:
    """Nodes + directed edges around an entity, scope-safe and bounded."""
    T = T if T is not None else p.now()
    hops = neighbors(db, p, [entity], depth=depth, T=T, scopes=scopes,
                     viewer=viewer, teams=teams, user=user)
    nodes = {entity: 0, **{e: v["hops"] for e, v in hops.items()}}
    edges, seen_e = [], set()
    for e in sorted(nodes):
        for edge in edges_of(db, p, e, T=T, scopes=scopes, viewer=viewer,
                             teams=teams, user=user):
            if edge["src"] in nodes and edge["dst"] in nodes:
                key = (edge["src"], edge["relation"], edge["dst"])
                if key not in seen_e:
                    seen_e.add(key)
                    edges.append(edge)
    def _label(eid):
        meta = p.labels.get(eid)
        return (meta.get("label") if isinstance(meta, dict) else None) or eid.split(":", 1)[-1]
    return {"entity": entity, "as_of": T, "depth": depth,
            "nodes": [{"id": e, "label": _label(e), "hops": h}
                      for e, h in sorted(nodes.items(), key=lambda kv: (kv[1], kv[0]))],
            "edges": edges}
