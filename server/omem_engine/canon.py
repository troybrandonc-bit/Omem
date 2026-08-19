"""OMEM Canonicalization Profile v1.0 — executable form.

This module is the normative canonical-form authority for the reference
implementation. Every comparison or ordering the Model delegates to canonical
form (propositions Model 8.2, identifiers 7.1/9.1/10.1 & ordering 14.6,
reproducibility-marker inputs 16.4) MUST route through here.

Profile sections implemented:
  2  UTF-8 + NFC; identity = byte-equality of canonical form
  3  Proposition canonical form; reserved RETRACTED marker
  4  Identifier canonical form + unsigned-byte lexicographic order;
     U+001E / U+001F forbidden inside identifiers
  5  Reproducibility-marker input serialization (see reproducibility.py)
  6  Numeric canonical form (logical time, confidence)
"""

from __future__ import annotations

import unicodedata

# Profile 4.4 / 5: reserved separators. Forbidden inside identifiers.
UNIT_SEP = "\u001f"     # U+001F, between elements in marker serialization
RECORD_SEP = "\u001e"   # U+001E, between the id-set and the logical time

# Profile 3.3: the single reserved retraction proposition (Model 13.3).
RETRACTED = "RETRACTED"


class CanonError(ValueError):
    """Raised when a value is ill-formed under the profile (Profile 2.3, 4.4)."""


def _nfc(value: str) -> str:
    """Profile 2.1: NFC-normalize. Input is already a Python str (UTF-8 decoded);
    invalid UTF-8 cannot exist here, but bytes inputs are rejected in canon_text."""
    return unicodedata.normalize("NFC", value)


def canon_text(value: str) -> bytes:
    """Profile 2: canonical byte form of an in-scope textual value = NFC UTF-8 bytes.

    Profile 2.3: reject values that are not valid text. We accept only `str`;
    a bytes value that is not valid UTF-8 raises (mirrors 'reject ill-formed UTF-8').
    """
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonError("ill-formed UTF-8") from exc
    if not isinstance(value, str):
        raise CanonError(f"non-textual value: {type(value)!r}")
    return _nfc(value).encode("utf-8")


def canon_proposition(prop: str) -> bytes:
    """Profile 3.1: proposition canonical form = NFC UTF-8 bytes."""
    return canon_text(prop)


def proposition_identical(a: str, b: str) -> bool:
    """Profile 3.1: proposition identity is byte-equality of canonical forms."""
    return canon_proposition(a) == canon_proposition(b)


def canon_identifier(idstr: str) -> bytes:
    """Profile 4.1: identifier canonical form = NFC UTF-8 bytes.

    Profile 4.4: reject identifiers whose canonical form contains the reserved
    separators U+001E / U+001F.
    """
    b = canon_text(idstr)
    if b"\x1e" in b or b"\x1f" in b:
        raise CanonError("identifier contains reserved separator U+001E/U+001F")
    return b


def identifier_order_key(idstr: str) -> bytes:
    """Profile 4.2: ordering key = the canonical bytes, compared as unsigned 8-bit.

    Python's bytes comparison is already unsigned-lexicographic with proper-prefix
    ordering first, which is exactly Profile 4.2.
    """
    return canon_identifier(idstr)


def canon_logical_time(t: int) -> str:
    """Profile 6.1: logical time canonical form = shortest decimal ASCII, no leading
    zeros ('0' for zero)."""
    if not isinstance(t, int) or isinstance(t, bool):
        raise CanonError("logical time must be a non-negative integer")
    if t < 0:
        raise CanonError("logical time must be non-negative")
    return str(t)  # Python str(int) is already the shortest no-leading-zero form


def canon_confidence(c: float) -> str:
    """Profile 6.2: confidence in [0,1]; single leading '0' when <1, '1' for one,
    '0' for zero, no trailing zeros after the point. Reject outside [0,1] (Model 8.5).
    """
    if isinstance(c, bool) or not isinstance(c, (int, float)):
        raise CanonError("confidence must be a real number")
    if c < 0.0 or c > 1.0:
        raise CanonError("confidence outside [0,1]")
    if c == 0.0:
        return "0"
    if c == 1.0:
        return "1"
    # Render without trailing zeros, single leading zero before the point.
    # Use repr-free formatting: format with enough precision then strip.
    s = f"{c:.12f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    # f-string on a value in (0,1) already yields '0.xxxx'
    return s
