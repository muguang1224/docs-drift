#!/usr/bin/env python3
"""Tests for docs-drift. Run: python3 -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "docs_drift.py")

sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import docs_drift as ddf  # noqa: E402


def write(root, name, content):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


class Slug(unittest.TestCase):
    def test_slugify_basic(self):
        # GitHub anchors a space to a hyphen but keeps the double space left by
        # a dropped '&', hence the double hyphen
        self.assertEqual(ddf.slugify("Install & Usage"), "install--usage")

    def test_slugify_punct(self):
        self.assertEqual(ddf.slugify("What's new?"), "whats-new")

    def test_external_detection(self):
        self.assertTrue(ddf.is_external("https://example.com"))
        self.assertTrue(ddf.is_external("mailto:a@b.com"))
        self.assertFalse(ddf.is_external("docs/other.md"))


class Rules(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_analyze(self):
        docs, sources = ddf.collect(self.root, ddf.DEFAULT_DOCS, ddf.DEFAULT_SOURCE)
        return {f.rule for f in ddf.analyze(self.root, docs, sources, set())}

    def test_all_clean(self):
        write(self.root, "README.md", "# Project\n\nSee [docs](docs/guide.md).\n")
        write(self.root, "docs/guide.md", "# Guide\n\nHello.\n")
        write(self.root, "app.py", "def main():\n    pass\n")
        self.assertEqual(self.run_analyze(), set())

    def test_drift001_dead_link(self):
        write(self.root, "README.md", "# P\n\n[missing](docs/nope.md)\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertIn("DRIFT001", self.run_analyze())

    def test_drift002_broken_anchor(self):
        write(self.root, "README.md", "# P\n\n[jump](#does-not-exist)\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertIn("DRIFT002", self.run_analyze())

    def test_drift002_valid_anchor(self):
        write(self.root, "README.md", "# P\n\n## Install\n\n[jump](#install)\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT002", self.run_analyze())

    def test_drift003_version_mismatch(self):
        write(self.root, "README.md", "# P\n\n![v](https://img.shields.io/badge/version-0.9.0-blue)\n")
        write(self.root, "pyproject.toml", '[project]\nname = "p"\nversion = "1.0.0"\n')
        write(self.root, "app.py", "x = 1\n")
        self.assertIn("DRIFT003", self.run_analyze())

    def test_drift003_match_ok(self):
        write(self.root, "README.md", "# P\n\n![v](https://img.shields.io/badge/version-1.0.0-blue)\n")
        write(self.root, "pyproject.toml", '[project]\nname = "p"\nversion = "1.0.0"\n')
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT003", self.run_analyze())

    def test_drift004_unknown_identifier(self):
        write(self.root, "README.md", "# P\n\nCall `run_pipeline()` to start.\n")
        write(self.root, "app.py", "def start():\n    pass\n")
        self.assertIn("DRIFT004", self.run_analyze())

    def test_drift004_known_identifier_ok(self):
        write(self.root, "README.md", "# P\n\nCall `run_pipeline()` to start.\n")
        write(self.root, "app.py", "def run_pipeline():\n    pass\n")
        self.assertNotIn("DRIFT004", self.run_analyze())

    def test_drift005_unknown_flag(self):
        write(self.root, "README.md", "# P\n\nUse `--frobnicate` to enable it.\n")
        write(self.root, "cli.py", "import argparse\np.add_argument('--other')\n")
        self.assertIn("DRIFT005", self.run_analyze())

    def test_drift005_known_flag_ok(self):
        write(self.root, "README.md", "# P\n\nUse `--verbose` to enable it.\n")
        write(self.root, "cli.py", "p.add_argument('--verbose')\n")
        self.assertNotIn("DRIFT005", self.run_analyze())

    def test_drift006_changelog_missing_version(self):
        write(self.root, "README.md", "# P\n")
        write(self.root, "pyproject.toml", '[project]\nversion = "2.0.0"\n')
        write(self.root, "CHANGELOG.md", "# Changelog\n\n## 1.0.0\n\n- stuff\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertIn("DRIFT006", self.run_analyze())

    def test_drift007_duplicate_heading(self):
        write(self.root, "README.md", "# P\n\n## Notes\n\n## Notes\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertIn("DRIFT007", self.run_analyze())

    def test_drift008_stale_marker(self):
        write(self.root, "README.md", "# P\n\nTODO: write this section.\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertIn("DRIFT008", self.run_analyze())

    def test_fenced_heading_not_counted(self):
        # a "## Usage" inside a code sample must not count as a real heading
        write(self.root, "README.md", "# P\n\n## Usage\n\n```md\n## Usage\n```\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT007", self.run_analyze())

    def test_fenced_link_ignored(self):
        write(self.root, "README.md", "# P\n\n```md\n[missing](nope.md)\n```\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT001", self.run_analyze())

    def test_fenced_stale_marker_ignored(self):
        write(self.root, "README.md", "# P\n\n```python\n# TODO: fix\nx = 1\n```\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT008", self.run_analyze())

    def test_nested_fence_not_closed_early(self):
        # a 3-backtick line inside a 4-backtick fence must not end the fence
        write(self.root, "README.md",
              "# P\n\n````md\n```\n[dead](nope.md)\n```\n````\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT001", self.run_analyze())

    def test_flag_in_fence_ignored(self):
        # an example that runs some *other* tool must not flag our CLI
        write(self.root, "README.md", "# P\n\n```console\npip install thing --upgrade\n```\n")
        write(self.root, "cli.py", "p.add_argument('--verbose')\n")
        self.assertNotIn("DRIFT005", self.run_analyze())

    def test_url_encoded_link_resolves(self):
        write(self.root, "README.md", "# P\n\n[g](my%20doc.md)\n")
        write(self.root, "my doc.md", "# G\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT001", self.run_analyze())

    def test_v_prefixed_version_mismatch(self):
        write(self.root, "README.md", "# P\n\nThis is version v0.9.0.\n")
        write(self.root, "pyproject.toml", '[project]\nversion = "1.0.0"\n')
        write(self.root, "app.py", "x = 1\n")
        self.assertIn("DRIFT003", self.run_analyze())

    def test_changelog_old_versions_not_flagged(self):
        write(self.root, "README.md", "# P\n")
        write(self.root, "pyproject.toml", '[project]\nversion = "2.0.0"\n')
        write(self.root, "CHANGELOG.md", "# Changelog\n\n## version 1.0.0\n\n- old\n\n## 2.0.0\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT003", self.run_analyze())

    def test_link_inside_inline_code_ignored(self):
        write(self.root, "README.md", "# P\n\nFor example, write `[link](x)` to make a link.\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT001", self.run_analyze())

    def test_todo_mentioned_in_prose_ignored(self):
        write(self.root, "README.md", "# P\n\nFlags a stale marker (TODO/FIXME) in the text.\n")
        write(self.root, "app.py", "x = 1\n")
        self.assertNotIn("DRIFT008", self.run_analyze())


class Cli(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)

    def test_json_format(self):
        write(self.root, "README.md", "# P\n\n[missing](nope.md)\n")
        write(self.root, "app.py", "x = 1\n")
        proc = self.run_cli(self.root, "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["tool"], "docs-drift")
        self.assertGreaterEqual(data["summary"]["total"], 1)

    def test_fail_on_medium(self):
        write(self.root, "README.md", "# P\n\n[missing](nope.md)\n")
        write(self.root, "app.py", "x = 1\n")
        proc = self.run_cli(self.root, "--fail-on", "medium")
        self.assertEqual(proc.returncode, 1)

    def test_clean_exit_zero(self):
        write(self.root, "README.md", "# Project\n\nHello.\n")
        write(self.root, "app.py", "x = 1\n")
        proc = self.run_cli(self.root, "--fail-on", "info")
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_ignore_rule(self):
        write(self.root, "README.md", "# P\n\n[missing](nope.md)\n")
        write(self.root, "app.py", "x = 1\n")
        proc = self.run_cli(self.root, "--format", "json", "--ignore", "DRIFT001")
        data = json.loads(proc.stdout)
        self.assertNotIn("DRIFT001", {f["rule"] for f in data["findings"]})

    def test_not_a_directory_exit_2(self):
        proc = self.run_cli(os.path.join(self.root, "nope"))
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
