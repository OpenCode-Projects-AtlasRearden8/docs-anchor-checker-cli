"""pytest suite for docs-anchor-checker against seeded good/bad doc trees."""

from __future__ import annotations

import io
import json
import sys
import textwrap
from pathlib import Path

from docs_anchor_checker import checker
from docs_anchor_checker.cli import format_report, main

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOOD = FIXTURES / "good"
BAD = FIXTURES / "bad"


def codes(findings):
    return {f.code for f in findings}


# --- good tree ------------------------------------------------------------


def test_good_tree_is_clean():
    report = checker.scan(str(GOOD))
    assert report.findings == [], [f.__dict__ for f in report.findings]
    assert report.issue_count == 0
    assert report.files_scanned == 5


def test_good_tree_finds_fake_links_in_code_fence():
    report = checker.scan(str(GOOD))
    assert "does-not-exist" not in format_report(report)


# --- bad tree: one test per check ------------------------------------------

def _bad_report():
    return checker.scan(str(BAD))


def test_bad_tree_flags_all_seven_checks():
    report = _bad_report()
    expected = {"BROKEN_LINK", "BROKEN_ANCHOR", "MISSING_ALT",
                "DUPLICATE_HEADING", "HEADING_SKIP", "FRONT_MATTER", "ORPHAN"}
    assert codes(report.findings) == expected


def test_bad_tree_counts():
    report = _bad_report()
    assert report.files_scanned == 3
    assert report.issue_count == 10


def test_broken_link_findings():
    report = _bad_report()
    links = [(f.file, f.line, f.message) for f in report.findings
             if f.code == "BROKEN_LINK"]
    assert any(f[0] == "index.md" and f[1] == 10 and "missing-page.md" in f[2]
               for f in links)
    assert any(f[0] == "index.md" and f[1] == 14 for f in links)
    assert any(f[0] == "guide.md" and f[1] == 17 for f in links)


def test_broken_anchor_findings():
    report = _bad_report()
    anchors = [(f.file, f.line) for f in report.findings if f.code == "BROKEN_ANCHOR"]
    assert ("index.md", 11) in anchors
    assert ("guide.md", 18) in anchors


def test_missing_alt_findings():
    report = _bad_report()
    alts = [(f.file, f.line) for f in report.findings if f.code == "MISSING_ALT"]
    assert ("index.md", 14) in alts


def test_duplicate_heading_findings():
    report = _bad_report()
    dupes = [(f.file, f.line, f.message) for f in report.findings
             if f.code == "DUPLICATE_HEADING"]
    assert ("guide.md", 13) in [d[0:2] for d in dupes]
    assert any("Packaging" in f[2] for f in dupes)


def test_heading_skip_findings():
    report = _bad_report()
    skips = [(f.file, f.line) for f in report.findings if f.code == "HEADING_SKIP"]
    assert ("guide.md", 9) in skips


def test_front_matter_inconsistency():
    report = _bad_report()
    fm = [f for f in report.findings if f.code == "FRONT_MATTER"]
    assert len(fm) == 1
    assert fm[0].file == "guide.md"
    assert "description" in fm[0].message


def test_orphan_page():
    report = _bad_report()
    orphans = [(f.file, f.line) for f in report.findings if f.code == "ORPHAN"]
    assert orphans == [("lonely.md", 0)]


def test_code_fence_in_bad_tree_is_ignored():
    report = _bad_report()
    text = format_report(report)
    assert "cloaked" not in text
    assert "Secret dupe" not in text


# --- unit-level behaviours -------------------------------------------------


def test_github_slug():
    assert checker.github_slug("Hello, World!") == "hello-world"
    assert checker.github_slug("FAQ: Setup & Care") == "faq-setup-care"
    assert checker.github_slug("Install **v2**") == "install-v2"


def test_strip_front_matter():
    text = "---\ntitle: x\n---\n\n# Head"
    assert checker.strip_front_matter(text) == "\n\n\n\n# Head"
    assert checker.parse_front_matter(text) == {"title": "x"}


def test_front_matter_line_numbers_align():
    text = "---\ntitle: x\n---\n\n# Head\n\nBroken? [x](./nope.md)\n"
    out = []
    checker.check_file("f.md", text, out, set(), str(FIXTURES),
                       {"f.md": {checker.github_slug("Head").lower(): "Head"}})
    assert isinstance(out[0].line, int)
    pre = text.split("./nope.md")[0].count("\n")
    assert out[0].line == pre + 1


def test_classify_target():
    assert checker.classify_target("#anchor") == "internal"
    assert checker.classify_target("./a.md#x") == "internal"
    assert checker.classify_target("a.md") == "internal"
    assert checker.classify_target("https://x.com") == "external"
    assert checker.classify_target("image.png") == "external"
    assert checker.classify_target("bare.txt") == "skip"
    assert checker.classify_target("/root-ish.md") == "skip"


def test_front_matter_missing_stats_long_text():
    body = textwrap.dedent("x" * 10)
    assert body == "xxxxxxxxxx"


# --- report formatting / CLI -----------------------------------------------


def test_report_has_suggested_fixes_section():
    report = _bad_report()
    text = format_report(report)
    assert "Suggested fixes" in text
    assert text.strip().startswith("docs-anchor-checker")
    assert text.rstrip().endswith("Result: FAIL — fix issues before publishing")


def test_good_report_passes_and_no_fixes():
    text = format_report(checker.scan(str(GOOD)))
    assert "Suggested fixes" not in text
    assert "Result: PASS — no issues found" in text


def _fix_report(report):
    # help type checkers: findings carry line numbers as ints
    for f in report.findings:
        assert isinstance(f.line, int)
    return report


def test_cli_exit_codes():
    assert main([str(GOOD)]) == 0
    assert main([str(BAD)]) == 1


def test_cli_json_output(capsys):
    rc = main(["--json", str(BAD)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 1
    assert data["issue_count"] == 10
    assert data["files_scanned"] == 3
    assert data["codes"]["ORPHAN"] == 1
    assert all("file" in f and "message" in f for f in data["findings"])


def test_cli_exclude():
    rc = main([str(GOOD), "--exclude", "subdir"])
    assert rc == 0
    report = checker.scan(str(GOOD), exclude=("subdir",))
    assert report.files_scanned == 4
