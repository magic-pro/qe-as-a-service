"""Agent twin command line.

    python3 -m twin serve [--port 8787]
    python3 -m twin copilot enable
    python3 -m twin run <agent> "<prompt>"
    python3 -m twin snapshot
"""

from __future__ import annotations

import argparse
import json
import sys
import sqlite3

from twin import activity, qe_run, sources


def _cmd_serve(args: argparse.Namespace) -> int:
    from twin.server import serve

    httpd = serve(port=args.port)
    print(f"QEaaS agent twin → http://127.0.0.1:{httpd.server_port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def _cmd_copilot(args: argparse.Namespace) -> int:
    scoped = activity.scope(sources.REPO_ROOT)
    if not scoped:
        sys.exit("Run this command from a clone of magic-pro/qe-as-a-service with its GitHub origin.")
    activity.enable_copilot(scoped[0], args.action == "enable")
    print(f"Copilot capture {'enabled' if args.action == 'enable' else 'disabled'} for this local clone.")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    command = ["claude", "--agent", args.agent, "-p", args.prompt]
    if args.read_only:
        command.extend(["--tools", "", "--strict-mcp-config"])
    result = qe_run.launch(args.agent, "qe-manual", command, cwd=sources.REPO_ROOT)
    assert result is not None
    return result


def _cmd_snapshot(args: argparse.Namespace) -> int:
    print(json.dumps(sources.snapshot(hours=max(1, min(args.hours, 168))), indent=2))
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m twin", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("serve", help="run the twin web UI")
    p.add_argument("--port", type=int, default=8787)
    p.set_defaults(func=_cmd_serve)

    p = sub.add_parser("copilot", help="opt this local clone in or out of Copilot capture")
    p.add_argument("action", choices=("enable", "disable"))
    p.set_defaults(func=_cmd_copilot)

    p = sub.add_parser("run", help="observe a local QE agent run via Claude Code")
    p.add_argument("agent", choices=sorted(path.stem for path in
                                           (sources.REPO_ROOT / ".claude/agents").glob("*.md")))
    p.add_argument("prompt")
    p.add_argument("--read-only", action="store_true", help="disable Claude Code tools and MCP servers")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("snapshot", help="print the twin state as JSON")
    p.add_argument("--hours", type=int, default=24)
    p.set_defaults(func=_cmd_snapshot)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, sqlite3.Error) as exc:
        parser.exit(1, f"QE Twin: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
