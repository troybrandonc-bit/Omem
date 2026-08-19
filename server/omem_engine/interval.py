"""Phase 3 — belief-interval engine (Model 14.3, 14.4, 14.7; N5 half-open).

A belief-interval is half-open [start, end): it contains its open bound and
excludes its close bound (14.3 as amended by N5). start = the Assertion's
assertion-time. end = the assertion-time of the supersession that closed it, or
None ("still believed").

INV-3 fidelity: the close bound is NOT stored on the frozen Assertion. It is a
computed view over the supersession ledger (revision engine, Phase 5) — this module
takes the closure map as input and never mutates a primitive.

Determinism / N5: every closed interval is non-empty because supersession requires
strictly-greater assertion-time (Model 13.1 amended). So [s, e) with e > s always,
and the point T = s is always contained.
"""

from __future__ import annotations

from typing import Dict, Optional

from .primitives import Assertion


def is_open_at(assertion: Assertion, close_time: Optional[int], T: int) -> bool:
    """Half-open evaluation (Model 14.3 as amended, N5).

    open at T  iff  start <= T  and  (end is None or T < end)
    where start = assertion_time, end = close_time (None if never closed).
    """
    s = assertion.assertion_time
    if T < s:
        return False
    if close_time is None:
        return True
    return T < close_time


class IntervalLedger:
    """Holds the computed close bound for each Assertion id.

    Populated by the revision engine (Phase 5) when a supersession closes an
    interval. Kept separate from the store so primitives remain immutable (INV-3)
    and interval state is a recomputable view (INV-9).
    """

    def __init__(self) -> None:
        self._close: Dict[str, int] = {}  # assertion id -> close time (exclusive)
        self._version = 0                 # bumped on every close; see `version`

    @property
    def version(self) -> int:
        """A counter that changes whenever a close bound is added.

        Exists so a derived view can be cached and invalidated exactly. Closing an
        interval changes which assertions are open at T, and therefore the referent
        partition at T, without adding any primitive to the store — so a store
        sequence number alone would not notice it, and a cache keyed only on that
        would serve a partition computed before a split. Nothing here decides
        belief; this is a cache-correctness input and nothing more.
        """
        return self._version

    def close(self, assertion_id: str, close_time: int) -> None:
        # INV-4: once closed, never reopened. A second close is a monotonicity
        # violation and is rejected by the revision engine before reaching here;
        # we assert defensively.
        if assertion_id in self._close:
            raise ValueError(f"interval already closed (INV-4): {assertion_id}")
        self._close[assertion_id] = close_time
        self._version += 1

    def close_time(self, assertion_id: str) -> Optional[int]:
        return self._close.get(assertion_id)

    def is_closed(self, assertion_id: str) -> bool:
        return assertion_id in self._close

    def is_open_at(self, assertion: Assertion, T: int) -> bool:
        return is_open_at(assertion, self._close.get(assertion.id), T)
