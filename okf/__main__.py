"""OKF command line.

    python3 -m okf normalize --source jira   <raw.json> --out <dir>
    python3 -m okf normalize --source github <raw.json> --event workflow_run [--log gotest.txt] --out <dir>
    python3 -m okf normalize --source gcp    <raw.json> --out <dir>
    python3 -m okf validate  <dir> [--strict]
    python3 -m okf expect    <expected.yaml> <workspace>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from okf import expect, validate
from okf.normalize import normalize


def _cmd_normalize(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.raw).read_text())
    kwargs = {"event": args.event, "base_url": args.base_url}
    if args.log:
        kwargs["log"] = Path(args.log).read_text()
    doc = normalize(args.source, payload, **kwargs)
    print(doc.write(args.out))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    target = Path(args.root).resolve()
    if target.is_file():
        issues = validate.validate_doc(target, target.parent)
    else:
        issues = validate.validate(target)
    for i in issues:
        print(i)
    errors = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warn"]
    print(f"okf validate: {len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if errors or (args.strict and warns) else 0


def _cmd_expect(args: argparse.Namespace) -> int:
    failed = 0
    for label, ok, detail in expect.check(args.expected, args.workspace):
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"okf expect: {'PASS' if not failed else f'FAIL ({failed})'}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="okf")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("normalize", help="raw signal payload -> OKF signal doc")
    n.add_argument("raw")
    n.add_argument("--source", required=True, choices=["jira", "github", "gcp"])
    n.add_argument("--event", default="workflow_run", help="GitHub event name")
    n.add_argument("--log", help="CI log file to excerpt (GitHub)")
    n.add_argument("--base-url", default="", help="Jira site URL for resource links")
    n.add_argument("--out", required=True)
    n.set_defaults(func=_cmd_normalize)

    v = sub.add_parser("validate", help="lint an OKF bundle (dir) or a single doc (file)")
    v.add_argument("root")
    v.add_argument("--strict", action="store_true", help="treat warnings as errors")
    v.set_defaults(func=_cmd_validate)

    e = sub.add_parser("expect", help="assert agent output against expected.yaml")
    e.add_argument("expected")
    e.add_argument("workspace")
    e.set_defaults(func=_cmd_expect)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
