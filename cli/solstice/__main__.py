"""`solstice` command-line entry point.

Commands register through COMMANDS: each entry maps a name to
(help text, configure(parser), run(args) -> exit code).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from solstice import __version__
from solstice.workspace import WorkspaceError, resolve_workspace


def _run_workspace(args: argparse.Namespace) -> int:
    print(resolve_workspace())
    return 0


Command = tuple[str, Callable[[argparse.ArgumentParser], None], Callable[[argparse.Namespace], int]]

COMMANDS: dict[str, Command] = {
    "workspace": ("print the resolved workspace path", lambda p: None, _run_workspace),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solstice")
    parser.add_argument("--version", action="version", version=f"solstice {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, configure, run) in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        configure(p)
        p.set_defaults(_run=run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args._run(args)
    except WorkspaceError as exc:
        print(f"solstice: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
