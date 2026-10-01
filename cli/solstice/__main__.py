"""`solstice` command-line entry point.

Commands register through COMMANDS: each entry maps a name to
(help text, configure(parser), run(args) -> exit code).

Record commands read JSON (a file path or `-` for stdin) and print JSON.
Exit codes: 0 ok, 1 invalid record or refused transition, 2 workspace
error, 3 workspace lock held by another writer.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence

from solstice import __version__
from solstice.lifecycle import TransitionError
from solstice.state import ENTITIES, LockError, RecordError, Store, load_schema
from solstice.workspace import WorkspaceError, resolve_workspace


def _out(data) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _read_json(source: str):
    try:
        text = sys.stdin.read() if source == "-" else open(source).read()
        return json.loads(text)
    except OSError as exc:
        raise RecordError(f"cannot read {source}: {exc}") from exc
    except ValueError as exc:
        raise RecordError(f"{source}: not valid JSON ({exc})") from exc


def _store() -> Store:
    return Store(resolve_workspace())


def _run_workspace(args: argparse.Namespace) -> int:
    print(resolve_workspace())
    return 0


def _conf_schema(p: argparse.ArgumentParser) -> None:
    p.add_argument("entity", choices=list(ENTITIES))


def _run_schema(args: argparse.Namespace) -> int:
    _out(load_schema(args.entity))
    return 0


def _conf_record(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="action", required=True)
    entity = {"choices": list(ENTITIES)}

    c = sub.add_parser("create", help="create a record from a JSON body")
    c.add_argument("entity", **entity)
    c.add_argument("--file", required=True, help="JSON file, or - for stdin")

    g = sub.add_parser("get", help="print one record")
    g.add_argument("entity", **entity)
    g.add_argument("id")

    ls = sub.add_parser("list", help="print records as a JSON array")
    ls.add_argument("entity", **entity)
    ls.add_argument("--status")

    u = sub.add_parser("update", help="merge a JSON patch into a record (not status)")
    u.add_argument("entity", **entity)
    u.add_argument("id")
    u.add_argument("--file", required=True, help="JSON patch file, or - for stdin")

    t = sub.add_parser("transition", help="change status through the lifecycle rules")
    t.add_argument("entity", choices=["problem", "product", "approval"])
    t.add_argument("id")
    t.add_argument("status")
    t.add_argument("--file", help="JSON fields to set with the move (e.g. channel_live_at, reason)")

    e = sub.add_parser("event", help="append an event (e.g. buy_signal) to a record's history")
    e.add_argument("entity", **entity)
    e.add_argument("id")
    e.add_argument("--file", required=True, help="JSON event file, or - for stdin")

    r = sub.add_parser("refetch-failed", help="count a failed refetch for a pending_evidence problem")
    r.add_argument("id")
    r.add_argument("--error", required=True)


def _run_record(args: argparse.Namespace) -> int:
    store = _store()
    a = args.action
    if a == "create":
        _out(store.create(args.entity, _read_json(args.file)))
    elif a == "get":
        _out(store.get(args.entity, args.id))
    elif a == "list":
        _out(store.list(args.entity, status=args.status))
    elif a == "update":
        _out(store.update(args.entity, args.id, _read_json(args.file)))
    elif a == "transition":
        fields = _read_json(args.file) if args.file else None
        _out(store.transition(args.entity, args.id, args.status, fields))
    elif a == "event":
        _out(store.add_event(args.entity, args.id, _read_json(args.file)))
    elif a == "refetch-failed":
        _out(store.record_refetch_failure(args.id, args.error))
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    checked, errors = _store().validate_all()
    _out({"ok": not errors, "checked": checked, "errors": errors})
    return 1 if errors else 0


def _run_migrate(args: argparse.Namespace) -> int:
    migrated, errors = _store().migrate()
    _out({"ok": not errors, "migrated": migrated, "errors": errors})
    return 1 if errors else 0


Command = tuple[str, Callable[[argparse.ArgumentParser], None], Callable[[argparse.Namespace], int]]

COMMANDS: dict[str, Command] = {
    "workspace": ("print the resolved workspace path", lambda p: None, _run_workspace),
    "schema": ("print the JSON Schema for a record entity", _conf_schema, _run_schema),
    "record": ("create, read, list, update, transition, or add events to records",
               _conf_record, _run_record),
    "validate": ("validate every record in the workspace", lambda p: None, _run_validate),
    "migrate": ("upgrade records written by an older CLI", lambda p: None, _run_migrate),
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
    except LockError as exc:
        print(f"solstice: {exc}", file=sys.stderr)
        return 3
    except (RecordError, TransitionError) as exc:
        print(f"solstice: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
