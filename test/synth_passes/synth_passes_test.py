"""The synth_passes output group of PassesTop's partitioned synthesis."""

import os
import re
import sys
import unittest

FILES = sys.argv[1:]
PARTITION = re.compile(r"^\s*[\d.]+s\s+(\S+)$")
PASS = re.compile(r"^\s+[\d.]+s\s+(\S+) (\S+)$")


def read(path):
    with open(path) as f:
        return f.read()


class SynthPassesTest(unittest.TestCase):
    def setUp(self):
        by_name = {}
        for path in FILES:
            by_name.setdefault(os.path.basename(path), []).append(path)
        (summary,) = by_name.pop("synth_passes.txt")
        self.summary = read(summary).splitlines()
        self.logs = {
            name: read(paths[0])
            for name, paths in by_name.items()
            if name.endswith(".log")
        }

    def test_every_partition_has_its_log(self):
        self.assertEqual(
            sorted(self.logs),
            ["partition_Adder.log", "partition_Mult.log", "partition_top.log"],
        )
        for name, text in self.logs.items():
            self.assertIn("Executing ABC pass", text, name)

    def test_every_partition_lists_passes_its_log_executed(self):
        partitions = {}
        current = None
        for line in self.summary:
            p = PASS.match(line)
            if p:
                partitions[current].append(p.groups())
                continue
            m = PARTITION.match(line)
            self.assertTrue(m, line)
            current = m.group(1)
            partitions[current] = []
        self.assertEqual(len(partitions), len(self.logs), self.summary)
        logs = "".join(self.logs.values())
        for partition, passes in partitions.items():
            self.assertIn("abc", [name for _, name in passes], partition)
            for number, name in passes:
                self.assertIn(f"\n{number}. Executing {name.upper()} pass", logs)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
