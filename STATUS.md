# STATUS.md — docs-anchor-checker

**Built:** October 29, 2026 by a task run for Asdale Dynamics, LLC
**Version:** 1.0.0 · **License:** MIT (see `LICENSE`, Copyright (c) 2026 Asdale Dynamics, LLC)

## What was built

A standard-library-only Python CLI that lints a markdown docs site before
publishing. Package: `docs_anchor_checker/` (`checker.py` — all lint logic;
`cli.py` — argparse CLI, human report + `--json`; `__main__.py` — `python -m`
entry point). Console script `docs-anchor-checker` is registered via
`pyproject.toml`.

Checks implemented (all seven, each with a plain-English suggested fix):

1. `BROKEN_LINK` — relative `.md` links and local `images/*` paths that do
   not resolve to an existing file.
2. `BROKEN_ANCHOR` — `#heading` links (same page or cross-page) whose target
   heading is missing, validated against GitHub-style slugs with a
   "closest heading" hint.
3. `MISSING_ALT` — images with empty alt text.
4. `DUPLICATE_HEADING` — headings in one file producing the same anchor slug.
5. `HEADING_SKIP` — outline jumps (e.g. h1 straight to h3).
6. `FRONT_MATTER` — fields that the site's other front-matter'd pages share
   but a given page lacks (majority vote, needs ≥2 pages with front matter).
7. `ORPHAN` — pages no other markdown file links to (index/README exempt).

Report shape: per-file findings with line numbers (site-wide findings show
`site-wide`), a summary with per-code counts, then a **Suggested fixes**
section at the bottom, then `Result: PASS/FAIL`. Exit codes: 0 = clean,
1 = issues, 2 = usage error. Code fences and front matter are excluded from
scanning; external URLs and ambiguous bare targets are intentionally skipped.

## How to run it

```bash
python3 -m docs_anchor_checker                 # lint current directory
python3 -m docs_anchor_checker ./site          # lint a docs tree
python3 -m docs_anchor_checker ./site --exclude drafts --json
# or, after `python3 -m pip install .`:
docs-anchor-checker ./site
```

## Verification results

- `python3 -m pytest` → **22 passed** in 0.03s.
  Tests cover the seeded `tests/fixtures/good/` tree (expects zero issues,
  proves code fences are skipped), the seeded `tests/fixtures/bad/` tree
  (expects exactly 10 findings touching all seven codes, with exact line
  numbers), slug/front-matter/classifier unit tests, the Suggested-fixes
  section, CLI exit codes, `--json` output shape, and `--exclude`.
- `pip install` into a clean venv verified: `docs-anchor-checker --version`
  → 1.0.0; installed console script reproduces both fixture reports
  (good → exit 0 PASS, bad → exit 1 FAIL with 10 findings).
- `py_compile` on all modules: clean.
- No secrets, API keys, or personal data in any file.

## Known gaps

- Reference-style link definitions (`[label]: ./x.md`) are counted for the
  orphan check only; their file/anchor targets are not validated.
- Only flat front-matter fields are parsed (not nested YAML), and no YAML
  syntax errors are reported.
- Hard-coded HTML anchor sites (`<a id="...">`) and explicit `{#ids}` after
  headings are not recognised as anchor targets.
- Web-content-only image targets (e.g. inside raw `<img>` tags) are not
  parsed; markdown image syntax only.
- Orphan detection can't see links from generated pages or templates
  outside the scanned tree (e.g. a nav built by a static-site generator).
- Windows path separators are handled via `os.sep` replacement but not
  tested on Windows.
