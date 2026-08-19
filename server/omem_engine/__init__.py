"""OMEM v1.0 reference implementation — the executable definition of the standard."""

from .engine import Engine, ACCEPTED
from .proposition import BELIEVED_TRUE, BELIEVED_FALSE, CONTRADICTED, UNKNOWN
from .reasons import (
    Rejected, R_NO_AGENT, R_NO_SUBJECT, R_MUTATION, R_REOPEN, R_CYCLE,
    R_DANGLING, R_TEMPORAL, R_UNKNOWN_OP,
)
from .canon import RETRACTED

__all__ = [
    "Engine", "ACCEPTED",
    "BELIEVED_TRUE", "BELIEVED_FALSE", "CONTRADICTED", "UNKNOWN",
    "Rejected", "R_NO_AGENT", "R_NO_SUBJECT", "R_MUTATION", "R_REOPEN",
    "R_CYCLE", "R_DANGLING", "R_TEMPORAL", "R_UNKNOWN_OP", "RETRACTED",
]
__version__ = "1.0.0"
