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

# Partitions for the slow-partition rule: over a 600 s budget with no
# dominant pass, abc-dominated, extract_fa at exactly 90%, and fine.
SLOW_STATS = r"""=== partition Top
End of script. Logfile hash: 01, time: 10.00s, user: 9.00s
Time spent: 50% 1x abc (5 sec), ...
=== partition Slow
End of script. Logfile hash: 02, time: 900.00s, user: 899.00s
Time spent: 40% 1x abc (360 sec), 30% 1x opt (270 sec), ...
=== partition Abc
End of script. Logfile hash: 03, time: 400.00s, user: 399.00s
Time spent: 95% 1x abc (380 sec), ...
=== partition Fa
End of script. Logfile hash: 04, time: 100.00s, user: 99.00s
Time spent: 90% 1x extract_fa (90 sec), ...
=== partition Fine
End of script. Logfile hash: 05, time: 50.00s, user: 49.00s
Time spent: 60% 1x abc (30 sec), ...
"""

# Partitions with synth_searches.py's lines: one whose extract_fa took a
# third of its wall time for three adders and whose share merged nothing,
# one whose searches paid off and ran the area script, one whose
# searches were off, and one from before the searches were recorded.
SEARCH_STATS = r"""=== partition Top
End of script. Logfile hash: 01, time: 10.00s, user: 9.00s
Using ABC speed script.
search abc seconds=4.0
=== partition Mux
End of script. Logfile hash: 02, time: 300.00s, user: 299.00s
Using ABC speed script.
Time spent: 40% 1x abc (120 sec), ...
search extract_fa seconds=100.0 full=2 half=1
search share seconds=12.5 candidates=40 merged=0
search abc seconds=120.0
=== partition Alu
Using ABC area script.
End of script. Logfile hash: 03, time: 200.00s, user: 199.00s
Time spent: 95% 1x abc (190 sec), ...
search extract_fa seconds=80.0 full=640 half=64
search share seconds=5.0 candidates=4 merged=2
search abc seconds=190.0
=== partition Off
End of script. Logfile hash: 04, time: 50.00s, user: 49.00s
Using ABC script /abc/mux.script.
search abc seconds=40.0
=== partition Old
End of script. Logfile hash: 05, time: 20.00s, user: 19.00s
Using ABC speed script.
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

    def test_slow_partitions(self):
        children = {"Top": {"Slow": 1, "Abc": 1, "Fine": 1, "Fa": 1}}
        for m in ("Slow", "Abc", "Fine", "Fa"):
            children[m] = {}
        costs = {m: 10 for m in children}
        stats = keep_report.read_stats([SLOW_STATS])
        text = keep_report.report(
            "Top",
            ["Slow", "Abc", "Fine", "Fa"],
            children,
            set(),
            costs,
            stats,
            budget=600,
        )
        slow = text.split("## Slow partitions", 1)[1]
        self.assertIn("indicative", slow)
        self.assertIn("- **Slow**: 900.0 s, over the 600 s budget.", slow)
        self.assertIn("split it: see its keep candidates below", slow)
        self.assertIn("- **Abc**: abc takes 95% of its wall time.", slow)
        self.assertIn(
            "try ABC_AREA=1 for this partition (per-partition arguments)", slow
        )
        self.assertIn("pre-map them (muxcover)", slow)
        self.assertIn("- **Fa**: extract_fa takes 90% of its wall time.", slow)
        self.assertIn("`extract_fa` pass", slow)
        self.assertNotIn("Fine", slow)
        self.assertNotIn("Top", slow)

    def test_no_budget_flags_only_dominant_passes(self):
        children = {"Top": {"Slow": 1}, "Slow": {}}
        stats = keep_report.read_stats([SLOW_STATS])
        text = keep_report.report("Top", ["Slow"], children, set(), {}, stats)
        self.assertNotIn("Slow partitions", text)

    def test_searches_parsed(self):
        stats = keep_report.read_stats([SEARCH_STATS])
        self.assertEqual(
            stats["Mux"]["searches"],
            {
                "extract_fa": {"seconds": 100.0, "full": 2, "half": 1},
                "share": {"seconds": 12.5, "candidates": 40, "merged": 0},
                "abc": {"seconds": 120.0, "script": "speed"},
            },
        )
        self.assertNotIn("searches", stats["Old"])

    def search_report(self):
        modules = ["Mux", "Alu", "Off", "Old"]
        children = {"Top": {m: 1 for m in modules}}
        for m in modules:
            children[m] = {}
        stats = keep_report.read_stats([SEARCH_STATS])
        return keep_report.report("Top", modules, children, set(), {}, stats)

    def test_searches_columns(self):
        text = self.search_report()
        self.assertIn(
            "| Own gates | Searches: extract_fa (s) | Full/half adders "
            "| share (s) | Merged/candidates | ABC script | ABC (s) |",
            text,
        )
        self.assertIn("| 100.0 | 2/1 | 12.5 | 0/40 | speed | 120.0 |", text)
        self.assertIn("| 80.0 | 640/64 | 5.0 | 2/4 | area | 190.0 |", text)
        self.assertIn("| off |  | off |  | custom | 40.0 |", text)
        self.assertIn("| ? | ? | ? | ? | ? | ? |", text)

    def test_no_searches_no_columns(self):
        stats = keep_report.read_stats([KEPT_STAT])
        text = keep_report.report(
            "Top", ["Kept"], self.children, self.blackboxes, self.costs, stats
        )
        self.assertNotIn("Searches", text)

    def test_search_suggestions(self):
        slow = self.search_report().split("## Slow partitions", 1)[1]
        mux = slow.split("- **Mux**", 1)[1].split("- **", 1)[0]
        self.assertIn(": a search costs time and finds little.", mux)
        self.assertIn(
            "SKIP_EXTRACT_FA=1 for this partition: extract_fa took 100.0 s "
            "(33% of its wall time) and found 2 full and 1 half adders",
            mux,
        )
        self.assertIn(
            "SYNTH_ARGS=-noshare for this partition: share took 12.5 s over "
            "40 candidates and merged none",
            mux,
        )
        alu = slow.split("- **Alu**", 1)[1]
        self.assertIn("abc takes 95% of its wall time", alu)
        self.assertNotIn("ABC_AREA", alu)
        self.assertNotIn("SKIP_EXTRACT_FA", alu)
        self.assertNotIn("noshare", alu)
        self.assertNotIn("**Off**", slow)
        self.assertNotIn("**Old**", slow)
        self.assertNotIn("**(top) Top**", slow)

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
                    "--budget=1",
                    paths["top.txt"],
                    paths["kept.txt"],
                ]
            )
            with open(out) as f:
                text = f.read()
            self.assertTrue(text.startswith("# Keep report: Top"))
            self.assertIn("- **(top) Top**: 515.0 s, over the 1 s budget.", text)


if __name__ == "__main__":
    unittest.main()
