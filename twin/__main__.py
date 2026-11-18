"""Agent twin command line.

    python3 -m twin serve [--port 8787] [--copilot-match qe-as-a-service | --all-copilot]
    python3 -m twin event <agent> <dispatched|working|waiting|done|failed|idle> [message]
    python3 -m twin snapshot            # print the current state as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from twin import sources


def _cmd_serve(args: argparse.Namespace) -> int:
    from twin.server import serve

    match = None if args.all_copilot else args.copilot_match
    httpd = serve(args.host, args.port, copilot_dir=Path(args.copilot_dir).expanduser(),
                  copilot_match=match, copilot_limit=args.copilot_limit)
    scope = "all repos" if match is None else f"matching '{match}'"
    print(f"QEaaS agent twin → http://{args.host}:{args.port}  (Copilot sessions: {scope})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def _cmd_event(args: argparse.Namespace) -> int:
    entry = sources.record_activity(args.agent, args.status, args.message, source=args.source)
    print(json.dumps(entry))
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    match = None if args.all_copilot else args.copilot_match
    print(json.dumps(sources.snapshot(copilot_match=match, hours=args.hours), indent=2))
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m twin", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def copilot_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--copilot-match", default="qe-as-a-service",
                       help="only show Copilot sessions whose repo/cwd/name contains this (default: qe-as-a-service)")
        p.add_argument("--all-copilot", action="store_true", help="show Copilot sessions from every repo")

    p = sub.add_parser("serve", help="run the twin web UI")
    p.add_argument("--host", default="127.0.0.1", help="bind address (default: localhost only)")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--copilot-dir", default=str(sources.COPILOT_STATE_DIR))
    p.add_argument("--copilot-limit", type=int, default=12, help="max Copilot studios (default 12)")
    copilot_flags(p)
    p.set_defaults(func=_cmd_serve)

    p = sub.add_parser("event", help="record QE agent activity in the twin journal")
    p.add_argument("agent", help="agent name, e.g. planning-agent")
    p.add_argument("status", choices=sorted(sources.JOURNAL_STATUSES))
    p.add_argument("message", nargs="?", default="")
    p.add_argument("--source", default="agent")
    p.set_defaults(func=_cmd_event)

    p = sub.add_parser("snapshot", help="print the twin state as JSON")
    p.add_argument("--hours", type=int, default=24)
    copilot_flags(p)
    p.set_defaults(func=_cmd_snapshot)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
