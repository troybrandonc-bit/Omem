"""Phase 8 — reproducibility markers (Model 16.4; Canonicalization Profile 5).

The marker is computed over a canonical serialization of exactly the permitted inputs
(16.2): the in-scope primitive canonical identifiers, their confidences, and the
logical time. Profile 5 fixes the byte serialization:

  (a) collect contributing primitive identifiers in canonical form, deduplicated;
  (b) sort by unsigned-byte identifier order (Profile 4.2);
  (c) join with U+001F between elements;
  (d) append U+001E;
  (e) append the canonical numeric form of the logical time.

The marker function itself is implementation-defined (16.4); we use SHA-256 over the
canonical input bytes. Because the INPUT bytes are canonical, identical inputs yield
identical marker-inputs across implementations, so equality/inequality of markers is
reproducible regardless of the hash chosen. Markers are compared only for
equality/inequality, never value (CTS V-TRUST-02).
"""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, Optional

from .canon import (canon_identifier, canon_confidence, canon_logical_time,
                    UNIT_SEP, RECORD_SEP)


def canonical_marker_input(
    primitive_ids: Iterable[str],
    confidences: Optional[Dict[str, float]],
    logical_time: int,
) -> bytes:
    """Profile 5 serialization -> canonical input bytes."""
    # dedup + canonicalize identifiers
    canon_ids = {canon_identifier(pid) for pid in primitive_ids}
    # sort by unsigned-byte order (bytes compare is already unsigned-lexicographic)
    ordered = sorted(canon_ids)
    # 5.3: where confidences participate, append each after its id, U+001F-separated,
    # but the ORDERING key remains the identifier. We attach confidence to the element.
    elements = []
    # need id string form to look up confidence; recompute mapping canon->original
    canon_to_conf: Dict[bytes, Optional[str]] = {}
    if confidences:
        for pid, c in confidences.items():
            canon_to_conf[canon_identifier(pid)] = canon_confidence(c)
    for cid in ordered:
        el = cid.decode("utf-8")
        conf = canon_to_conf.get(cid)
        if conf is not None:
            el = el + UNIT_SEP + conf
        elements.append(el)
    id_block = UNIT_SEP.join(elements)
    serialized = id_block + RECORD_SEP + canon_logical_time(logical_time)
    return serialized.encode("utf-8")


def repro_marker(
    primitive_ids: Iterable[str],
    logical_time: int,
    confidences: Optional[Dict[str, float]] = None,
) -> str:
    """Deterministic reproducibility identifier (implementation-defined function over
    canonical inputs). SHA-256 hex. Equality across implementations follows from the
    canonical input, not from this specific hash choice (16.4)."""
    data = canonical_marker_input(primitive_ids, confidences, logical_time)
    return hashlib.sha256(data).hexdigest()
