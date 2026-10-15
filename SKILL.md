---
name: "docs-drift"
description: "Detect where documentation has drifted away from the code in a repository: dead relative links, broken in-page anchors, version numbers in docs that disagree with the manifest, identifiers and CLI flags mentioned in docs that no longer exist in source, a CHANGELOG missing an entry for the current version, duplicate headings, and stale markers. Use to audit a README/docs set for accuracy, keep docs in sync before a release, or gate CI on documentation consistency. Reads files and prints a report; it never edits docs and never rewrites prose."
---

# docs-drift

Docs go stale silently. A flag gets renamed, a function is deleted, the version badge is never bumped, a link rots — and nothing fails. `docs-drift` finds the parts of doc-vs-code drift that are *mechanically checkable*, so a human only has to review the parts that need judgment.

It compares markdown against the actual source tree and reports specific, verifiable mismatches with a file and line. It does not summarize, rewrite, or "improve" prose.

## When to use this skill

- "Is my README still accurate after this refactor?"
- "Check the docs before I tag a release."
- "Find broken links and stale examples across my docs."
- A CI gate: fail when a doc references a flag or symbol that no longer exists.

Do **not** use it to rewrite documentation, to fix prose, or as a plagiarism/similarity checker. It reports drift; a human decides how to close it.

## How it works

1. Point it at a repo root.
2. It collects markdown (README, `docs/**`, any tracked `*.md`) and source files (Python, JS/TS, Go, Rust, …).
3. It parses headings, links, inline code, and code fences, then runs a fixed rule set against the source tree and the version manifest.
4. It prints a report — markdown for humans, JSON for tooling — most-severe first.

Code fences are masked before markdown structure is parsed, so a `## Heading` inside a fenced example is never mistaken for a real heading, and a `[link](x)` inside a sample is not chased.

## Running it

```bash
# check the current repo
python3 scripts/docs_drift.py .

# machine-readable
python3 scripts/docs_drift.py . --format json

# CI gate: fail on anything medium or worse
python3 scripts/docs_drift.py . --fail-on medium

# widen the source globs if your code isn't *.py/*.js/...
python3 scripts/docs_drift.py . --source "*.rb" --source "lib/**/*.rb"

# silence a noisy rule or a path
python3 scripts/docs_drift.py . --ignore DRIFT004 --ignore vendor/
```

Zero third-party dependencies — standard library only. Runs on Python 3.8+.

## Rules

| Rule    | Severity | Meaning |
|---------|----------|---------|
| DRIFT001 | medium  | Relative link target does not exist |
| DRIFT002 | low     | In-page or cross-file anchor has no matching heading |
| DRIFT003 | high    | Doc cites a version that disagrees with the manifest |
| DRIFT004 | low     | Identifier in inline code not found anywhere in source |
| DRIFT005 | medium  | Documented CLI flag not defined in source |
| DRIFT006 | low     | CHANGELOG has no entry for the current version |
| DRIFT007 | info    | Duplicate heading in one document |
| DRIFT008 | info    | A line starts with a stale marker (TODO/FIXME/TBD/WIP) |
| DRIFT000 | info    | No markdown documentation found |
| DRIFT010 | info    | No source files found; symbol/flag checks skipped |

DRIFT004 and DRIFT005 are heuristics and are marked low/medium on purpose: they flag "this doc token has no counterpart in code", which a human confirms. Everything else (links, anchors, versions, changelog) is exact.

## Output

- **markdown** (default): a header with the root, a severity tally, then one section per finding with rule id, severity, `path:line`, the message, and a suggested fix.
- **json**: `{tool, version, root, summary, findings[]}` — stable shape for CI.

Exit codes: `0` clean or below `--fail-on`; `1` a finding at or above `--fail-on`; `2` usage/IO error.

## Closing the drift (the part that matters)

The report is a worklist, not an answer. Turn it into action:

1. **Broken links and version mismatches first** — those are unambiguously wrong and erode trust fastest.
2. **Confirm symbol/flag findings** — DRIFT004/005 could be a real doc error or a deliberately-illustrative example. Check before "fixing".
3. **Don't pad the docs** — deleting a stale line is usually better than rewriting around it.
4. **Fix the cause, not just the symptom** — if a flag keeps getting renamed, that's a naming-stability problem, not a docs problem.

## Guardrails

- **Read-only.** docs-drift never edits a file, never rewrites prose, never "tidies" a README.
- **No prose judgment.** It does not assess tone, clarity, grammar, or whether a claim is *true* — only whether links resolve, versions match, and named symbols exist.
- **No similarity/plagiarism checks.** It will not and should not be used to detect or evade plagiarism.
- **Heuristics are labeled.** Identifier and flag checks are best-effort; findings carry their location so a human can decide.
- **Fences are respected.** Code samples are not parsed as documentation structure.
- **Two deliberate blind spots.** Flags and symbols are checked *outside* code blocks only, so an
  example that invokes some *other* tool (`pip install x --upgrade`) is never mistaken for yours.
  Reference-style link definitions (`[x]: url`) are not resolved — write inline links to have them checked.

---

## Bundled files (self-contained)

This skill ships with everything it needs. **On first use, if the file is not already on disk, create it under a working directory (e.g. `./docs-drift/`) and run the script from there.** Then use the workflow above.

### `scripts/docs_drift.py`

```python
#!/usr/bin/env python3
"""docs-drift -- detect where documentation has drifted away from the code.

Standard library only (Python 3.8+). Compares markdown docs against the source
tree and reports the *checkable* mismatches: dead relative links, broken
in-page anchors, version numbers that disagree with the manifest, identifiers
and CLI flags mentioned in docs that no longer exist in code, a CHANGELOG that
never got an entry for the current version, duplicate headings, and stale
markers. It reads files and prints a report; it never edits anything.

Usage:
    python3 docs_drift.py [PATH] [--format markdown|json] [--fail-on LEVEL]
                          [--docs GLOB ...] [--source GLOB ...]
                          [--ignore RULE|PATH ...] [--config FILE]

Exit codes:
    0  ran clean, or no finding at/above --fail-on
    1  at least one finding at/above --fail-on
    2  usage / IO error
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from urllib.parse import unquote

VERSION = "1.0.0"
SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}

DEFAULT_DOCS = ["*.md", "README*", "docs/**/*.md", "docs/*.md", "*.mdx"]
DEFAULT_SOURCE = ["*.py", "*.js", "*.ts", "*.jsx", "*.tsx", "*.go", "*.rs",
                  "*.rb", "*.java", "*.c", "*.h", "*.cpp", "*.sh"]

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "site-packages", ".idea", ".vscode", "vendor", ".next", "target",
}

# Words that look like identifiers but rarely are project symbols.
IDENTIFIER_ALLOWLIST = {
    "true", "false", "none", "null", "nil", "ok", "yes", "no", "and", "or",
    "not", "if", "else", "for", "while", "return", "import", "from", "class",
    "def", "function", "const", "let", "var", "new", "this", "self", "super",
    "json", "yaml", "toml", "http", "https", "url", "uri", "api", "cli", "sdk",
    "readme", "changelog", "license", "todo", "fixme", "pip", "npm", "git",
    "os", "id", "uid", "uuid", "utf-8", "utf8", "ascii", "csv", "tsv", "html",
    "css", "sql", "xml", "yaml", "md", "txt", "stdout", "stdin", "stderr",
    "argv", "argc", "main", "init", "setup", "test", "tests", "util", "utils",
    "config", "example", "default", "key", "value", "name", "path", "file",
    "dir", "data", "type", "kind", "foo", "bar", "baz", "qux", "hello", "world",
    "python", "node", "docker", "kubernetes", "bash", "shell", "linux", "macos",
    "windows", "ubuntu", "v1", "v2", "get", "post", "put", "delete", "patch",
    # proper nouns / product names that read as camelCase but are not symbols
    "github", "gitlab", "javascript", "typescript", "postgresql", "postgres",
    "mysql", "mongodb", "sqlite", "redis", "kafka", "graphql", "oauth", "jwt",
    "grpc", "rest", "numpy", "pandas", "react", "vue", "django", "flask",
    "fastapi", "docker", "kubernetes", "terraform", "markdown", "nodejs",
    "pypi", "macos", "linux", "android", "ios", "html5", "css3", "openai",
    "nan", "inf", "null", "nil", "na", "utf8",
}


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
class Finding:
    __slots__ = ("rule", "severity", "path", "line", "message", "hint")

    def __init__(self, rule, severity, path, line, message, hint=""):
        self.rule = rule
        self.severity = severity
        self.path = path
        self.line = line
        self.message = message
        self.hint = hint

    def key(self):
        return (self.path, self.line or 0, self.rule, self.message)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def matches(relpath, patterns):
    rel = relpath.replace(os.sep, "/")
    base = os.path.basename(rel)
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(base, pat):
            return True
        if "**" in pat and fnmatch.fnmatch(rel, pat.replace("**/", "")):
            return True
    return False


def collect(root, doc_globs, source_globs):
    docs, sources = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            low = fn.lower()
            if low.endswith((".md", ".mdx", ".markdown")):
                if matches(rel, doc_globs) or matches(rel, ["*.md", "*.mdx"]):
                    docs.append(full)
            elif matches(rel, source_globs):
                sources.append(full)
    return sorted(set(docs)), sorted(set(sources))


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_ANCHOR_RE = re.compile(r"<a\s+(?:name|id)=\"([^\"]+)\"", re.IGNORECASE)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
FLAG_RE = re.compile(r"(?<![\w-])--([a-zA-Z][a-zA-Z0-9-]*)")
# A stale marker counts only when it *starts* a line (optionally after a bullet),
# not when prose merely mentions the word "TODO".
STALE_LINE_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+|>\s*)*(TODO|FIXME|TBD|WIP|XXX)\b", re.IGNORECASE)


def slugify(text):
    """Approximate GitHub's heading anchor (keeps underscores, drops punctuation,
    turns each space into a hyphen -- so 'Usage & Examples' -> 'usage--examples')."""
    s = text.strip().lower()
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = s.replace(" ", "-")
    return s.strip("-")


FENCE_RE = re.compile(r"^\s*(\x60{3,}|~{3,})")  # \x60 is a backtick; kept escaped so this
# file stays safe to embed inside a markdown code fence.


def mask_fences(lines):
    """Return a copy of `lines` with fenced code blocks blanked out.

    Line count is preserved so reported line numbers stay correct. Markdown
    structure (headings, links, flags, stale markers) must never be read out of
    a code sample. A closing fence must use the same character as the opener and
    be at least as long (CommonMark), so a 4-backtick fence is not closed early
    by a 3-backtick line inside it.
    """
    out, fence_char, fence_len = [], None, 0
    for raw in lines:
        m = FENCE_RE.match(raw)
        if fence_char is None:
            if m:
                tok = m.group(0).strip()
                fence_char, fence_len = tok[0], len(tok)
                out.append("")
            else:
                out.append(raw)
        else:
            out.append("")
            if m:
                tok = m.group(0).strip()
                if tok[0] == fence_char and len(tok) >= fence_len:
                    fence_char, fence_len = None, 0
    return out


def parse_markdown(text):
    """Return headings [(line, level, text, slug)], links [(line, target, kind)]."""
    headings, links = [], []
    for i, raw in enumerate(text.splitlines(), start=1):
        m = HEADING_RE.match(raw)
        if m:
            headings.append((i, len(m.group(1)), m.group(2), slugify(m.group(2))))
        # a link inside inline code is code, not a link -- blank the spans first
        scan = CODE_SPAN_RE.sub(lambda mm: " " * len(mm.group(0)), raw)
        for lm in LINK_RE.finditer(scan):
            links.append((i, lm.group(1),
                          "image" if scan[max(0, lm.start() - 1):lm.start()] == "!" else "link"))
        for am in HTML_ANCHOR_RE.finditer(raw):
            headings.append((i, 0, am.group(1), am.group(1).lower()))
    return headings, links


def is_external(target):
    t = target.strip().lower()
    return (t.startswith(("http://", "https://", "mailto:", "tel:", "ftp://"))
            or re.match(r"^[a-z][a-z0-9+.-]*://", t) is not None)


# ---------------------------------------------------------------------------
# Source scanning
# ---------------------------------------------------------------------------
def scan_sources(sources):
    blob = []
    flags = set()
    for path in sources:
        try:
            text = read_text(path)
        except OSError:
            continue
        blob.append(text)
        for m in re.finditer(r"--[a-zA-Z][a-zA-Z0-9-]+", text):
            flags.add(m.group(0))
    return "\n".join(blob), flags


# ---------------------------------------------------------------------------
# Version sources
# ---------------------------------------------------------------------------
def manifest_version(root):
    pyproj = os.path.join(root, "pyproject.toml")
    if os.path.exists(pyproj):
        try:
            text = read_text(pyproj)
            m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
            if m:
                return m.group(1), "pyproject.toml"
        except Exception:
            pass
    pkg = os.path.join(root, "package.json")
    if os.path.exists(pkg):
        try:
            data = json.loads(read_text(pkg))
            if data.get("version"):
                return str(data["version"]), "package.json"
        except Exception:
            pass
    for name in ("VERSION", "VERSION.txt"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            v = read_text(p).strip().splitlines()
            if v:
                return v[0].strip(), name
    return None, None


def doc_versions(text):
    """Find version-like strings that clearly refer to the project version."""
    found = []
    for m in re.finditer(r"badge/(?:version|v)-([0-9]+\.[0-9]+\.[0-9]+)", text):
        found.append(m.group(1))
    for m in re.finditer(r"\bversion[^\n`]{0,24}?v?([0-9]+\.[0-9]+\.[0-9]+)", text, re.IGNORECASE):
        found.append(m.group(1))
    return found


def changelog_path(root, docs):
    for p in docs:
        if os.path.basename(p).lower().startswith("changelog"):
            return p
    for name in ("CHANGELOG.md", "CHANGELOG", "CHANGELOG.rst"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyze(root, docs, sources, ignore):
    findings = []
    src_blob, src_flags = scan_sources(sources)
    src_lower = src_blob.lower()
    doc_texts = {}
    all_slugs = {}   # path -> set of slugs (for cross-file anchors)

    for path in docs:
        if is_ignored(path, root, ignore):
            continue
        try:
            text = read_text(path)
        except OSError:
            continue
        doc_texts[path] = text
        headings, _ = parse_markdown("\n".join(mask_fences(text.splitlines())))
        all_slugs[path] = {h[3] for h in headings if h[3]}

    ver, ver_src = manifest_version(root)

    for path, text in doc_texts.items():
        rp = rel(root, path)
        lines = text.splitlines()
        masked_lines = mask_fences(lines)
        masked_text = "\n".join(masked_lines)
        headings, links = parse_markdown(masked_text)
        is_changelog = os.path.basename(path).lower().startswith("changelog")

        # DRIFT001 / DRIFT002 -- links and anchors
        for line_no, target, kind in links:
            if is_external(target) or target.startswith("{"):
                continue
            file_part, _, anchor = target.partition("#")
            file_part = unquote(file_part)
            anchor = unquote(anchor)
            if not file_part:  # same-file anchor
                if anchor and anchor.lower() not in all_slugs.get(path, set()):
                    findings.append(Finding("DRIFT002", "low", rp, line_no,
                                            "anchor link #%s does not match any heading in this file" % anchor,
                                            "Fix the spelling or add the missing heading."))
                continue
            if file_part.startswith("/"):
                continue
            target_path = os.path.normpath(os.path.join(os.path.dirname(path), file_part))
            if not os.path.exists(target_path):
                findings.append(Finding("DRIFT001", "medium", rp, line_no,
                                        "relative link target does not exist: %s" % file_part,
                                        "Fix the path or remove the link."))
            elif anchor:
                tp = os.path.normpath(target_path)
                slugs = all_slugs.get(tp)
                if slugs is None and tp.lower().endswith((".md", ".markdown", ".mdx")):
                    try:
                        h2, _ = parse_markdown(read_text(tp))
                        slugs = {x[3] for x in h2 if x[3]}
                    except OSError:
                        slugs = set()
                if slugs is not None and anchor.lower() not in slugs:
                    findings.append(Finding("DRIFT002", "low", rp, line_no,
                                            "anchor #%s not found in %s" % (anchor, file_part),
                                            "Fix the anchor or add the heading."))

        # DRIFT003 -- version mismatch (a CHANGELOG legitimately cites old versions)
        if ver and not is_changelog:
            for dv in doc_versions(masked_text):
                if dv != ver:
                    findings.append(Finding("DRIFT003", "high", rp, 0,
                                            "documentation cites version %s but %s says %s"
                                            % (dv, ver_src, ver),
                                            "Update the doc (badge/text) to match the manifest."))
                    break

        # DRIFT004 -- identifiers mentioned in inline code but absent from source
        if sources:
            for m in INLINE_CODE_RE.finditer(masked_text):
                token = m.group(1).strip()
                base = token[:-2] if token.endswith("()") else token
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", base):
                    continue
                if len(base) < 3 or base.lower() in IDENTIFIER_ALLOWLIST:
                    continue
                looks_like_code = ("_" in base) or bool(re.search(r"[a-z][A-Z]", base)) \
                    or token.endswith("()")
                if not looks_like_code:
                    continue
                if base not in src_blob:
                    line_no = masked_text[:m.start()].count("\n") + 1
                    findings.append(Finding("DRIFT004", "low", rp, line_no,
                                            "`%s` is mentioned in docs but not found in any source file" % base,
                                            "Rename the doc mention or confirm the symbol still exists."))

        # DRIFT005 -- CLI flags in docs but not in source (code samples excluded)
        if src_flags:
            for m in FLAG_RE.finditer(masked_text):
                flag = "--" + m.group(1)
                if flag not in src_blob and flag not in src_flags:
                    line_no = masked_text[:m.start()].count("\n") + 1
                    findings.append(Finding("DRIFT005", "medium", rp, line_no,
                                            "documented flag %s is not defined anywhere in source" % flag,
                                            "Remove the stale flag or implement it."))

        # DRIFT007 -- duplicate headings
        slugs_seen = {}
        for line_no, level, htext, slug in headings:
            if level == 0:
                continue
            if slug in slugs_seen:
                findings.append(Finding("DRIFT007", "info", rp, line_no,
                                        "duplicate heading %r (first at line %d)" % (htext, slugs_seen[slug]),
                                        "Merge the sections or rename one heading."))
            else:
                slugs_seen[slug] = line_no

            # DRIFT008 -- stale markers (outside code blocks; only when a line starts with one)
        for i, raw in enumerate(masked_lines, start=1):
            sm = STALE_LINE_RE.match(raw)
            if sm:
                findings.append(Finding("DRIFT008", "info", rp, i,
                                        "stale marker %r left in documentation" % sm.group(0),
                                        "Resolve it or move it to an issue tracker."))

    # DRIFT006 -- CHANGELOG missing current version
    if ver:
        cl = changelog_path(root, docs)
        if cl:
            try:
                ctext = read_text(cl)
                if ver not in ctext:
                    findings.append(Finding("DRIFT006", "low", rel(root, cl), 0,
                                            "CHANGELOG has no entry for the current version %s (%s)"
                                            % (ver, ver_src),
                                            "Add a section for %s before releasing." % ver))
            except OSError:
                pass

    if not docs:
        findings.append(Finding("DRIFT000", "info", ".", 0,
                                "no markdown documentation found under this path",
                                "Point docs-drift at a repo containing a README or docs/."))
    elif not sources:
        findings.append(Finding("DRIFT010", "info", ".", 0,
                                "no source files found; identifier and flag checks were skipped",
                                "Pass --source with your code globs if the sources live outside the default set."))

    findings = [f for f in findings if f.rule not in {i for i in ignore if re.match(r"^DRIFT\d+$", i)}]
    uniq, seen = [], set()
    for f in findings:
        if f.key() in seen:
            continue
        seen.add(f.key())
        uniq.append(f)
    uniq.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.path, f.line or 0, f.rule))
    return uniq


def is_ignored(path, root, ignore):
    rp = rel(root, path)
    for item in ignore:
        if re.match(r"^DRIFT\d+$", item):
            continue
        if rp == item or rp.startswith(item.rstrip("/") + "/") or os.path.basename(path) == item:
            return True
    return False


def rel(root, path):
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        return path


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_markdown(findings, root):
    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1
    lines = ["# docs-drift report", "",
             "Root: `%s`" % os.path.abspath(root), "",
             "**%d finding(s)** — %d high, %d medium, %d low, %d info"
             % (len(findings), counts["high"], counts["medium"], counts["low"], counts["info"]), ""]
    if not findings:
        lines.append("Documentation and code agree on everything checked.")
        return "\n".join(lines) + "\n"
    for f in findings:
        loc = f.path + (":%d" % f.line if f.line else "")
        lines.append("## `%s` [%s] %s" % (f.rule, f.severity.upper(), loc))
        lines.append("")
        lines.append(f.message)
        if f.hint:
            lines.append("")
            lines.append("> %s" % f.hint)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(findings, root):
    return json.dumps({
        "tool": "docs-drift",
        "version": VERSION,
        "root": os.path.abspath(root),
        "summary": {"total": len(findings),
                    **{s: sum(1 for f in findings if f.severity == s) for s in SEVERITY_ORDER}},
        "findings": [{"rule": f.rule, "severity": f.severity, "path": f.path,
                      "line": f.line, "message": f.message, "hint": f.hint} for f in findings],
    }, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog="docs-drift",
                                description="Detect drift between docs and code (standard library only).")
    p.add_argument("path", nargs="?", default=".", help="repo root to check (default: .)")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("--fail-on", choices=("info", "low", "medium", "high"), default=None)
    p.add_argument("--docs", action="append", default=[], metavar="GLOB", help="doc globs (repeatable)")
    p.add_argument("--source", action="append", default=[], metavar="GLOB", help="source globs (repeatable)")
    p.add_argument("--ignore", action="append", default=[], metavar="RULE_OR_PATH")
    p.add_argument("--config", default=None, help="JSON file with {\"ignore\": [...], \"docs\": [...], \"source\": [...]}")
    p.add_argument("--version", action="version", version="docs-drift %s" % VERSION)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.path):
        print("docs-drift: not a directory: %s" % args.path, file=sys.stderr)
        return 2

    doc_globs = list(DEFAULT_DOCS)
    source_globs = list(DEFAULT_SOURCE)
    ignored = list(args.ignore)
    if args.config:
        try:
            cfg = json.loads(read_text(args.config))
            doc_globs += cfg.get("docs", [])
            source_globs += cfg.get("source", [])
            ignored += cfg.get("ignore", [])
        except Exception as exc:
            print("docs-drift: could not read config %s: %s" % (args.config, exc), file=sys.stderr)
            return 2
    doc_globs += args.docs
    source_globs += args.source

    docs, sources = collect(args.path, doc_globs, source_globs)
    findings = analyze(args.path, docs, sources, ignored)

    out = render_markdown(findings, args.path) if args.format == "markdown" else render_json(findings, args.path)
    sys.stdout.write(out)

    if args.fail_on:
        threshold = SEVERITY_ORDER[args.fail_on]
        if any(SEVERITY_ORDER[f.severity] >= threshold for f in findings):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

```
