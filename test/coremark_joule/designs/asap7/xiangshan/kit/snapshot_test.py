"""snapshot.py's arithmetic, and the snapshot in kit/snapshot/ against the
kit's netlist: one floorplan, with and without macros, that places every
macro of the netlist once."""

import csv
import json
import os
import re
import unittest

import snapshot

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "snapshot")


def def_components(path):
    """name -> (master, x, y) in DBU, and the DIEAREA and units."""
    text = open(path).read()
    dbu = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", text).group(1))
    die = [
        int(v)
        for v in re.search(
            r"DIEAREA \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", text
        ).groups()
    ]
    comps = {}
    for m in re.finditer(
        r"^- (\S+) (\S+) \+ FIXED \( (-?\d+) (-?\d+) \) (\S+) ;$", text, re.M
    ):
        comps[m.group(1)] = (m.group(2), int(m.group(3)), int(m.group(4)))
    n = int(re.search(r"COMPONENTS (\d+) ;", text).group(1))
    return comps, die, dbu, n


class Squeeze(unittest.TestCase):
    def test_macros_keep_their_length_and_the_ends_map(self):
        f, k = snapshot.squeeze([(10, 30), (30, 50), (70, 80)], 100, 80)
        self.assertAlmostEqual(f(0), 0)
        self.assertAlmostEqual(f(100), 80)
        self.assertAlmostEqual(f(30) - f(10), 20)
        self.assertAlmostEqual(f(50) - f(30), 20)
        self.assertAlmostEqual(f(80) - f(70), 10)
        self.assertAlmostEqual(k, (80 - 50) / (100 - 50))

    def test_abutting_stays_abutting_and_apart_stays_apart(self):
        f, _ = snapshot.squeeze([(0, 10), (10, 20), (40, 50)], 100, 60)
        self.assertAlmostEqual(f(10), 10)
        self.assertGreater(f(40), f(20))

    def test_monotone(self):
        f, _ = snapshot.squeeze([(5, 15), (40, 60)], 100, 70)
        xs = [i * 0.5 for i in range(201)]
        ys = [f(x) for x in xs]
        self.assertEqual(ys, sorted(ys))

    def test_no_room_stops(self):
        with self.assertRaises(SystemExit):
            snapshot.squeeze([(0, 90)], 100, 80)


class Overlaps(unittest.TestCase):
    def test_finds_and_ignores(self):
        ms = [
            {"name": "a", "box": [0, 0, 10, 10]},
            {"name": "b", "box": [10, 0, 20, 10]},
            {"name": "c", "box": [5, 5, 15, 15]},
        ]
        found = {tuple(sorted(p)) for p in snapshot.overlaps(ms)}
        self.assertEqual(found, {("a", "c"), ("b", "c")})


class TheSnapshot(unittest.TestCase):
    """kit/snapshot/ as checked in, against the kit's netlist (pinned/)."""

    @classmethod
    def setUpClass(cls):
        cls.report = json.load(open(os.path.join(SNAP, "snapshot.json")))
        facts = json.load(open(os.path.join(HERE, "pinned", "facts.json")))
        cls.netlist = {i: m for m, d in facts["macros"].items() for i in d["instances"]}
        cls.blocks = cls.report["floorplan"]["blocks"]

    def test_every_netlist_macro_placed_once_flat(self):
        comps, die, dbu, n = def_components(
            os.path.join(SNAP, "floorplan", "flat", "XSTile.def")
        )
        self.assertEqual(n, len(comps))
        self.assertEqual({k: v[0] for k, v in comps.items()}, self.netlist)
        rows = list(csv.DictReader(open(os.path.join(SNAP, "floorplan", "macros.csv"))))
        self.assertEqual({r["name"]: r["master"] for r in rows}, self.netlist)

    def test_flat_has_no_overlap_and_stays_on_the_die(self):
        rows = list(csv.DictReader(open(os.path.join(SNAP, "floorplan", "macros.csv"))))
        ms = [
            {"name": r["name"], "box": [float(r[k]) for k in ("x0", "y0", "x1", "y1")]}
            for r in rows
        ]
        self.assertEqual(snapshot.overlaps(ms), [])
        _, die, dbu, _ = def_components(
            os.path.join(SNAP, "floorplan", "flat", "XSTile.def")
        )
        for m in ms:
            self.assertGreaterEqual(m["box"][0] * dbu, die[0] - 1, m["name"])
            self.assertGreaterEqual(m["box"][1] * dbu, die[1] - 1, m["name"])
            self.assertLessEqual(m["box"][2] * dbu, die[2] + 1, m["name"])
            self.assertLessEqual(m["box"][3] * dbu, die[3] + 1, m["name"])

    def test_with_and_without_macros_is_one_floorplan(self):
        """Each block's macro, at the block's origin in the parent, is where
        the flat floorplan has it; the parent's own macros are the same in
        both; every netlist macro is in exactly one block or the parent."""
        flat, _, dbu, _ = def_components(
            os.path.join(SNAP, "floorplan", "flat", "XSTile.def")
        )
        top, _, _, _ = def_components(
            os.path.join(SNAP, "floorplan", "hier", "XSTile.def")
        )
        seen = set()
        for b, x in self.blocks.items():
            inst = x["instance"]
            self.assertEqual(top[inst][0], b)
            comps, die, _, _ = def_components(
                os.path.join(SNAP, "floorplan", "hier", b + ".def")
            )
            self.assertAlmostEqual(die[2] / dbu, x["footprint_um"][0], places=2)
            for name, (master, cx, cy) in comps.items():
                full = inst + "/" + name
                self.assertNotIn(full, seen)
                seen.add(full)
                self.assertEqual(flat[full][0], master)
                self.assertLessEqual(abs(flat[full][1] - (top[inst][1] + cx)), 1, full)
                self.assertLessEqual(abs(flat[full][2] - (top[inst][2] + cy)), 1, full)
        for name, v in top.items():
            if v[0] in self.blocks:
                continue
            self.assertEqual(flat[name], v)
            seen.add(name)
        self.assertEqual(seen, set(self.netlist))

    def test_the_kpi_periods(self):
        """The snapshot's periods are the KPI row's it names."""
        row = self.report["kpi_row"]
        parts = self.report["parts"]
        self.assertEqual(parts["XSTile"]["kpi"]["period_ps"], row["parent_ps"])
        for b, ps in row["blocks"].items():
            self.assertEqual(parts[b]["kpi"]["period_ps"], ps, b)


if __name__ == "__main__":
    unittest.main()
