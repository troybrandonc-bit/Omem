"""The five OMEM primitives (Model 5). Exactly five; no sixth (Model 5.1, 19.6).

Each primitive is an immutable value object. Immutability is how the reference
implementation enforces INV-3 (append-only meaning: no recorded primitive may be
mutated). `frozen=True` makes field assignment raise at the language level.

Fields are exactly those the Model requires:
  Entity     (7.1): stable id + type designator ONLY. No attributes (7.2, 19.2).
  Event      (9.1): stable id, event-time OR event-interval, kind.
  Agent     (10.1): stable id, kind.
  Assertion  (8.1): one agent, >=1 entity subjects, proposition, assertion-time,
                    belief-interval, OPTIONAL event-time, confidence.
  Derivation(11.1): one consequent assertion, >=1 antecedents, kind.

Belief-intervals (14.3) are half-open [start, end); end=None means unbounded
("still believed"). Interval logic lives in interval.py; the Assertion stores the
close bound as mutable-by-supersession *only through the store*, never in place —
see store.py, which records closure as a new fact, keeping the Assertion object's
recorded meaning intact per INV-3. To honor immutability strictly, the close bound
is held in the store's interval ledger, NOT on the frozen Assertion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .canon import canon_identifier, canon_proposition


# Derivation kinds named by the Model (11.1, 11.4). Open vocabulary (21.1): unknown
# kinds are valid opaque values, so this set is advisory, not a gate.
KIND_INFERENCE = "inference"
KIND_EXTRACTION = "extraction"
KIND_SUPERSESSION = "supersession"
KIND_COREFERENCE = "coreference"
KIND_AGGREGATION = "aggregation"


@dataclass(frozen=True)
class Entity:
    """P1 — a referent. Identity + type only (Model 7.1, 7.2)."""
    id: str
    type: str

    def __post_init__(self) -> None:
        canon_identifier(self.id)  # Profile 4: reject ill-formed id eagerly


@dataclass(frozen=True)
class Event:
    """P3 — an Observation (Model 9.1).

    event_time locates it in world time. An event-interval (9.1) is represented by
    (event_time, event_end); a point Event has event_end is None. Timeline ordering
    (14.5, amended) orders by event_time (interval start) then id.
    """
    id: str
    kind: str
    event_time: int
    event_end: Optional[int] = None  # present => event-interval [event_time, event_end)

    def __post_init__(self) -> None:
        canon_identifier(self.id)


@dataclass(frozen=True)
class Agent:
    """P4 — an asserter (Model 10.1). recorded_existence is the logical time the
    Agent was recorded (INV-7 amended): assertion-time MUST NOT precede it."""
    id: str
    kind: str
    recorded_existence: int

    def __post_init__(self) -> None:
        canon_identifier(self.id)


@dataclass(frozen=True)
class Assertion:
    """P2 — a claim (Model 8.1).

    subjects: tuple of Entity ids (>=1, INV-2), order not observable.
    proposition: opaque comparable value (8.2); compared via canon.
    agent: exactly one Agent id (INV-1).
    assertion_time: logical time the claim was made (14.1).
    event_time: OPTIONAL world time the proposition concerns (14.2), may be future.
    confidence: OPTIONAL, in [0,1] (8.5).

    The belief-interval START is assertion_time (14.3). The CLOSE bound is NOT stored
    on this frozen object (INV-3): closure is recorded by the store as a supersession
    fact, so the Assertion's recorded meaning never mutates.
    """
    id: str
    agent: str
    subjects: Tuple[str, ...]
    proposition: str
    assertion_time: int
    event_time: Optional[int] = None
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        canon_identifier(self.id)
        canon_proposition(self.proposition)  # Profile 3: reject ill-formed proposition
        # INV-1 / INV-2 are enforced at operation time in the store (so the correct
        # reason code R_NO_AGENT / R_NO_SUBJECT is returned), but we defend here too.
        object.__setattr__(self, "subjects", tuple(self.subjects))


@dataclass(frozen=True)
class Derivation:
    """P5 — why a claim exists (Model 11.1).

    consequent: exactly one Assertion id.
    antecedents: tuple of primitive ids (Assertions and/or Events), >=1.
    kind: designator (11.1); supersession/coreference are special (11.4).
    """
    id: str
    consequent: str
    antecedents: Tuple[str, ...]
    kind: str

    def __post_init__(self) -> None:
        canon_identifier(self.id)
        object.__setattr__(self, "antecedents", tuple(self.antecedents))
