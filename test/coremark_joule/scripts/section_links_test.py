#!/usr/bin/env python3
"""Every § in the committed README is a link to a heading that exists."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import section_links  # noqa: E402


def _readme():
    root = os.path.join(os.environ["TEST_SRCDIR"], os.environ["TEST_WORKSPACE"])
    with open(os.path.join(root, "test/coremark_joule/README.md")) as f:
        return f.read()


class SectionLinksTest(unittest.TestCase):
    def test_anchor_matches_github(self):
        self.assertEqual(
            section_links.anchor("4.8 Cross-checks against the nearest published studies"),
            "48-cross-checks-against-the-nearest-published-studies",
        )
        self.assertEqual(section_links.anchor("5. Threats to validity"), "5-threats-to-validity")
        self.assertEqual(
            section_links.anchor("3.8 What sets a CPU core's frequency, and what the SDC must therefore say"),
            "38-what-sets-a-cpu-cores-frequency-and-what-the-sdc-must-therefore-say",
        )

    def test_relink_links_and_reports_dangling(self):
        text = "## 4. Results\n\n### 4.1 The four\n\nSee §4.1 and §9.\n\n```\n# §4.1 in code stays\n```\n"
        new, dangling = section_links.relink(text)
        self.assertIn("[§4.1](#41-the-four)", new)
        self.assertIn("# §4.1 in code stays", new)
        self.assertEqual(dangling, ["9"])

    def test_readme_is_fully_linked(self):
        text = _readme()
        new, dangling = section_links.relink(text)
        self.assertEqual(dangling, [], "§ references with no heading")
        self.assertEqual(new, text, "README has unlinked or stale § references; run section_links.py --fix")


if __name__ == "__main__":
    unittest.main()
