"""Core linting logic: parsing markdown, collecting findings, building reports."""

from __future__ import annotations

import os
import posixpath
import re
from dataclasses import dataclass, field

SEVERITY_ORDER = ("BROKEN_LINK", "BROKEN_ANCHOR", "MISSING_ALT", "HEADING_SKIP",
                  "DUPLICATE_HEADING", "FRONT_MATTER", "ORPHAN")

MIN_LINK_LENGTH = 60  # targets longer than this are unlikely to be real paths

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF_RE = re.compile(r"^\s*\[([^\]]+)\]:\s*(\S+)\s*$")
YAML_FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


@dataclass
class Finding:
    file: str            # path relative to root, "/"-separated
    line: int            # 1-based; 0 for site-wide findings
    code: str            # one of SEVERITY_ORDER
    message: str
    suggestion: str = ""


@dataclass
class Report:
    root: str
    files_scanned: int = 0
    findings: list = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.findings)

    def codes(self) -> dict:
        counts = {}
        for f in self.findings:
            counts[f.code] = counts.get(f.code, 0) + 1
        return counts


def strip_front_matter(text: str) -> str:
    """Return the markdown body without the leading YAML front-matter block."""
    return body_with_placeholder(text)


def body_with_placeholder(text: str) -> str:
    """Like removing front matter, but keeps line numbers aligned by replacing
    each front-matter line with a blank line."""
    if not (text.startswith("---") and "\n" in text):
        return text
    first_nl = text.index("\n")
    m = re.search(r"^---\s*$", text[first_nl + 1:], flags=re.MULTILINE)
    if not m:
        return text
    cut = first_nl + 1 + m.end()
    cut = cut + 1 if cut < len(text) else len(text)
    return "\n" * text[:cut].count("\n") + text[cut:]


def strip_code_blocks(text: str) -> str:
    """Blank out fenced code blocks so we never lint inside them."""
    out_lines = []
    fence_char = None
    for line in text.splitlines():
        if fence_char:
            if line.strip().startswith(fence_char):
                fence_char = None
            out_lines.append("")
            continue
        m = FENCE_RE.match(line)
        if m:
            fence_char = m.group(1)[0]
            out_lines.append("")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def inline_clean(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[*_~]+([^*_~]+)[*_~]+", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text.strip()


def github_slug(title: str) -> str:
    """GitHub-style heading slug: '#Hi, There! v2' -> '#hi-there-v2' minus slug form."""
    slug = inline_clean(title).lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    slug = slug.replace("_", " ")
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def extract_headings(text: str):
    """Yield (line_no, level, title) from non-code lines of a markdown body."""
    code = strip_code_blocks(text)
    for i, line in enumerate(code.splitlines(), start=1):
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = inline_clean(m.group(2))
            if title:
                yield i, level, title


def parse_front_matter(text: str) -> dict | None:
    """Parse simple flat YAML front matter. Returns None if absent/malformed."""
    if not text.startswith("---"):
        return None
    parts = text.split("\n", 1)
    if len(parts) != 2:
        return None
    end = re.search(r"^---\s*$", parts[1], flags=re.MULTILINE)
    if not end:
        return None
    fields = {}
    for line in parts[1][:end.start()].splitlines():
        m = YAML_FIELD_RE.match(line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def iter_markdown(root: str, exclude: tuple = ()):
    """Yield absolute paths of markdown files under root (sorted, excluded dirs skipped)."""
    skip = {e.replace(os.sep, "/").strip("/").strip() for e in exclude} - {""}
    for dirpath, dirnames, filenames in os.walk(root):
        here = rel(root, dirpath)
        dirnames[:] = [d for d in dirnames
                       if posixpath.normpath(d) not in skip
                       and d not in (".git", "node_modules", ".venv", "__pycache__")]
        if here != ".":
            dirnames[:] = [d for d in dirnames
                           if posixpath.normpath(posixpath.join(here, d)) not in skip]
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                yield os.path.join(dirpath, name)


def classify_target(target: str) -> str:
    """'external' (skip), 'internal' (must exist), or 'skip' (ambiguous)."""
    t = target.strip("<>")
    if t.startswith(("http://", "https://", "mailto:", "//")):
        return "external"
    path_part, _, _frag = t.partition("#")
    if path_part.startswith("/"):
        return "skip"  # site-root absolute path: root is unknowable
    ext = posixpath.splitext(path_part)[1].lower()
    if not path_part:
        return "internal"  # pure '#anchor' link
    if ext == ".md":
        return "internal"
    if ext in IMAGE_EXTS:
        return "external"  # images handled separately (alt text + existence)
    return "skip"  # bare targets like 'setup' or 'notes.txt': ambiguous


def resolve_target(file_rel: str, target: str) -> str:
    """Resolve a relative markdown target against the source file's directory."""
    path_part = target.strip("<>").partition("#")[0]
    if not path_part:
        return ""
    rel_dir = posixpath.dirname(file_rel) if posixpath.dirname(file_rel) else ""
    resolved = posixpath.normpath(posixpath.join(rel_dir, path_part))
    return resolved


def abs_target_path(root: str, file_rel: str, target: str) -> str:
    """Absolute filesystem path for a target resolved from file_rel's directory."""
    return os.path.normpath(os.path.join(
        root, os.path.dirname(file_rel or ""), target.strip("<>")))


def best_anchor_match(anchors, wanted: str) -> str:
    wanted = wanted.lower()
    best, best_score = "", -1.0
    for a in anchors:
        al = a.lower()
        hit = sum(1 for ch in al if ch in wanted) / max(len(al), 1)
        if hit > best_score:
            best, best_score = a, hit
    return best if best_score >= 0.4 else ""


def check_file(file_rel: str, text: str, out: list, links_out: set, root: str,
               slug_maps: dict):
    """Append per-file findings to `out`; record outbound .md links in `links_out`.

    `slug_maps` maps each scanned file (relative path, lowercase) to its
    heading-slug lookup so cross-file anchors can be validated. Same-page
    anchors and duplicate-heading checks use this file's own slugs.
    """
    body = strip_code_blocks(strip_front_matter(text))
    headings = list(extract_headings(strip_front_matter(text)))
    own_slugs = {github_slug(title).lower(): title for _, _, title in headings}

    # duplicate headings (same slug more than once)
    seen = {}
    for line_no, _level, title in headings:
        slug = github_slug(title)
        seen.setdefault(slug, []).append((line_no, title))
    for slug, occurrences in sorted(seen.items()):
        if len(occurrences) > 1:
            for line_no, title in occurrences[1:]:
                out.append(Finding(
                    file_rel, line_no, "DUPLICATE_HEADING",
                    f"duplicate heading '{title}' -> #{slug}",
                    f"rename this heading so each slug is unique (already used on line"
                    f" {occurrences[0][0]}); GitHub anchors can only point to one of them"))

    # heading level skips
    prev = 0
    for line_no, level, title in headings:
        if prev and level > prev + 1:
            out.append(Finding(
                file_rel, line_no, "HEADING_SKIP",
                f"heading level jumps from h{prev} to h{level} ('{title}')",
                f"insert an h{prev + 1} heading between them, or demote earlier"
                f" h{prev} headings so '{title}' fits the outline"))
        prev = level

    for i, line in enumerate(body.splitlines(), start=1):
        # images: alt text + target existence
        for m in IMAGE_RE.finditer(line):
            alt, target = m.group(1), m.group(2)
            real = target.strip("<>")
            ext = posixpath.splitext(real)[1].lower()
            remote = real.startswith(("http://", "https://", "//")) or os.path.isabs(real)
            if ext in IMAGE_EXTS and not remote:
                target_path = abs_target_path(root, file_rel, target)
                if not os.path.isfile(target_path):
                    out.append(Finding(
                        file_rel, i, "BROKEN_LINK",
                        f"broken image reference '{target}': file not found",
                        f"add the image file or fix the path '{real}'"))
            if not alt.strip():
                out.append(Finding(
                    file_rel, i, "MISSING_ALT",
                    f"image '{target}' is missing alt text",
                    f'describe the image, e.g. ![<short description>]({target})'))

        # inline links: existence + anchors
        for m in LINK_RE.finditer(line):
            label, target = m.group(1), m.group(2)
            real = target.strip("<>")
            if not label.strip() or len(real) > MIN_LINK_LENGTH:
                continue
            kind = classify_target(real)
            if kind == "external" or kind == "skip":
                continue
            path_part, _, anchor = real.partition("#")
            resolved = ""
            if path_part:
                resolved = resolve_target(file_rel, real)
                links_out.add(resolved)
                target_path = abs_target_path(root, file_rel, path_part)
                if not os.path.isfile(target_path):
                    out.append(Finding(
                        file_rel, i, "BROKEN_LINK",
                        f"broken link '{target}': file not found"
                        f" (resolved to '{resolved}')",
                        f"create the file or fix the path '{path_part}', which resolves"
                        f" against the directory of '{file_rel}'"))
                    continue
            if anchor:
                candidates = own_slugs if not path_part else slug_maps.get(
                    resolved.lower(), {})
                locator = f"#{anchor}" if not path_part else \
                    f"'{real}' (target '{resolved}')"
                if anchor.lower() not in candidates:
                    nearest = best_anchor_match(list(candidates.keys()), anchor)
                    has_headings = bool(candidates)
                    out.append(Finding(
                        file_rel, i, "BROKEN_ANCHOR",
                        f"broken anchor in '{real}': "
                        + ("target page has no headings" if not has_headings
                           else f"no heading '#{anchor}'")
                        + (f" (closest: '{nearest}')" if nearest else ""),
                        f"point the link at an existing heading, e.g."
                        f" [{label}]({path_part or ''}#{nearest or 'existing-heading'})"))


def scan(root: str, exclude: tuple = ()):
    """Run all checks over the doc tree at `root`; returns a Report."""
    report = Report(root=root)
    markdowns = sorted(iter_markdown(root, exclude))
    file_texts = {}
    link_sets = {}
    fm_fields = {}

    for path in markdowns:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        rel_file = rel(root, path)
        file_texts[rel_file] = text
        fm = parse_front_matter(text)
        if fm is not None:
            fm_fields[rel_file] = fm

    slug_maps = {}
    for rel_file, text in file_texts.items():
        slug_maps[rel_file.lower()] = {
            github_slug(title).lower(): title for _, _, title in
            extract_headings(strip_front_matter(text))}

    for rel_file, text in file_texts.items():
        links = set()
        link_sets[rel_file] = links
        check_file(rel_file, text, report.findings, links, root, slug_maps)
        # reference-style definitions: [label]: ./other.md#section
        for m in REF_DEF_RE.finditer(strip_code_blocks(strip_front_matter(text))):
            target = m.group(2)
            if "<" in target and "http" in target:
                continue
            real = target.strip("<>")
            kind = classify_target(real)
            if kind != "internal":
                continue
            path_part, _, anchor = real.partition("#")
            if path_part and len(real) <= MIN_LINK_LENGTH:
                links.add(resolve_target(rel_file, real))

    # front-matter consistency: common fields should appear in every doc
    if len(fm_fields) >= 2:
        counts = {}
        for fm in fm_fields.values():
            for k in fm:
                counts[k] = counts.get(k, 0) + 1
        common = {k for k, c in counts.items() if c >= max(2, len(fm_fields) // 2 + 1)}
        for rel_file in sorted(fm_fields):
            missing = sorted(common - set(fm_fields[rel_file]))
            if missing:
                report.findings.append(Finding(
                    rel_file, 0, "FRONT_MATTER",
                    "front matter is missing field(s) use elsewhere on the site: "
                    + ", ".join(missing),
                    "add " + ", ".join(f"{k}: <value>" for k in missing)
                    + " to the front matter, or remove the field from the other pages"))

    # orphan pages: nothing anywhere links to them (front pages are exempt)
    for rel_file in sorted(file_texts):
        if posixpath.basename(rel_file).lower() in ("index.md", "readme.md"):
            continue
        incoming = any(rel_file in s for f, s in link_sets.items() if f != rel_file)
        if not incoming:
            report.findings.append(Finding(
                rel_file, 0, "ORPHAN",
                "orphan page: no other markdown file links to it",
                f"connect it from a related page, e.g. in index.md add "
                f"[<label>](./{rel_file}) (links resolve relative to each page's directory)"))

    order = {c: i for i, c in enumerate(SEVERITY_ORDER)}
    report.findings.sort(key=lambda f: (f.file, order.get(f.code, 99),
                                        f.line, f.message))
    report.files_scanned = len(file_texts)
    return report
