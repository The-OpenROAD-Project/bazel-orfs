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


# ASAP7's M5 stripes: pitch 5.4, first pair 0.3 from the core edge, a
# VDD+VSS pair spanning 0.312.
STRAPS = macro_anneal.Straps(5400, 300, 312, 200)


def run(text, straps=None, **kw):
    inv = macro_anneal.Inventory.parse(text)
    chan = int(kw.get("channel_um", 4.0) * DBU)
    gap = int(kw.get("block_gap_um", 10.8) * DBU)
    blocks, residual = macro_anneal.build_blocks(
        inv,
        kw.get("depth", 3),
        kw.get("min_cluster", 4),
        chan,
        kw.get("fill", 0.6),
        straps,
    )
    weights = macro_anneal.build_weights(inv, blocks, kw.get("depth", 3), 1000.0)
    anneal = macro_anneal.Anneal(inv, blocks, weights, gap, kw.get("seed", 1), 400)
    order, cost = anneal.run()
    placed = macro_anneal.placements(inv, blocks, chan, straps)
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
        for inst, master, x, y, _ in placed:
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
        for inst, master, x, y, _ in placed:
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


class StrapTest(unittest.TestCase):
    def narrow_inventory(self):
        # array_64x16 is 4.18 wide: narrower than a 5.4 stripe pitch.
        text = inventory().replace(
            "master array_512x17 8930 42000 M4 100 M5 70",
            "master array_512x17 4180 11200 M4 100 M5 70",
        )
        return text

    def test_wide_macro_never_misses(self):
        self.assertFalse(STRAPS.can_miss(14820))
        self.assertTrue(STRAPS.can_miss(4180))

    def test_every_narrow_bank_holds_a_stripe_pair(self):
        inv, blocks, _, placed, _ = run(self.narrow_inventory(), straps=STRAPS)
        narrow = [(x, m) for _, m, x, _, _ in placed if m == "array_512x17"]
        self.assertEqual(len(narrow), 8)
        for x, m in narrow:
            self.assertTrue(
                STRAPS.pair_inside(inv.core[0], x, inv.masters[m]["w"]),
                "bank at {} has no stripe pair inside its rails".format(x),
            )
        # And they are still on their pin tracks.
        for inst, master, x, y, _ in placed:
            self.assertEqual((x + inv.masters[master]["pox"] - 24) % 48, 0, inst)

    def test_narrow_banks_step_by_a_strap_multiple(self):
        inv, blocks, _, _, _ = run(self.narrow_inventory(), straps=STRAPS)
        (b,) = [b for b in blocks if b.is_macro() and b.master == "array_512x17"]
        self.assertEqual(b.step_x % 5400, 0)
        self.assertEqual(b.step_x % 48, 0)
        self.assertGreaterEqual(b.step_x, 4180 + 4000)

    def test_without_strap_data_nothing_changes(self):
        a = run(self.narrow_inventory())[3]
        b = run(self.narrow_inventory(), straps=macro_anneal.Straps())[3]
        self.assertEqual(a, b)

    def test_pair_inside_arithmetic(self):
        # Core at x0=1026 dbu (asap7's snapped core), stripes at 1326 + 5400 k.
        s = STRAPS
        self.assertFalse(s.pair_inside(1026, 88426, 4180))
        self.assertTrue(s.pair_inside(1026, 92500, 4180))


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


class LatticeTest(unittest.TestCase):
    """asap7's grids: pins on two layers per axis, one of them irregular.

    M2's y tracks are seven patterns of period 270 (0.036 apart six
    times, then 0.045), M4's are 48 from 12; M3's x tracks 36 from 9, M5's
    48 from 12. The XiangShan take-16 parent failed pin_access on every
    macro because origins were snapped to the lowest layer only and
    macros were flipped regardless of their size (measured 2026-09-18).
    """

    def inventory(self, w=83232, h=83232, vlayers="M3 M5", hlayers="M2 M4"):
        lines = [
            "# macro_anneal inventory v1",
            "die 0 0 400000 400000 dbu {}".format(DBU),
            "core 10000 10000 390000 390000",
            "mfg_grid 1",
            "site 54 270",
            "track M3 V 9 36",
            "track M2 H 45 36",
        ]
        for origin in (45, 81, 117, 153, 189, 225, 270):
            lines.append("trackpat M2 H {} 37 270".format(origin))
        lines += [
            "trackpat M4 H 12 208 48",
            "trackpat M3 V 9 277 36",
            "trackpat M5 V 12 208 48",
            "master mock {} {} M3 9 M2 45".format(w, h),
            "pinlayers mock V {}".format(vlayers),
            "pinlayers mock H {}".format(hlayers),
            "edges mock 100 0 100 0",
            "module logic 500000000",
            "macro top/a mock",
            "macro top/b mock",
            "net top/a macro:top/b 100",
            "netedge top/a macro:top/b L 100",
        ]
        return "\n".join(lines)

    def test_residues_and_lattice(self):
        inv = macro_anneal.Inventory.parse(self.inventory())
        period, residues = macro_anneal.track_residues(inv, "M2", "H")
        self.assertEqual(period, 270)
        self.assertEqual(residues, [0, 45, 81, 117, 153, 189, 225])
        self.assertEqual(macro_anneal.lattice(inv, "mock", "V"), 144)
        self.assertEqual(macro_anneal.lattice(inv, "mock", "H"), 2160)

    def test_origin_is_a_lattice_multiple_for_every_flip(self):
        inv = macro_anneal.Inventory.parse(self.inventory())
        for orient in ("R0", "MX", "MY", "R180"):
            ox, oy = macro_anneal.macro_origin(inv, "mock", 10007, 10011, orient)
            self.assertEqual(ox % 144, 0, orient)
            self.assertEqual(oy % 2160, 0, orient)
            self.assertGreaterEqual(ox, 10007)
            self.assertGreaterEqual(oy, 10011)

    def test_flip_legality_is_a_property_of_the_size(self):
        # 83.232 um: R0 only. MX needs h == 1080 mod 2160 for M2 and M4
        # together; MY has no width M3 and M5 both accept.
        inv = macro_anneal.Inventory.parse(self.inventory())
        self.assertTrue(macro_anneal.flip_legal(inv, "mock", "R0"))
        self.assertFalse(macro_anneal.flip_legal(inv, "mock", "MX"))
        self.assertFalse(macro_anneal.flip_legal(inv, "mock", "MY"))
        self.assertFalse(macro_anneal.flip_legal(inv, "mock", "R180"))
        inv = macro_anneal.Inventory.parse(self.inventory(h=1080 + 38 * 2160))
        self.assertTrue(macro_anneal.flip_legal(inv, "mock", "MX"))
        self.assertFalse(macro_anneal.flip_legal(inv, "mock", "MY"))
        for w in range(83232, 83232 + 144):
            inv = macro_anneal.Inventory.parse(self.inventory(w=w))
            self.assertFalse(macro_anneal.flip_legal(inv, "mock", "MY"), w)
        # One vertical pin layer: w == 18 mod 36 mirrors M3 onto itself.
        inv = macro_anneal.Inventory.parse(self.inventory(w=83250, vlayers="M3"))
        self.assertTrue(macro_anneal.flip_legal(inv, "mock", "MY"))
        inv = macro_anneal.Inventory.parse(self.inventory(w=83232, vlayers="M3"))
        self.assertFalse(macro_anneal.flip_legal(inv, "mock", "MY"))

    def test_chooser_never_picks_an_illegal_flip(self):
        # a's left pins face b to its right: MY would win, but is illegal
        # at this width, so R0 stays.
        inv = macro_anneal.Inventory.parse(self.inventory())
        centres = {"top/b": (300000.0, 50000.0)}
        self.assertEqual(
            macro_anneal.choose_orientation(
                inv, "top/a", "mock", 10000, 10000, centres
            ),
            "R0",
        )
        inv = macro_anneal.Inventory.parse(self.inventory(w=83250, vlayers="M3"))
        self.assertEqual(
            macro_anneal.choose_orientation(
                inv, "top/a", "mock", 10000, 10000, centres
            ),
            "MY",
        )

    def test_banks_step_by_the_lattice(self):
        text = self.inventory()
        for i in range(4):
            text += "\nmacro top/bank/m{} mock\nnet top/bank/m{} logic 10".format(i, i)
        inv, blocks, _, placed, _ = run(text)
        for inst, master, x, y, _ in placed:
            self.assertEqual(x % 144, 0, inst)
            self.assertEqual(y % 2160, 0, inst)

    def test_without_patterns_the_old_snapping_holds(self):
        inv, blocks, _, placed, _ = run(inventory())
        for inst, master, x, y, _ in placed:
            m = inv.masters[master]
            self.assertEqual((x + m["pox"] - 24) % 48, 0, inst)


class ChannelTest(unittest.TestCase):
    """Pins are wires that leave through the channel along their side.

    asap7 densities: M2 and M4 along a horizontal channel, M3 and M5 along
    a vertical one, 48.6 tracks per um either way. A VectorDecodeChannel
    mock brings 557 pins to a side: 11.5 um of channel; two facing sides
    in a 4 um bank channel are the wall take 16's router found.
    """

    def inventory(self, n=4, chan_pins=557):
        lines = LatticeTest().inventory(w=40212, h=40212).splitlines()
        lines = [l for l in lines if not l.startswith(("edges", "macro", "net"))]
        lines.append("edges mock {} 0 {} 0".format(chan_pins, chan_pins))
        for i in range(n):
            lines.append("macro top/bank/m{} mock".format(i))
            lines.append("net top/bank/m{} logic 10".format(i))
        return "\n".join(lines)

    def test_escape_need(self):
        inv = macro_anneal.Inventory.parse(self.inventory())
        self.assertAlmostEqual(
            macro_anneal.layer_density(inv, "mock", "V") * 1000, 48.6, 1
        )
        self.assertEqual(macro_anneal.escape_need(inv, "mock", "L"), 11459)
        self.assertEqual(macro_anneal.escape_need(inv, "mock", "R"), 0)
        # MY puts the left pins on the right edge
        self.assertEqual(macro_anneal.escape_need(inv, "mock", "R", "MY"), 11459)
        self.assertEqual(macro_anneal.escape_need(inv, "mock", "B"), 11913)

    def test_narrow_bank_channel_is_reported(self):
        inv, blocks, _, placed, _ = run(self.inventory(), channel_um=4.0)
        short = macro_anneal.channel_shortfalls(inv, placed)
        self.assertTrue(short)
        a, ea, b, eb, width, need = short[0]
        self.assertEqual((ea, eb), ("R", "L"))
        self.assertLess(width, 5000)
        self.assertEqual(need, 11459)  # one facing side has pins, the other none

    def test_channel_auto_widens_the_bank_channel(self):
        text = self.inventory()
        inv = macro_anneal.Inventory.parse(text)
        blocks, _ = macro_anneal.build_blocks(
            inv, 3, 4, 4000, 0.6, None, channel_auto=True, gap=10800
        )
        b = [b for b in blocks if b.is_macro()][0]
        self.assertGreaterEqual(b.chan, 11459)
        self.assertGreaterEqual(b.step_x - inv.masters["mock"]["w"], 11459)
        self.assertGreaterEqual(b.halo, b.step_x - inv.masters["mock"]["w"])
        placed = macro_anneal.placements(inv, blocks, 4000)
        self.assertEqual(macro_anneal.channel_shortfalls(inv, placed), [])

    def test_halos_add_up_between_blocks(self):
        inv = macro_anneal.Inventory.parse(inventory())
        blocks, _ = macro_anneal.build_blocks(inv, 3, 4, 4000, 0.6, None)
        for b in blocks:
            b.halo = 7000
        packer = macro_anneal.Packer(inv, 10800)
        packer.pack(blocks, list(range(len(blocks))))
        row = sorted((b.x, b.x + b.w) for b in blocks if b.y == blocks[0].y)
        for (x0, x1), (n0, n1) in zip(row, row[1:]):
            self.assertEqual(n0 - x1, 14000)

    def test_without_auto_the_placement_is_unchanged(self):
        base = run(inventory())[3]
        inv = macro_anneal.Inventory.parse(inventory())
        blocks, _ = macro_anneal.build_blocks(inv, 3, 4, 4000, 0.6, None, gap=10800)
        self.assertTrue(all(b.halo is None for b in blocks))
        self.assertEqual(run(inventory())[3], base)


class OrientationTest(unittest.TestCase):
    """A macro whose pins all sit on one edge is flipped to face its connections."""

    def inventory(self):
        return "\n".join(
            [
                "# macro_anneal inventory v1",
                "die 0 0 400000 400000 dbu {}".format(DBU),
                "core 10000 10000 390000 390000",
                "mfg_grid 1",
                "site 54 270",
                "track M4 V 24 48",
                "track M5 H 20 40",
                "master left_pins 20000 20000 M4 100 M5 70",
                "edges left_pins 100 0 0 0",
                "module logic 500000000",
                # two singletons: a, whose pins are all on its left edge, and b
                # to be placed after it (to its right); a's pins connect to b.
                "macro top/a left_pins",
                "macro top/b left_pins",
                "net top/a macro:top/b 100",
                "netedge top/a macro:top/b L 100",
            ]
        )

    def test_pins_face_the_connected_macro(self):
        inv = macro_anneal.Inventory.parse(self.inventory())
        self.assertEqual(inv.edges["left_pins"]["L"], 100)
        # a at the origin, b to its right: a's left-edge pins face away.
        centres = {"top/b": (200000.0, 20000.0)}
        self.assertEqual(
            macro_anneal.choose_orientation(
                inv, "top/a", "left_pins", 10000, 10000, centres
            ),
            "MY",
        )
        # b below a instead: a's left pins want the bottom edge, which no
        # flip gives (a flip keeps left on a vertical edge), so R0 by tie.
        centres = {"top/b": (20000.0, -200000.0)}
        self.assertEqual(
            macro_anneal.choose_orientation(
                inv, "top/a", "left_pins", 10000, 10000, centres
            ),
            "R0",
        )

    def test_flipped_origin_keeps_pins_on_tracks(self):
        inv = macro_anneal.Inventory.parse(self.inventory())
        m = inv.masters["left_pins"]
        for orient in ("R0", "MX", "MY", "R180"):
            ox, oy = macro_anneal.macro_origin(inv, "left_pins", 10007, 10011, orient)
            pox, poy = macro_anneal.pin_offsets(m, orient)
            self.assertEqual((ox + pox - 24) % 48, 0, orient)
            self.assertEqual((oy + poy - 20) % 40, 0, orient)

    def test_spread_pins_keep_r0(self):
        inv = macro_anneal.Inventory.parse(
            self.inventory().replace(
                "edges left_pins 100 0 0 0", "edges left_pins 25 25 25 25"
            )
        )
        inv.net_edges.clear()
        for e in "LRBT":
            inv.net_edges[("top/a", "macro:top/b", e)] = 25
        centres = {"top/b": (200000.0, 20000.0)}
        self.assertEqual(
            macro_anneal.choose_orientation(
                inv, "top/a", "left_pins", 10000, 10000, centres
            ),
            "R0",
        )


if __name__ == "__main__":
    unittest.main()
