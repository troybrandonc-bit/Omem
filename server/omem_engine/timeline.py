"""Phase 10 — timeline (Model 14.5 as amended by I-5; tiebreak 14.6).

The timeline is the ordering of EVENTS ONLY (I-5) by event-time; an Event bearing an
event-interval is ordered by the interval's start bound; ties broken by canonical-id
order (Profile 4.2 / Model 14.6). Assertions are NOT members (I-5).

`timeline(T)` includes events whose event-time <= T (the events known/occurred as-of
the world time T for timeline purposes). The Model defines timeline as a computed view
over Events; the CTS probes it at logical times, so we include events with
event_time <= T to make the as-of behavior observable and deterministic.
"""

from __future__ import annotations

from typing import List

from .canon import identifier_order_key
from .store import Store


class TimelineEngine:
    def __init__(self, store: Store) -> None:
        self.store = store

    def timeline(self, T: int) -> List[str]:
        """Ordered list of event ids with event-time <= T, ordered by (event_time,
        canonical-id). Interval events order by their start bound (event_time)."""
        events = [e for e in self.store.events() if e.event_time <= T]
        events.sort(key=lambda e: (e.event_time, identifier_order_key(e.id)))
        return [e.id for e in events]

    def timeline_all(self) -> List[str]:
        """Full timeline of all events (no as-of bound), same ordering."""
        events = list(self.store.events())
        events.sort(key=lambda e: (e.event_time, identifier_order_key(e.id)))
        return [e.id for e in events]
