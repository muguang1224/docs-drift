# docs-drift

**Find where your documentation stopped matching your code.** Point it at a repo; it compares markdown against the actual source tree and reports the checkable mismatches — dead links, broken anchors, stale version numbers, renamed flags and symbols that never made it back into the docs.

No network. No rewriting. No prose opinions. Just the drift you can verify.

```console
$ docs-drift .
# docs-drift report

Root: `/home/you/proj`

**3 finding(s)** — 0 high, 1 medium, 2 low, 0 info

## `DRIFT005` [MEDIUM] README.md:42

documented flag --frobnicate is not defined anywhere in source

> Remove the stale flag or implement it.
...
```

## Why

A README is a promise about the code. Refactors silently break it: a flag gets renamed, a function is deleted, the version badge is never bumped, a link rots in a moved file. Nothing fails, so nobody notices until a user follows the docs and hits a wall. docs-drift turns "our docs might be stale" into a concrete, line-numbered list.

## Install

No install. It's a single standard-library script.

```bash
git clone https://github.com/muguang1224/docs-drift
python3 docs-drift/scripts/docs_drift.py /path/to/your/repo
```

Requires Python 3.8+.

## Usage

```bash
docs_drift.py [PATH] [--format markdown|json] [--fail-on LEVEL]
              [--docs GLOB ...] [--source GLOB ...]
              [--ignore RULE|PATH ...] [--config FILE] [--version]
```

| Flag | Meaning |
|------|---------|
| `PATH` | Repo root to check (default `.`) |
| `--format` | `markdown` (default) or `json` |
| `--fail-on` | Exit `1` if any finding is at/above `info\|low\|medium\|high` |
| `--docs` | Extra doc globs (repeatable) |
| `--source` | Override/append source globs (repeatable) |
| `--ignore` | Silence a rule id (`DRIFT004`) or a path; repeatable |
| `--config` | JSON file: `{"ignore": [...], "docs": [...], "source": [...]}` |

Exit codes: `0` clean / below threshold · `1` finding at/above `--fail-on` · `2` usage or IO error.

## Rules

| Rule | Severity | Meaning |
|------|----------|---------|
| DRIFT001 | medium | Relative link target does not exist |
| DRIFT002 | low | Anchor has no matching heading |
| DRIFT003 | high | Doc version disagrees with the manifest |
| DRIFT004 | low | Identifier in inline code not found in source |
| DRIFT005 | medium | Documented CLI flag not defined in source |
| DRIFT006 | low | CHANGELOG has no entry for the current version |
| DRIFT007 | info | Duplicate heading in one document |
| DRIFT008 | info | A line starts with a stale marker (TODO/FIXME/TBD/WIP) |
| DRIFT000 | info | No markdown documentation found |
| DRIFT010 | info | No source files found; symbol/flag checks skipped |

Code fences are masked before structure is parsed, so a `## Heading` or `[link](x)` inside a code sample is never treated as real documentation.

## CI

```yaml
- run: python3 docs-drift/scripts/docs_drift.py . --fail-on medium
```

## What it is not

Not a prose editor, not a grammar or tone checker, not a plagiarism/similarity tool. It never rewrites your docs — deleting or correcting a stale line is your call. See `SKILL.md` for the full guardrails.

## Also an Agent Skill

This repo is also a self-contained Agent Skill: [`SKILL.md`](SKILL.md) contains the workflow, the guardrails, and the full script inline.

## License

MIT — see [`LICENSE`](LICENSE).
