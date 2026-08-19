"""Phase 6 — proposition engine (Model 8.6/8.7/8.8, J-1, N10; conflict view).

proposition_state(S, P, T) is a total four-valued function (8.8, C4):
  BELIEVED_TRUE   A+ non-empty, A- empty
  BELIEVED_FALSE  A- non-empty, A+ empty
  CONTRADICTED    both non-empty
  UNKNOWN         both empty

A+ = open assertions satisfying S at T (J-1: coreference-reduced subject-set EQUALITY)
     whose proposition affirms P.
A- = same, whose proposition denies P.

Affirm/deny (8.8): determined ONLY by an explicitly recorded contradiction relation
between proposition tokens, never by text parsing. The CTS supplies declared
contradiction pairs; we model that as a ContradictionRegistry of unordered token
pairs. If P's token is directly asserted, it affirms P; if a token declared
contradictory to P is asserted, it denies P.

N10: the reserved RETRACTED proposition contributes to neither A+ nor A- (13.3.1).

beliefs_about(entity, T): the set of open assertion ids in which the entity appears
as a subject (entity-scoped, membership — I-2), reduced under coreference at T.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import FrozenSet, List, Set, Tuple

from .canon import RETRACTED, canon_proposition, proposition_identical, identifier_order_key
from .coreference import CoreferenceRegistry
from .interval import IntervalLedger
from .primitives import Assertion
from .store import Store

BELIEVED_TRUE = "BELIEVED_TRUE"
BELIEVED_FALSE = "BELIEVED_FALSE"
CONTRADICTED = "CONTRADICTED"
UNKNOWN = "UNKNOWN"


class ContradictionRegistry:
    """Explicitly declared contradiction relations between proposition tokens (8.8).
    Unordered pairs. Absent a declared pair, no two tokens contradict (CTS 5.2).

    Indexed by canonical form rather than scanned. Profile 3.1 defines proposition
    identity as byte-equality of the NFC UTF-8 canonical form, which is an
    equivalence relation, so canonicalising once and hashing decides exactly what
    the pairwise scan decided — while turning a walk over every declared pair into
    one dict lookup. `contradicts` runs inside the per-assertion and per-pair loops
    below, so the scan multiplied the cost of every belief query by the size of the
    project's whole vocabulary.
    """

    def __init__(self) -> None:
        self._pairs: Set[FrozenSet[str]] = set()          # as declared, for readback
        self._index: dict = {}                            # canon bytes -> {canon bytes}

    def declare(self, token_a: str, token_b: str) -> None:
        self._pairs.add(frozenset({token_a, token_b}))
        ca, cb = canon_proposition(token_a), canon_proposition(token_b)
        if ca == cb:
            return          # a token cannot contradict itself (identity, below)
        self._index.setdefault(ca, set()).add(cb)
        self._index.setdefault(cb, set()).add(ca)

    def contradicts(self, token_a: str, token_b: str) -> bool:
        ca, cb = canon_proposition(token_a), canon_proposition(token_b)
        if ca == cb:
            return False
        return cb in self._index.get(ca, ())


class PropositionEngine:
    # Distinct logical times to hold a prepared context for. A page asking about
    # one instant is the common case; a few slots also cover a caller walking a
    # short history without turning the cache into a second copy of the store.
    _CTX_SLOTS = 8

    def __init__(self, store: Store, ledger: IntervalLedger,
                 coref: CoreferenceRegistry, contra: ContradictionRegistry) -> None:
        self.store = store
        self.ledger = ledger
        self.coref = coref
        self.contra = contra
        self._ctx_cache: "OrderedDict[tuple, tuple]" = OrderedDict()

    def _all_entity_ids(self) -> Set[str]:
        return {e.id for e in self.store.entities()}

    def _context(self, T: int):
        """Everything a query at T needs, gathered once.

        The reduction map is the point. Reducing one subject set used to compute
        the referent partition of the entire store, once per subject, inside a loop
        over every open assertion — so answering a single question about one
        customer walked every entity and every assertion thousands of times. The
        semantics never needed that: the partition at T is one value, and this
        computes it once and hands back a lookup.

        Held between calls as well as within one, keyed on the store and ledger
        versions plus T, because a caller asking about six propositions at one
        instant was otherwise rebuilding the same three structures six times. Any
        record or interval close changes one of those versions, so a stale context
        cannot be served.

        Nothing here changes what an answer is. Same partition, same canonical
        representative (Profile 4.2 unsigned-byte order), same open-interval test.

        The returned structures are shared with the next caller and must be treated
        as read-only; every reader below only iterates them.
        """
        key = (self.store.version, self.ledger.version, T)
        hit = self._ctx_cache.get(key)
        if hit is not None:
            return hit
        assertions = {a.id: a for a in self.store.assertions()}
        all_ent = self._all_entity_ids()
        reps = self.coref.representatives_at(all_ent, assertions, self.ledger, T)
        open_as = [a for a in assertions.values() if self.ledger.is_open_at(a, T)]
        self._ctx_cache[key] = (reps, open_as)
        while len(self._ctx_cache) > self._CTX_SLOTS:
            self._ctx_cache.popitem(last=False)
        return reps, open_as

    def _reduce(self, subjects: Tuple[str, ...], reps: dict) -> FrozenSet[str]:
        """Reduce a subject set to referents through a prepared map (J-1).

        A subject with no entry is an entity the store does not hold, which under
        the old code came back as its own singleton class; it maps to itself here
        for the same result.
        """
        return frozenset(reps.get(s, s) for s in subjects)

    def _reduced_subject_set(self, subjects: Tuple[str, ...], T: int) -> FrozenSet[str]:
        """Reduce a subject set under the coreference partition at T (J-1): replace
        each subject by a canonical representative of its coreference class, so that
        set equality is computed over referents, not raw entity ids.

        Kept for callers outside this module; the query paths below use a context
        they build once instead of paying for the partition per call.
        """
        reps, _ = self._context(T)
        return self._reduce(subjects, reps)

    def _open_assertions_at(self, T: int) -> List[Assertion]:
        return [a for a in self.store.assertions() if self.ledger.is_open_at(a, T)]

    def proposition_state(self, subject_ids: Tuple[str, ...], proposition: str, T: int) -> str:
        """Total four-valued proposition state (8.8, J-1, N10)."""
        reps, open_as = self._context(T)
        query_S = self._reduce(tuple(subject_ids), reps)
        canon_retracted = canon_proposition(RETRACTED)
        canon_query = canon_proposition(proposition)
        a_plus = False
        a_minus = False
        for a in open_as:
            canon_a = canon_proposition(a.proposition)
            # N10: RETRACTED never contributes to A+/A- for the retracted proposition.
            if canon_a == canon_retracted:
                continue
            # J-1: subject-set EQUALITY under coreference reduction.
            if self._reduce(a.subjects, reps) != query_S:
                continue
            if canon_a == canon_query:
                a_plus = True
            elif self.contra.contradicts(a.proposition, proposition):
                a_minus = True
            # Both sides found: nothing further can change the answer.
            if a_plus and a_minus:
                return CONTRADICTED
        if a_plus and a_minus:
            return CONTRADICTED
        if a_plus:
            return BELIEVED_TRUE
        if a_minus:
            return BELIEVED_FALSE
        return UNKNOWN

    def beliefs_about(self, entity_id: str, T: int) -> Set[str]:
        """Set of open assertion ids in which entity_id (or any entity coreferent with
        it at T) appears as a subject (I-2 membership, coreference-scoped)."""
        assertions = {a.id: a for a in self.store.assertions()}
        all_ent = self._all_entity_ids()
        cls = self.coref.class_of(entity_id, all_ent, assertions, self.ledger, T)
        result: Set[str] = set()
        for a in assertions.values():
            if not self.ledger.is_open_at(a, T):
                continue
            if any(s in cls for s in a.subjects):
                result.add(a.id)
        return result

    def conflicts(self, T: int) -> Set[FrozenSet[str]]:
        """Unordered pairs of open assertion ids with contradictory propositions about
        the same referent at T (Appendix B; ties to 8.8 CONTRADICTED).

        Grouped by referent before pairing. Two assertions can only conflict if their
        reduced subject sets are equal, so comparing across different referents was
        work whose answer was known in advance: every pair in the store was formed and
        then discarded, each discard costing two partition computations. Bucketing
        first leaves only the pairs that could possibly conflict, which is what took
        this from near-cubic to roughly linear on data where subjects are spread over
        many referents.

        Identical results: same pairs, same exclusions, same RETRACTED handling. The
        only change is which comparisons are skipped, and every skipped one was a
        comparison whose subject sets differed.
        """
        reps, open_as = self._context(T)
        canon_retracted = canon_proposition(RETRACTED)

        buckets: dict = {}
        for a in open_as:
            if canon_proposition(a.proposition) == canon_retracted:
                continue      # N10: a retraction is not a side of a conflict
            buckets.setdefault(self._reduce(a.subjects, reps), []).append(a)

        result: Set[FrozenSet[str]] = set()
        for group in buckets.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    if self.contra.contradicts(a.proposition, b.proposition):
                        result.add(frozenset({a.id, b.id}))
        return result
