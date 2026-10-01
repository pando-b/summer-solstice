"""RFC 8785 JSON Canonicalization Scheme (JCS) and its SHA-256, stdlib only.

Approval hashes are computed over these bytes (KTD8), so the same content
always yields the same hash whatever the key order or whitespace.

- Objects: members sorted by the UTF-16 code units of their keys, no whitespace.
- Strings: only `"`, `\\`, and control characters below U+0020 are escaped
  (\\b \\t \\n \\f \\r short forms, others as lowercase \\u00xx); everything else
  is emitted as UTF-8.
- Numbers: the ECMAScript Number-to-string form. Python's `repr` gives the
  shortest round-trip digits; they are laid out by the ECMAScript rules.

Refused, because I-JSON cannot carry them exactly: NaN and infinity, integers
outside the IEEE 754 double's exact range (|n| > 2^53 - 1), lone surrogates,
non-string keys, and non-JSON types.
"""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal

from solstice.errors import SolsticeError

MAX_SAFE_INTEGER = 2**53 - 1

_SHORT_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\t": "\\t", "\n": "\\n",
                  "\f": "\\f", "\r": "\\r"}


class CanonicalError(SolsticeError):
    """A value has no RFC 8785 canonical form."""

    kind = "invalid_record"


def canonical_bytes(value) -> bytes:
    parts: list[str] = []
    _emit(value, parts)
    try:
        return "".join(parts).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonicalError("string holds a lone surrogate; it is not valid I-JSON") from exc


def canonical_hash(value) -> str:
    """Lowercase hex SHA-256 of the canonical bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _emit(value, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError(f"integer {value} is beyond 2^53 - 1 and cannot be represented "
                                 f"exactly; store it as a string")
        out.append(str(value))
    elif isinstance(value, float):
        out.append(_number(value))
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _emit(item, out)
        out.append("]")
    elif isinstance(value, dict):
        for k in value:
            if not isinstance(k, str):
                raise CanonicalError(f"object key {k!r} is not a string")
        out.append("{")
        for i, k in enumerate(sorted(value, key=_utf16_key)):
            if i:
                out.append(",")
            out.append(_string(k))
            out.append(":")
            _emit(value[k], out)
        out.append("}")
    else:
        raise CanonicalError(f"{type(value).__name__} is not a JSON value")


def _utf16_key(key: str) -> bytes:
    try:
        return key.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise CanonicalError("object key holds a lone surrogate; it is not valid I-JSON") from exc


def _string(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[ch])
        elif ch < " ":
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _number(x: float) -> str:
    if math.isnan(x) or math.isinf(x):
        raise CanonicalError("NaN and infinity have no JSON form; refused")
    if x == 0:
        return "0"  # also -0
    sign = "-" if x < 0 else ""
    _, digits_t, exp = Decimal(repr(abs(x))).as_tuple()
    digits = "".join(map(str, digits_t)).rstrip("0")
    exp += len(digits_t) - len(digits)  # account for stripped trailing zeros
    digits = digits.lstrip("0") or "0"
    k = len(digits)
    n = exp + k  # value = 0.digits x 10^n  (ECMAScript's k and n)
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mant = digits if k == 1 else digits[0] + "." + digits[1:]
        body = f"{mant}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body
