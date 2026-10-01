"""The machine error contract agents parse.

Every failure that reaches `solstice.__main__.main` prints one JSON object to
stderr::

    {"error": {"kind": "<token>", "message": "<readable text>", "details": {...}}}

`kind` is one of KINDS, a stable snake_case token. `message` is the same text
the exception carries, and `details` holds structured fields for the kind
(for example `from`, `to`, and `allowed` on a refused transition).
"""

from __future__ import annotations

import json
import sys

KINDS = (
    "workspace",
    "lock_held",
    "invalid_record",
    "not_found",
    "transition_refused",
    "corrupt_history",
    "usage",
    "adapter",
    "budget",
    "approval",
    "internal",
)

EX_USAGE = 64  # sysexits.h: the command was used incorrectly
EX_SOFTWARE = 70  # sysexits.h: an internal error, reported as kind `internal`


class SolsticeError(Exception):
    """Base for errors that map to an envelope `kind` and an exit code."""

    kind = "internal"
    exit_code = 1

    def __init__(self, message: str = "", *, kind: str | None = None,
                 details: dict | None = None):
        super().__init__(message)
        if kind is not None:
            if kind not in KINDS:
                raise ValueError(f"unknown error kind {kind!r}")
            self.kind = kind
        self.details = dict(details or {})

    @property
    def message(self) -> str:
        return str(self)


def envelope(kind: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"kind": kind, "message": message, "details": details or {}}}


def emit(kind: str, message: str, details: dict | None = None) -> None:
    print(json.dumps(envelope(kind, message, details), sort_keys=True), file=sys.stderr)


class UsageError(SolsticeError):
    """The command was used incorrectly (exit EX_USAGE, like argparse errors)."""

    kind = "usage"
    exit_code = EX_USAGE
