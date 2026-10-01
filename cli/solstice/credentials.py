"""The one place the plugin reads keys (KTD17, R26).

Keys come from the process environment only: no files, no workspace config
values, no defaults, no shared fallback. A missing key makes its adapter
unavailable before any network call. Every value read here is remembered so
`redact` can strip it (and URL `token`/`key` parameters) from error text
before that text is stored or printed.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

_LOADED: set[str] = set()
_URL_SECRET = re.compile(
    r"(?i)([?&](?:[a-z_]*token|[a-z_]*key|password|secret)=)[^&#\s]+")
REDACTED = "[redacted]"


class MissingKey(Exception):
    def __init__(self, names: list[str]):
        self.names = list(names)
        super().__init__("missing key " + ", ".join(self.names))


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def missing(names: Iterable[str], env: Mapping[str, str] | None = None) -> list[str]:
    """Key names that are unset or blank. Values are never returned."""
    source = _env(env)
    return [n for n in names if not (source.get(n) or "").strip()]


def load(names: Iterable[str], env: Mapping[str, str] | None = None) -> dict[str, str]:
    names = list(names)
    gone = missing(names, env)
    if gone:
        raise MissingKey(gone)
    source = _env(env)
    values = {n: source[n].strip() for n in names}
    for v in values.values():
        register_secret(v)
    return values


def register_secret(value: str) -> None:
    """Remember a derived secret (e.g. an encoded Basic credential) for redaction."""
    if value and len(value) >= 4:
        _LOADED.add(value)


def redact(text: str) -> str:
    for value in sorted(_LOADED, key=len, reverse=True):
        text = text.replace(value, REDACTED)
    return _URL_SECRET.sub(lambda m: m.group(1) + REDACTED, text)
