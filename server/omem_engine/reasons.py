"""Observable rejection reason codes (CTS 6).

The CTS compares the *code*, never any message. This is the entire fixed set;
no implementation may mint another (CTS 6, 13.4 reserves R_UNKNOWN_OP).
"""

from __future__ import annotations


class Rejected(Exception):
    """An operation rejected with an observable reason code (CTS 3.1)."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


# CTS 6 — the fixed reason-code set.
R_NO_AGENT = "R_NO_AGENT"        # INV-1: assertion with no/invalid Agent
R_NO_SUBJECT = "R_NO_SUBJECT"    # INV-2: assertion with no Entity subject
R_MUTATION = "R_MUTATION"        # INV-3: attempt to mutate a recorded primitive
R_REOPEN = "R_REOPEN"            # INV-4: reopen a closed belief-interval
R_CYCLE = "R_CYCLE"              # INV-5: derivation would create a cycle
R_DANGLING = "R_DANGLING"        # INV-6: derivation references a non-existent primitive
R_TEMPORAL = "R_TEMPORAL"        # INV-7 / 13.1: temporal-coherence failure
R_UNKNOWN_OP = "R_UNKNOWN_OP"    # 13.4: forward-compat, operation not recognized

VALID_CODES = frozenset({
    R_NO_AGENT, R_NO_SUBJECT, R_MUTATION, R_REOPEN,
    R_CYCLE, R_DANGLING, R_TEMPORAL, R_UNKNOWN_OP,
})
