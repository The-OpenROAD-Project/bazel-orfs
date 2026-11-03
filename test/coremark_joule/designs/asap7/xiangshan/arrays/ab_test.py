"""README.md's A/B table is ab.json: the same blocks, minutes and
periods, so the kit's README (which reads ab.json) and this package's
README cannot disagree."""

import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def readme_rows():
    rows = []
    for line in open(os.path.join(HERE, "README.md")):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[-1] == "dominates":
            rows.append(
                {
                    "block": cells[0].split()[0],
                    "a_min": float(cells[1]),
                    "b_min": float(cells[2]),
                    "a_ps": float(cells[3].replace(",", "")),
                    "b_ps": float(cells[4].replace(",", "")),
                }
            )
    return rows


class AbTest(unittest.TestCase):
    def test_readme_is_ab_json(self):
        ab = json.load(open(os.path.join(HERE, "ab.json")))["rows"]
        strip = [
            {k: r[k] for k in ("block", "a_min", "b_min", "a_ps", "b_ps")} for r in ab
        ]
        self.assertTrue(strip)
        self.assertEqual(readme_rows(), strip)


if __name__ == "__main__":
    unittest.main()
