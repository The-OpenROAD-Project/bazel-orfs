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

    def _block(self, begin, end):
        self.assertEqual(self.readme.count(begin), 1)
        i = self.readme.index(begin) + len(begin)
        return self.readme[i : self.readme.index(end)].strip()

    def test_table7_is_rendered(self):
        self.assertEqual(
            self._block(readme_numbers.TABLE7_BEGIN, readme_numbers.TABLE7_END),
            readme_numbers.render_table7(self.document),
            "Table 7 in README.md differs from results.json",
        )

    def test_table8_is_rendered(self):
        self.assertEqual(
            self._block(readme_numbers.TABLE8_BEGIN, readme_numbers.TABLE8_END),
            readme_numbers.render_table8(self.document),
            "Table 8 in README.md differs from results.json",
        )

    def test_switch_table_is_rendered(self):
        begin = self.readme.index(readme_numbers.SWITCH_BEGIN)
        end = self.readme.index(readme_numbers.SWITCH_END)
        block = self.readme[begin + len(readme_numbers.SWITCH_BEGIN) : end].strip()
        self.assertEqual(
            block,
            readme_numbers.render_switch_table(),
            "Table 8b in README.md differs from results/model_switch.json",
        )
        self.assertEqual(self.readme.count(readme_numbers.SWITCH_BEGIN), 1)

    def test_seed_table_is_rendered(self):
        n = self.readme.count(readme_numbers.SEEDS_BEGIN)
        self.assertEqual(n, self.readme.count(readme_numbers.SEEDS_END))
        self.assertLessEqual(n, 1)
        if n == 0:
            self.assertFalse(
                readme_numbers.has_seeds(self.document),
                "results.json carries seed ensembles but README.md has no "
                "seeds block (§5.13)",
            )
            return
        begin = self.readme.index(readme_numbers.SEEDS_BEGIN)
        end = self.readme.index(readme_numbers.SEEDS_END)
        block = self.readme[begin + len(readme_numbers.SEEDS_BEGIN) : end].strip()
        self.assertEqual(block, readme_numbers.render_seed_table(self.document))

    def test_seed_table_without_ensembles_is_not_measured(self):
        doc = {"points": [{"core": "x", "coremark_per_joule": 1.0}]}
        self.assertEqual(readme_numbers.render_seed_table(doc), "Not yet measured.")

    def test_seed_table_columns_from_samples(self):
        doc = {
            "points": [
                {
                    "core": "a",
                    "coremark_per_joule": 1000.0,
                    "coremark_per_joule_2sigma": 20.0,
                    "power_2sigma_w": 0.0012,
                    "seed_samples": [
                        {"seed": "own", "coremark_per_joule": 1000.0},
                        {"seed": "11", "coremark_per_joule": 990.0},
                    ],
                }
            ]
        }
        table = readme_numbers.render_seed_table(doc)
        self.assertIn("| Core | own draw | seed 11 |", table)
        self.assertIn("| a | 1,000 | 990 | ±20 | 2.0 % | ±1.20 |", table)

    def test_table1_markers_unique(self):
        self.assertEqual(self.readme.count(readme_numbers.TABLE1_BEGIN), 1)
        self.assertEqual(self.readme.count(readme_numbers.TABLE1_END), 1)


if __name__ == "__main__":
    unittest.main()
