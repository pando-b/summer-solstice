"""RFC 8785 (JSON Canonicalization Scheme) serialization and hashing."""

import hashlib
import json
import math
import struct

import pytest

from solstice.canonical import CanonicalError, canonical_bytes, canonical_hash


def _from_bits(hex_bits: str) -> float:
    return struct.unpack(">d", bytes.fromhex(hex_bits))[0]


def test_rfc8785_sample_object():
    # RFC 8785 section 3.2.2: whitespace removed, keys sorted, numbers and
    # strings in canonical form.
    src = ('{"numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],'
           ' "string": "\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/",'
           ' "literals": [null, true, false]}')
    expected = ('{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
                '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}')
    assert canonical_bytes(json.loads(src)) == expected.encode("utf-8")


def test_rfc8785_key_ordering_by_utf16_code_units():
    # RFC 8785 section 3.2.3: an astral-plane key (a surrogate pair in UTF-16)
    # sorts before U+FB33, unlike a code-point sort.
    obj = {
        "€": "Euro Sign",
        "\r": "Carriage Return",
        "דּ": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "\U0001f600": "Emoji: Grinning Face",
        "\u0080": "Control",
        "ö": "Latin Small Letter O With Diaeresis",
    }
    keys = [k for k in json.loads(canonical_bytes(obj))]
    assert keys == ["\r", "1", "\u0080", "ö", "€", "\U0001f600", "דּ"]


def test_string_escaping():
    assert canonical_bytes("\b\t\n\f\r\x01\x1f\x7f\"\\/") == b'"\\b\\t\\n\\f\\r\\u0001\\u001f\x7f\\"\\\\/"'
    assert canonical_bytes("é\U0001f600") == '"é\U0001f600"'.encode("utf-8")


@pytest.mark.parametrize("value,expected", [
    (0, "0"), (-0, "0"), (1, "1"), (-1, "-1"), (9007199254740991, "9007199254740991"),
    (-9007199254740991, "-9007199254740991"), (True, "true"), (False, "false"), (None, "null"),
])
def test_integers_and_literals(value, expected):
    assert canonical_bytes(value) == expected.encode()


@pytest.mark.parametrize("bits,expected", [
    # RFC 8785 Appendix B number vectors (IEEE 754 bits -> text).
    ("0000000000000000", "0"),
    ("8000000000000000", "0"),
    ("0000000000000001", "5e-324"),
    ("8000000000000001", "-5e-324"),
    ("7fefffffffffffff", "1.7976931348623157e+308"),
    ("ffefffffffffffff", "-1.7976931348623157e+308"),
    ("4340000000000000", "9007199254740992"),
    ("c340000000000000", "-9007199254740992"),
    ("4430000000000000", "295147905179352830000"),
    ("44b52d02c7e14af5", "9.999999999999997e+22"),
    ("44b52d02c7e14af6", "1e+23"),
    ("44b52d02c7e14af7", "1.0000000000000001e+23"),
    ("444b1ae4d6e2ef4e", "999999999999999700000"),
    ("444b1ae4d6e2ef4f", "999999999999999900000"),
    ("444b1ae4d6e2ef50", "1e+21"),
    ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
    ("3eb0c6f7a0b5ed8d", "0.000001"),
    ("41b3de4355555553", "333333333.3333332"),
    ("41b3de4355555554", "333333333.33333325"),
    ("41b3de4355555555", "333333333.3333333"),
    ("41b3de4355555556", "333333333.3333334"),
    ("41b3de4355555557", "333333333.33333343"),
    ("becbf647612f3696", "-0.0000033333333333333333"),
    ("43143ff3c1cb0959", "1424953923781206.2"),
])
def test_rfc8785_number_vectors(bits, expected):
    assert canonical_bytes(_from_bits(bits)) == expected.encode()


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, {"a": [1, math.nan]}])
def test_nan_and_infinity_are_rejected(bad):
    with pytest.raises(CanonicalError, match="NaN|infinity"):
        canonical_bytes(bad)


def test_integers_beyond_ieee_double_precision_are_rejected():
    with pytest.raises(CanonicalError, match="2\\^53"):
        canonical_bytes(2**53)


@pytest.mark.parametrize("bad", [{1: "x"}, {"a": {1, 2}}, b"bytes", "\ud800"])
def test_non_json_values_are_rejected(bad):
    with pytest.raises(CanonicalError):
        canonical_bytes(bad)


def test_hash_is_sha256_of_the_canonical_bytes_and_ignores_key_order():
    a = {"b": [1, {"y": "z", "x": 2}], "a": "text"}
    b = json.loads('{"a": "text", "b": [1, {"x": 2, "y": "z"}]}')
    assert canonical_hash(a) == canonical_hash(b) == hashlib.sha256(canonical_bytes(a)).hexdigest()
    assert canonical_hash({**a, "a": "texT"}) != canonical_hash(a)
