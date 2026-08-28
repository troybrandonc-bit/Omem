"""What changed: the belief diff between two logical times.

Every piece of this has been reconstructable since the beginning -- the
supersession ledger gives belief state at any past T, conflicts() takes a T,
the referent partition takes a T -- and no surface ever asked the obvious
question: WHAT CHANGED since I was last here? An agent starting a session
does not want the whole memory pack again; it wants the delta. Sarah left,
the renewal closed, a conflict resolved, two records turned out to be one
person. That is the first thing a colleague back from holiday asks, and
until now the only way to answer it was to run two as_of queries yourself
and compare.

diff(since) is that comparison, done once, deterministically, from state the
engine already holds:

  appeared     beliefs asserted after `since` and still open now
  closed       beliefs open at `since` and not open now, each with HOW it
               closed: superseded (and by what) or withdrawn
  conflicts    newly contradicted propositions, and ones no longer contested
  identity     referents that merged, and ones that split

Read-only. Nothing here writes an op, changes a projection, or decides
belief -- it renders the difference between two answers the engine gives.
Scope applies as it does everywhere: a viewer's diff contains only what that
viewer could have recalled, and a conflict shows only when both sides are
visible to them. Bounded and sorted, so the same question gives the same
answer.
"""
from __future__ import annotations

MAX_ITEMS = 100


def _open_at(p, a, T) -> bool:
    try:
        return bool(p.engine.ledger.is_open_at(a, T))
    except Exception:
        return False


def _visible(scopes, scope_map, aid, viewer, teams, user) -> bool:
    # viewer=None is an operator/session read and sees everything, the same
    # convention the conflicts endpoint uses.
    if scopes is None or viewer is None:
        return True
    return scopes.visible(scope_map.get(aid, "org"), viewer, teams or set(), user)


def _shape(p, a) -> dict:
    meta = p.labels.get(a.id)
    return {"id": a.id, "proposition": a.proposition,
            "subjects": sorted(a.subjects), "agent": a.agent,
            "assertion_time": a.assertion_time,
            "label": (meta.get("label") if isinstance(meta, dict) else None)}


def _closer_of(p, aid: str):
    """The assertion that closed this one, via the supersession derivation
    the revision engine recorded. None when nothing links (should not happen
    for a closed interval, but a diff must not crash on a surprise)."""
    for d in p.engine.store.derivations_referencing(aid):
        if d.kind != "supersession" or aid not in d.antecedents:
            continue
        return p.engine.store.assertion(d.consequent)
    return None


def _class_map(p, T) -> dict:
    out = {}
    for cls in p.engine.referent_partition(T):
        members = frozenset(cls)
        for e in members:
            out[e] = members
    return out


def diff(p, db, scopes, since: int, viewer=None, teams=None, user=None) -> dict:
    from omem_engine.canon import RETRACTED

    T = p.now()
    since = min(int(since), T)
    scope_map = scopes.bulk(p.id) if scopes else {}

    appeared, closed = [], []
    for a in sorted(p.engine.store.assertions(),
                    key=lambda x: (-x.assertion_time, x.id)):
        if a.proposition == RETRACTED or (a.proposition or "").startswith("COREF("):
            continue  # machinery; identity changes get their own section
        if not _visible(scopes, scope_map, a.id, viewer, teams, user):
            continue
        if a.assertion_time > since and _open_at(p, a, T):
            if len(appeared) < MAX_ITEMS:
                appeared.append(_shape(p, a))
            continue
        if _open_at(p, a, since) and not _open_at(p, a, T):
            if len(closed) >= MAX_ITEMS:
                continue
            entry = _shape(p, a)
            closer = _closer_of(p, a.id)
            if closer is not None and closer.proposition == RETRACTED:
                entry["how"] = "withdrawn"
                entry["by"] = closer.agent
            elif closer is not None:
                entry["how"] = "superseded"
                entry["by"] = closer.agent
                entry["superseded_by"] = {"id": closer.id,
                                          "proposition": closer.proposition}
            else:
                entry["how"] = "closed"
            closed.append(entry)

    def _conflict_view(pairs):
        out = []
        for pair in sorted(pairs, key=lambda x: sorted(x)):
            a_id, b_id = sorted(pair)
            if not (_visible(scopes, scope_map, a_id, viewer, teams, user)
                    and _visible(scopes, scope_map, b_id, viewer, teams, user)):
                continue  # a conflict must not leak a side the viewer cannot see
            a, b = p.engine.store.assertion(a_id), p.engine.store.assertion(b_id)
            if a is None or b is None:
                continue
            out.append({"pair": [a_id, b_id],
                        "propositions": [a.proposition, b.proposition]})
            if len(out) >= MAX_ITEMS:
                break
        return out

    try:
        was = {frozenset(x) for x in p.engine.conflicts(since)}
        now = {frozenset(x) for x in p.engine.conflicts(T)}
    except Exception:
        was = now = set()
    new_conflicts = _conflict_view(now - was)
    resolved_conflicts = _conflict_view(was - now)

    then_cls = _class_map(p, since)
    now_cls = _class_map(p, T)
    merged, split = [], []
    for members in sorted({v for v in now_cls.values() if len(v) >= 2},
                          key=lambda m: sorted(m)):
        if len({then_cls.get(e, frozenset((e,))) for e in members}) > 1:
            merged.append(sorted(members))
    for members in sorted({v for v in then_cls.values() if len(v) >= 2},
                          key=lambda m: sorted(m)):
        if len({now_cls.get(e, frozenset((e,))) for e in members}) > 1:
            split.append(sorted(members))

    return {"since": since, "as_of": T,
            "appeared": appeared, "closed": closed,
            "new_conflicts": new_conflicts,
            "resolved_conflicts": resolved_conflicts,
            "identity": {"merged": merged[:MAX_ITEMS], "split": split[:MAX_ITEMS]},
            "quiet": not (appeared or closed or new_conflicts
                          or resolved_conflicts or merged or split)}
