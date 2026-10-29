"""Command-line interface for docs-anchor-checker."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .checker import scan


def format_report(report, quiet: bool = False) -> str:
    lines = []
    flagged = {}
    for f in report.findings:
        flagged.setdefault(f.file, []).append(f)
    clean = report.files_scanned - len(flagged)
    header = (f"docs-anchor-checker {__version__} — "
              f"scanned {report.files_scanned} markdown file(s) under "
              f"'{report.root or '.'}'")
    lines.append(header)
    lines.append("")

    for fname in sorted(flagged):
        fs = flagged[fname]
        lines.append(f"{fname}: {len(fs)} issue(s)")
        for f in fs:
            where = f"line {f.line}" if f.line else "site-wide"
            lines.append(f"  {where:12} {f.code:18} {f.message}")
        lines.append("")

    if clean and not quiet:
        lines.append(f"{clean} file(s) clean.")
        lines.append("")

    counts = report.codes()
    summary = "Summary: " + str(report.issue_count) + " issue(s)"
    listened = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    lines.append(summary + (" (" + listened + ")" if listened else " — all clear"))
    lines.append("")

    fixes = [f for f in report.findings if f.suggestion]
    if fixes:
        lines.append("Suggested fixes")
        lines.append("---------------")
        for f in fixes:
            where = f"{f.file}:{f.line}" if f.line else f"{f.file}"
            lines.append(f"  - {where}: {f.suggestion}")
        lines.append("")
    lines.append("Result: "
                 + ("FAIL — fix issues before publishing" if report.findings
                    else "PASS — no issues found"))
    return "\n".join(lines)


def format_json(report) -> str:
    return json.dumps({
        "root": report.root,
        "files_scanned": report.files_scanned,
        "issue_count": report.issue_count,
        "codes": report.codes(),
        "findings": [f.__dict__ for f in report.findings],
    }, indent=2)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="docs-anchor-checker",
        description="Lint a markdown docs site before publishing: broken internal "
                    "anchors and links, missing image alt text, duplicate headings, "
                    "inconsistent front matter, heading-level skips, orphan pages.",
        epilog="Suggested fixes appear at the bottom of the report. "
               "Exit code 1 when issues were found, 0 otherwise.")
    p.add_argument("root", nargs="?", default=".",
                   help="root directory of the markdown site (default: current directory)")
    p.add_argument("--exclude", action="append", default=[],
                   metavar="DIR", help="skip a subdirectory (relative to root; repeatable)")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="print findings as JSON instead of the human report")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--quiet", "-q", action="store_true", dest="quiet",
                   help="omit the 'clean files' note from the report")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = os.path.abspath(args.root or ".")
    if not os.path.isdir(root):
        print(f"error: root directory not found: {root}", file=sys.stderr)
        return 2
    report = scan(root, exclude=tuple(args.exclude or []))
    if args.as_json:
        print(format_json(report))
    else:
        print(format_report(report, quiet=args.quiet))
    return 1 if report.findings else 0
