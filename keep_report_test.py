"""keep_report.py on made-up inputs: a top with logic of its own and a
big submodule that is not kept, a kept module with a submodule instanced
twice, and a memory black box."""

import json
import os
import tempfile
import unittest

import keep_report

RTLIL = r"""attribute \blackbox 1
module \ram
end
attribute \top 1
module \Top
  cell \Big$Top.big \big
  end
  cell \Kept$Top.kept \kept
  end
  cell $add $1
  end
end
module \Big$Top.big
  cell \Leaf \l
  end
end
module \Kept$Top.kept
  cell \Leaf \a
  end
  cell \Leaf \b
  end
  cell \ram \mem
  end
end
module \Leaf
end
"""

COSTS = """5. Executing KEEP_HIERARCHY pass.
Keeping Leaf (estimated size above threshold: 10 > 1).
Keeping Big$Top.big (estimated size above threshold: 500 > 1).
Keeping Kept$Top.kept (estimated size above threshold: 30 > 1).
Keeping Top (estimated size above threshold: 100 > 1).
"""

# A partition in yosys 0.68's stat format, the log lines stamped as
# --@bazel-orfs//:log_timestamps stamps them.
TOP_STAT = r"""=== partition Top
[  516.1] End of script. Logfile hash: 5f, time: 514.66s, user: 97.48s
[  516.1] Time spent: 80% 1x abc (411 sec), 4% 63x opt_expr (21 sec), ...
Elapsed time: 8:35.05[h:]min:sec. CPU time: user 506.68 sys 3.47 (99%).

=== \Top ===

        +----------------------------Count including submodules.
        |        +-------------------Area including submodules.
        |        |        +----------Local count, excluding submodules.
        |        |        |        +-Local area, excluding submodules.
        |        |        |        |
     1200    90.5     1200     90.5 cells
        1        -        1        -   Kept

   Chip area for module '\Top': 90.500000
"""

# The older stat format, and no Elapsed line: End of script's time.
KEPT_STAT = r"""=== partition \Kept$Top.kept
End of script. Logfile hash: 9b, time: 61.00s, user: 59.52s
Time spent: 58% 1x abc (35 sec), 24% 1x share (14 sec), ...
=== Kept$Top.kept ===

   Number of wires:                 10
   Number of cells:                 77
   Chip area for module '\Kept$Top.kept': 7.250000
"""


class KeepReportTest(unittest.TestCase):
    def setUp(self):
        self.children, self.blackboxes = keep_report.read_hierarchy(
            RTLIL.splitlines(True)
        )
        self.costs = keep_report.read_costs(COSTS.splitlines())
        self.kept = keep_report.kept_set(["Kept"], self.children) - {"Top"}
        self.sizes = keep_report.Sizes(
            self.children, self.costs, self.kept | self.blackboxes
        )

    def test_hierarchy(self):
        self.assertEqual(self.blackboxes, {"ram"})
        self.assertEqual(self.children["Kept$Top.kept"], {"Leaf": 2, "ram": 1})
        self.assertEqual(self.children["Top"], {"Big$Top.big": 1, "Kept$Top.kept": 1})

    def test_kept_names_reach_every_spelling(self):
        self.assertEqual(self.kept, {"Kept$Top.kept"})

    def test_sizes_stop_at_kept_modules(self):
        self.assertEqual(self.sizes.size("Top"), 100 + 500 + 10)
        self.assertEqual(self.sizes.size("Kept$Top.kept"), 30 + 2 * 10)

    def test_candidates_count_instances(self):
        self.assertEqual(self.sizes.candidates("Kept$Top.kept"), {"Leaf": 2})
        self.assertEqual(self.sizes.candidates("Top"), {"Big$Top.big": 1, "Leaf": 1})

    def test_keep_names(self):
        names = keep_report.keep_names(list(self.children))
        self.assertEqual(names["Big$Top.big"], "Big")
        self.assertEqual(names["Leaf"], "Leaf")

    def test_stats_both_formats(self):
        stats = keep_report.read_stats([TOP_STAT, KEPT_STAT])
        self.assertEqual(
            stats["Top"],
            {
                "seconds": 515.05,
                "pass": "abc",
                "pass_seconds": 411,
                "cells": 1200,
                "area": 90.5,
            },
        )
        self.assertEqual(
            stats["Kept$Top.kept"],
            {
                "seconds": 61.0,
                "pass": "abc",
                "pass_seconds": 35,
                "cells": 77,
                "area": 7.25,
            },
        )

    def test_report_names_the_top_and_big(self):
        stats = keep_report.read_stats([TOP_STAT, KEPT_STAT])
        text = keep_report.report(
            "Top", ["Kept"], self.children, self.blackboxes, self.costs, stats
        )
        hint = text.splitlines()[2]
        self.assertIn("Critical path: (top) Top", hint)
        self.assertIn("abc 411 s", hint)
        self.assertIn("Keeping Big would move 84%", hint)
        self.assertIn(
            "| (top) Top | 515.0 | abc 411 s | 1,200 | 90.5 | 610 | 100 |", text
        )
        self.assertIn("| Big | 1 | 510 | 510 | 84% |", text)
        self.assertIn("| Leaf | 2 | 10 | 20 | 40% |", text)

    def test_a_partition_with_nothing_to_keep(self):
        costs = {"Top": 100}
        children = {"Top": {}}
        stats = {"Top": {"seconds": 9.0}}
        text = keep_report.report("Top", [], children, set(), costs, stats)
        self.assertIn("keeping more modules will not split it", text)

    def test_main(self):
        with tempfile.TemporaryDirectory() as d:
            paths = {}
            for name, text in [
                ("canon.rtlil", RTLIL),
                ("costs.txt", COSTS),
                ("top.txt", TOP_STAT),
                ("kept.txt", KEPT_STAT),
                ("kept.json", json.dumps({"modules": ["Kept"]})),
            ]:
                paths[name] = os.path.join(d, name)
                with open(paths[name], "w") as f:
                    f.write(text)
            out = os.path.join(d, "keep_report.md")
            keep_report.main(
                [
                    "--top=Top",
                    "--kept=" + paths["kept.json"],
                    "--rtlil=" + paths["canon.rtlil"],
                    "--costs=" + paths["costs.txt"],
                    "--out=" + out,
                    paths["top.txt"],
                    paths["kept.txt"],
                ]
            )
            with open(out) as f:
                self.assertTrue(f.read().startswith("# Keep report: Top"))


if __name__ == "__main__":
    unittest.main()
