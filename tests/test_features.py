"""docs/FEATURES.md stays current with each release.

Fails when the file's `Current release:` line is not the version in
.claude-plugin/plugin.json, or when no feature row has that version's Since.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEATURES = os.path.join(ROOT, "docs", "FEATURES.md")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def plugin_version():
    return json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["version"]


def rows(text):
    """Feature table rows as lists of cells, header and separator rows left out."""
    out = []
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Feature |"):
            continue
        out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


class FeaturesDocTests(unittest.TestCase):
    def setUp(self):
        self.text = read(FEATURES)
        self.version = plugin_version()

    def test_current_release_matches_plugin_version(self):
        m = re.search(r"^Current release: (\S+)$", self.text, re.M)
        self.assertIsNotNone(m, "docs/FEATURES.md needs a 'Current release: X.Y.Z' line")
        self.assertEqual(
            m.group(1), self.version,
            "docs/FEATURES.md says %s but plugin.json says %s: update the feature table for this release"
            % (m.group(1), self.version),
        )

    def test_every_row_has_four_cells(self):
        for cells in rows(self.text):
            self.assertEqual(len(cells), 4, cells)
            self.assertTrue(all(cells), cells)

    def test_release_has_its_features(self):
        minor = ".".join(self.version.split(".")[:2])
        since = [cells[3] for cells in rows(self.text)]
        self.assertTrue(
            any(s.startswith(minor) for s in since),
            "no feature row has Since %s: change its Unreleased rows to %s" % (minor, minor),
        )


if __name__ == "__main__":
    unittest.main()
