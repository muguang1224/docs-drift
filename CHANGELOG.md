# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-15

### Added

- Documentation-vs-code drift checker for markdown repos.
- Rules `DRIFT000`–`DRIFT010` with stable ids and severities: dead relative
  links, broken anchors, version mismatch against the manifest, identifiers in
  inline code that no longer exist in source, documented CLI flags with no
  definition, a CHANGELOG missing the current version, duplicate headings, and
  stale markers.
- Code-fence masking: fenced blocks are blanked before any markdown structure is
  parsed, with correct CommonMark nesting (a closing fence must match the opener's
  character and be at least as long).
- `--format markdown|json`, `--fail-on LEVEL`, `--docs` / `--source` globs,
  `--ignore RULE|PATH`, `--config`.
- Self-contained `SKILL.md` with the script inlined, so the whole skill is one file.

### Fixed

- A nested code fence (a 3-backtick line inside a 4-backtick fence) closed the
  fence early, leaking sample content into the checks — a `[link](x)` or a
  `## Heading` inside a code sample could be reported as real documentation.
- Links written inside inline code (`` `[link](x)` ``) were treated as real links.
- Prose that merely mentioned the word "TODO" was reported as a stale marker;
  markers are now flagged only when they start a line.
- URL-encoded link targets (`my%20doc.md`) failed to resolve to the file on disk.
- Heading anchors for headings containing `&` did not match GitHub's slug.

[1.0.0]: https://github.com/muguang1224/docs-drift/releases/tag/v1.0.0
