"""`solstice` command-line entry point.

Commands register through COMMANDS: each entry maps a name to
(help text, configure(parser), run(args) -> exit code).

Record commands read JSON (a file path or `-` for stdin) and print JSON.

Every failure that reaches `main` prints one JSON envelope to stderr and
nothing to stdout (see `solstice.errors`)::

    {"error": {"kind": "...", "message": "...", "details": {...}}}

Exit codes:

- 0  ok
- 1  invalid record, missing record, corrupt history, or refused transition
     (doctor: a missing-required item; leakscan: findings, push blocked)
- 2  workspace error (leakscan: the scan could not run, so it fails closed)
- 3  workspace lock held by another writer
- 64 usage error: unknown command, bad argument (`kind: usage`)
- 70 unexpected internal failure (`kind: internal`, no traceback)

`doctor` and `leakscan` print human reports; only their unexpected failures
use the envelope.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from solstice import __version__, doctor, init, leakscan
from solstice.errors import EX_SOFTWARE, EX_USAGE, SolsticeError, emit
from solstice.lifecycle import INITIAL
from solstice.state import ENTITIES, RecordError, Store, load_schema
from solstice.workspace import WorkspaceError, resolve_workspace


def _out(data) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _read_json(source: str):
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text()
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
    t.add_argument("entity", choices=list(INITIAL))
    t.add_argument("id")
    t.add_argument("status")
    t.add_argument("--file", help="JSON fields to set with the move (e.g. channel_live_at, reason)")

    h = sub.add_parser("events", help="print a record's history as a JSON array")
    h.add_argument("entity", **entity)
    h.add_argument("id")

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
    elif a == "events":
        store.get(args.entity, args.id)
        _out(store.events(args.entity, args.id))
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


def _conf_init(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", help="new or empty directory for the private workspace")
    p.add_argument("--plugin-checkout", metavar="DIR",
                   help="also arm the pre-push hook in this plugin checkout")


def _run_init(args: argparse.Namespace) -> int:
    ws, created = init.init_workspace(args.path)
    result = {"workspace": str(ws), "created": created}
    if args.plugin_checkout:
        result["hooks"] = init.install_hooks(args.plugin_checkout, workspace=ws)
    _out(result)
    return 0


def _conf_hooks(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="action", required=True)
    i = sub.add_parser("install", help="set core.hooksPath=.githooks in a plugin checkout")
    i.add_argument("checkout", nargs="?", default=".", help="plugin checkout (default: cwd)")
    i.add_argument("--workspace", help="workspace whose denylist the hook reads "
                                       "(stored as git config solstice.workspace)")


def _run_hooks(args: argparse.Namespace) -> int:
    _out(init.install_hooks(args.checkout, workspace=args.workspace))
    return 0


def _conf_doctor(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--plugin-root", help="plugin directory holding .claude-plugin/plugin.json")


def _run_doctor(args: argparse.Namespace) -> int:
    probes = doctor.Probes()
    probes.plugin_root = doctor.find_plugin_root(args.plugin_root, probes.env, probes.cwd)
    report = doctor.run_checks(probes)
    doctor.print_report(report, as_json=args.json)
    return 0 if report["ok"] else 1


def _conf_leakscan(p: argparse.ArgumentParser) -> None:
    sub = p.add_subparsers(dest="action", required=True)
    t = sub.add_parser("tree", help="structural and secret-pattern check over a tree (CI)")
    t.add_argument("root", nargs="?", default=".")
    pp = sub.add_parser("pre-push", help="scan the pushed commit range; reads git's pre-push stdin")
    pp.add_argument("remote", nargs="?")
    pp.add_argument("url", nargs="?")
    c = sub.add_parser("commits", help="secret-pattern scan of commit messages in a range (CI)")
    c.add_argument("range", help="<base>..<head>; a zero or unknown base scans all of head's history")


def _report_findings(findings, header: str) -> None:
    print(header, file=sys.stderr)
    for f in findings:
        print(f"  {f}", file=sys.stderr)


def _run_leakscan(args: argparse.Namespace) -> int:
    if args.action == "tree":
        try:
            findings = leakscan.scan_tree(args.root)
        except leakscan.LeakscanError as exc:
            print(f"solstice leakscan: {exc}", file=sys.stderr)
            return 2
        if findings:
            _report_findings(findings, f"leakscan: {len(findings)} finding(s):")
            return 1
        print("leakscan: tree clean")
        return 0

    if args.action == "commits":
        try:
            findings = leakscan.scan_commit_messages(Path.cwd(), args.range)
        except leakscan.LeakscanError as exc:
            print(f"solstice leakscan: {exc}", file=sys.stderr)
            return 2
        if findings:
            _report_findings(findings, f"leakscan: {len(findings)} finding(s) in commit messages:")
            return 1
        print("leakscan: commit messages clean")
        return 0

    blocked = "solstice leakscan: push BLOCKED"
    try:
        ws = resolve_workspace()
        terms = leakscan.load_terms(ws)
        findings = leakscan.scan_push(Path.cwd(), sys.stdin.read().splitlines(), terms,
                                      remote=args.remote)
    except (WorkspaceError, leakscan.LeakscanError) as exc:
        print(f"{blocked} (fail closed): {exc}", file=sys.stderr)
        return 2
    if findings:
        _report_findings(findings, f"{blocked}: {len(findings)} finding(s):")
        return 1
    return 0


Command = tuple[str, Callable[[argparse.ArgumentParser], None], Callable[[argparse.Namespace], int]]

COMMANDS: dict[str, Command] = {
    "workspace": ("print the resolved workspace path", lambda p: None, _run_workspace),
    "schema": ("print the JSON Schema for a record entity", _conf_schema, _run_schema),
    "record": ("create, read, list, update, transition, or add events to records",
               _conf_record, _run_record),
    "validate": ("validate every record in the workspace", lambda p: None, _run_validate),
    "migrate": ("upgrade records written by an older CLI", lambda p: None, _run_migrate),
    "init": ("scaffold a private workspace at a new or empty path", _conf_init, _run_init),
    "hooks": ("arm the leak-guard pre-push hook in a plugin checkout", _conf_hooks, _run_hooks),
    "doctor": ("report setup health: ok, missing-optional, missing-required",
               _conf_doctor, _run_doctor),
    "leakscan": ("leak guard: structural tree check, pre-push range scan, or message scan",
                 _conf_leakscan, _run_leakscan),
}


class _Parser(argparse.ArgumentParser):
    """Usage errors print the `usage` envelope and exit EX_USAGE (64), so a
    typo is distinguishable from a workspace failure. Subparsers inherit it."""

    def error(self, message: str):
        emit("usage", f"{self.prog}: {message}", {"usage": self.format_usage().strip()})
        self.exit(EX_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="solstice")
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
    except SolsticeError as exc:
        emit(exc.kind, exc.message, exc.details)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001  (the contract: never a traceback)
        emit("internal", f"unexpected {type(exc).__name__}: {exc}", {"type": type(exc).__name__})
        return EX_SOFTWARE


if __name__ == "__main__":
    sys.exit(main())
