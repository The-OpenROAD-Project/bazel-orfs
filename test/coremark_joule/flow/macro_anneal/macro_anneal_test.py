#!/usr/bin/env python3
"""macro_anneal.py on a synthetic inventory: legal, on-track, deterministic."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_anneal  # noqa: E402

DBU = 1000


def inventory(n_a=8, n_b=6, n_single=1):
    """Two bank groups under different prefixes, one singleton, one logic hub."""
    lines = [
        "# macro_anneal inventory v1",
        "die 0 0 400000 400000 dbu {}".format(DBU),
        "core 10000 10000 390000 390000",
        "mfg_grid 1",
        "site 54 270",
        "track M4 V 24 48",
        "track M5 H 20 40",
        # width 14820 height 21000, pin x at 100 on M4, pin y at 70 on M5
        "master array_64x114 14820 21000 M4 100 M5 70",
        "master array_512x17 8930 42000 M4 100 M5 70",
        "module frontend/bpu/tage 500000000",
        "module frontend/ifu 900000000",
        "module memblock/dcache 700000000",
    ]
    for i in range(n_a):
        lines.append("macro frontend/bpu/tage/t{} array_512x17".format(i))
        lines.append("net frontend/bpu/tage/t{} frontend/bpu/tage 30".format(i))
        lines.append("net frontend/bpu/tage/t{} frontend/ifu 5".format(i))
    for i in range(n_b):
        lines.append("macro memblock/dcache/bank{} array_64x114".format(i))
        lines.append("net memblock/dcache/bank{} memblock/dcache 40".format(i))
    for i in range(n_single):
        lines.append("macro memblock/pht/one{} array_64x114".format(i))
    return "\n".join(lines) + "\n"


def run(text, **kw):
    inv = macro_anneal.Inventory.parse(text)
    chan = int(kw.get("channel_um", 4.0) * DBU)
    gap = int(kw.get("block_gap_um", 10.8) * DBU)
    blocks, residual = macro_anneal.build_blocks(
        inv, kw.get("depth", 3), kw.get("min_cluster", 4), chan, kw.get("fill", 0.6)
    )
    weights = macro_anneal.build_weights(inv, blocks, kw.get("depth", 3), 1000.0)
    anneal = macro_anneal.Anneal(inv, blocks, weights, gap, kw.get("seed", 1), 400)
    order, cost = anneal.run()
    placed = macro_anneal.placements(inv, blocks, chan)
    return inv, blocks, residual, placed, cost


class TileTest(unittest.TestCase):
    def test_near_square(self):
        cols, rows, w, h = macro_anneal.tile_shape(64, 8930, 42000, 4400)
        self.assertEqual(cols * rows >= 64, True)
        self.assertLess(max(w, h) / float(min(w, h)), 2.0)

    def test_single_bank(self):
        self.assertEqual(macro_anneal.tile_shape(1, 100, 200, 10), (1, 1, 100, 200))

    def test_channel_is_between_banks_only(self):
        cols, rows, w, h = macro_anneal.tile_shape(4, 100, 100, 10)
        self.assertEqual((cols, rows, w, h), (2, 2, 210, 210))


class PlacementTest(unittest.TestCase):
    def test_clusters_and_residual(self):
        inv, blocks, residual, placed, _ = run(inventory())
        macro_blocks = [b for b in blocks if b.is_macro()]
        self.assertEqual(
            sorted(b.key for b in macro_blocks),
            ["frontend/bpu/tage", "memblock/dcache"],
        )
        self.assertEqual(residual, ["memblock/pht/one0"])
        self.assertEqual(len(placed), 14)
        ballast = [b for b in blocks if not b.is_macro()]
        self.assertEqual(
            sorted(b.key for b in ballast),
            ["frontend/bpu/tage", "frontend/ifu", "memblock/dcache"],
        )

    def test_legal_inside_core_no_overlap(self):
        inv, blocks, _, placed, _ = run(inventory())
        self.assertEqual(macro_anneal.check_legal(inv, blocks, placed), [])

    def test_pins_on_tracks(self):
        inv, blocks, _, placed, _ = run(inventory())
        for inst, master, x, y in placed:
            m = inv.masters[master]
            self.assertEqual((x + m["pox"] - 24) % 48, 0, inst)
            self.assertEqual((y + m["poy"] - 20) % 40, 0, inst)

    def test_banks_abut_halo_to_halo_and_blocks_keep_the_gap(self):
        # Inside a block, neighbouring banks are one channel apart, give or
        # take the track snap of under a site; between blocks, at least the
        # gap. A leftover sliver of rows between banks is what pdngen
        # cannot power.
        inv, blocks, _, placed, _ = run(inventory(), channel_um=4.0, block_gap_um=10.8)
        by_block = {}
        for inst, master, x, y in placed:
            for b in blocks:
                if inst in b.macros:
                    by_block.setdefault(id(b), []).append((x, y, inv.masters[master]))
        for banks in by_block.values():
            xs = sorted({x for x, _, _ in banks})
            for a, b in zip(xs, xs[1:]):
                gap = b - a - banks[0][2]["w"]
                self.assertGreaterEqual(gap, 4000)
                self.assertLess(gap, 4000 + 48)
        rects = [(b.x, b.y, b.x + b.w, b.y + b.h) for b in blocks]
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, c = rects[i], rects[j]
                dx = max(c[0] - a[2], a[0] - c[2])
                dy = max(c[1] - a[3], a[1] - c[3])
                self.assertGreaterEqual(max(dx, dy), 10800)

    def test_deterministic(self):
        a = run(inventory(), seed=3)[3]
        b = run(inventory(), seed=3)[3]
        self.assertEqual(a, b)

    def test_seed_changes_something_or_nothing_but_stays_legal(self):
        inv, blocks, _, placed, _ = run(inventory(), seed=7)
        self.assertEqual(macro_anneal.check_legal(inv, blocks, placed), [])

    def test_connected_blocks_end_up_close(self):
        # The TAGE banks talk to their own logic 30 pins each and to ifu 5;
        # after annealing the tage ballast must be nearer than the dcache one.
        inv, blocks, _, _, _ = run(inventory(), seed=1)
        by = {(b.key, b.is_macro()): b for b in blocks}
        tage = by[("frontend/bpu/tage", True)]
        near = by[("frontend/bpu/tage", False)]
        far = by[("memblock/dcache", False)]
        d = lambda a, b: abs(a.cx - b.cx) + abs(a.cy - b.cy)
        self.assertLess(d(tage, near), d(tage, far))

    def test_overrun_is_reported_not_emitted(self):
        text = inventory().replace(
            "core 10000 10000 390000 390000", "core 10000 10000 60000 60000"
        )
        inv, blocks, _, placed, cost = run(text)
        self.assertTrue(macro_anneal.check_legal(inv, blocks, placed))
        self.assertGreater(cost, 1e6)


class EmitTest(unittest.TestCase):
    def test_tcl_has_place_macro_and_firm(self):
        inv, blocks, residual, placed, _ = run(inventory())
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "p.tcl")
            macro_anneal.emit_tcl(inv, placed, residual, out)
            tcl = open(out).read()
        self.assertEqual(tcl.count("place_macro -macro_name"), 14)
        self.assertIn("setPlacementStatus FIRM", tcl)
        self.assertIn("1 macros left to rtl_macro_placer", tcl)
        self.assertNotIn("memblock/pht/one0", tcl)

    def test_main_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            inv_path = os.path.join(d, "inv.txt")
            with open(inv_path, "w") as f:
                f.write(inventory())
            out = os.path.join(d, "p.tcl")
            metrics = os.path.join(d, "m.json")
            rc = macro_anneal.main(
                [
                    "x",
                    "--inventory",
                    inv_path,
                    "--out",
                    out,
                    "--metrics",
                    metrics,
                    "--iterations",
                    "300",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))
            self.assertIn('"residual": 1', open(metrics).read())


if __name__ == "__main__":
    unittest.main()
