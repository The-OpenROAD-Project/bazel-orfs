#!/usr/bin/env python3
"""The README quotes results.json, and nothing it quotes may disagree.

Two assertions, over the committed README.md and results.json:

- Table 1, between its markers, is byte-equal to what readme_numbers
  renders.
- Every fact readme_numbers renders appears in the README as a
  substring.

Not manual: it is milliseconds, and what it guards -- three drafts'
numbers coexisting in the prose -- is silent everywhere else.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import readme_numbers  # noqa: E402


def _src(rel):
    root = os.path.join(os.environ["TEST_SRCDIR"], os.environ["TEST_WORKSPACE"])
    return os.path.join(root, "test/coremark_joule", rel)


class ReadmeNumbersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_src("results.json")) as f:
            cls.document = json.load(f)
        with open(_src("README.md")) as f:
            cls.readme = f.read()

    def test_table1_is_rendered(self):
        begin = self.readme.index(readme_numbers.TABLE1_BEGIN)
        end = self.readme.index(readme_numbers.TABLE1_END)
        block = self.readme[begin + len(readme_numbers.TABLE1_BEGIN) : end].strip()
        self.assertEqual(
            block,
            readme_numbers.render_table1(self.document),
            "Table 1 in README.md differs from results.json; paste the "
            "output of `bazelisk run //test/coremark_joule/scripts:"
            "readme_numbers -- test/coremark_joule/results.json`",
        )

    def test_every_fact_is_quoted(self):
        missing = {
            key: value
            for key, value in readme_numbers.facts(self.document).items()
            if value not in self.readme
        }
        self.assertEqual(
            missing, {}, "facts rendered from results.json absent from README.md"
        )

    def test_table1_markers_unique(self):
        self.assertEqual(self.readme.count(readme_numbers.TABLE1_BEGIN), 1)
        self.assertEqual(self.readme.count(readme_numbers.TABLE1_END), 1)


if __name__ == "__main__":
    unittest.main()
