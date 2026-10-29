# docs-anchor-checker

`docs-anchor-checker` is a standard-library-only Python CLI that lints a
markdown docs site *before* you publish it. Point it at a folder of
`.md` files and it reports, per file:

| Check | Code | What it catches |
|---|---|---|
| Broken links | `BROKEN_LINK` | relative `.md` links and local image paths that don't resolve to a file |
| Broken anchors | `BROKEN_ANCHOR` | `#heading` links whose target heading can't be found (same page or another page) |
| Missing image alt text | `MISSING_ALT` | `![](src)` images with empty alt text |
| Duplicate headings | `DUPLICATE_HEADING` | two headings in one file that produce the same GitHub anchor slug |
| Heading-level skips | `HEADING_SKIP` | outline jumps like h1 directly to h3 |
| Front-matter consistency | `FRONT_MATTER` | fields that other pages have but this one is missing |
| Orphan pages | `ORPHAN` | pages that no other markdown file links to |

Every finding comes with a plain-English suggested fix, and all suggestions
are collected in a **Suggested fixes** section at the bottom of the report.

Anchors are checked using GitHub-style slug rules, so what surfaces clean
here will match how GitHub and most static site generators render your
headings — links that look right on disk but are subtly wrong (typos,
renamed headings, moved files) get caught before readers do.

## Why

A docs site with one broken anchor instructs quietly and confuses loudly.
This tool is for authors who want their book-hub and manual pages verified
mechanically, with a report that reads like a friend pointing out problems —
not a stack trace at your feelings.

It complements the `markdown-manual-site-template` (which provides the
site skeleton) and `repo-polish-checker-cli` (which checks the repo
itself rather than the docs content).

## What it does not do

- No secrets, API keys, tracking, or network access — everything is local.
- It does not modify your files; it only reports.
- It intentionally skips external URLs (`https://...`), site-root-absolute
  links (`/other/dir/page.md`) whose published root isn't knowable, and
  ambiguous bare targets like `[X](setup)` with no extension.

## Requirements

Python 3.9+. No third-party packages.

## Install

From the project folder (optional — you can also run it straight from the
source directory):

```bash
python3 -m pip install .
docs-anchor-checker --version
```

## Usage

```bash
# Lint the current directory
python3 -m docs_anchor_checker

# Lint a docs tree, skipping one subdirectory
python3 -m docs_anchor_checker ./site --exclude drafts

# JSON output (for scripts and editors)
python3 -m docs_anchor_checker ./site --json
```

Exit codes: `0` = no issues found, `1` = issues found, `2` = bad arguments.
Wire it into CI or a publish script: lint, only publish when it passes.

### Sample report

```text
docs-anchor-checker 1.0.0 — scanned 3 markdown file(s) under 'site'

index.md: 4 issue(s)
  line 10     BROKEN_LINK        broken link './missing-page.md': file not found
  line 11     BROKEN_ANCHOR      broken anchor in './guide.md#wrong-anchor': no heading '#wrong-anchor' (closest: 'packaging')
  line 14     BROKEN_LINK        broken image reference './assets/shot.png': file not found
  line 14     MISSING_ALT        image './assets/shot.png' is missing alt text
...
Summary: 10 issue(s) (BROKEN_LINK=4, BROKEN_ANCHOR=2, ...)

Suggested fixes
---------------
  - index.md:14: describe the image, e.g. ![<short description>](<target>)

Result: FAIL — fix issues before publishing
```

## How links are resolved

- `[text](./guide.md#section)` resolves `guide.md` relative to the directory
  of the *linking* page, then checks that a heading slugging to `section`
  exists in *that* target file.
- `[text](#section)` checks the current page only.
- GitHub slug rules: lowercase, punctuation stripped, spaces to dashes,
  formatting markers (`**bold**`, `` `code` ``) removed.

## Development

```bash
python3 -m pip install -e .
python3 -m pytest
```

`tests/fixtures/` holds two seeded doc trees: `good/` (should report zero
issues) and `bad/` (one or more findings for every check). Add cases for
new rules next to the existing ones.

## License

MIT — see `LICENSE`. Copyright (c) 2026 Asdale Dynamics, LLC.

Part of the beginner-friendly AI tooling published by
[Asdale Dynamics, LLC](https://dylanasdale.github.io) — plain-English AI
education, manuals, and practical tools.
