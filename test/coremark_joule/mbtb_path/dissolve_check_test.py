"""ADDITIONAL_ODB_FILES on the test parent: the generated macro is gone,
its 735 cells are in the parent, every one FIRM, dont_touch and on a row
of its own orientation, and the placement is legal."""

import sys
import unittest


def facts(path):
    out = {}
    for line in open(path):
        k, v = line.split()
        out[k] = v
    return out


class DissolveTest(unittest.TestCase):
    def test_reports(self):
        for path in sys.argv[1:]:
            with self.subTest(path=path):
                f = facts(path)
                self.assertEqual(f["macros"], "0", "a macro was left")
                self.assertEqual(f["cells"], "735", "not every generated cell arrived")
                self.assertEqual(f["not_firm"], "0")
                self.assertEqual(
                    f["touchable"], "0", "an interior cell is not dont_touch"
                )
                self.assertEqual(f["off_row"], "0", "a cell is off its row")
                self.assertEqual(f["check_placement"], "ok")


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
