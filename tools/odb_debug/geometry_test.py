"""geometry.py on a hand-made dump: two macros, a sliver between them."""

import contextlib
import io
import os
import tempfile
import unittest

import geometry

DBU = 1000


def write_dump(d):
    # 1000 x 1000 um die and core; macros at [100,400]x[100,900] and
    # [410,710]x[100,900] leave a 10 um sliver between them.
    with open(os.path.join(d, "summary.txt"), "w") as f:
        f.write("dbu %d\n" % DBU)
        f.write("die 0 0 %d %d\n" % (1000 * DBU, 1000 * DBU))
        f.write("core 0 0 %d %d\n" % (1000 * DBU, 1000 * DBU))
        f.write("insts 4 nets 0 rows 3 blockages 0\n")
    with open(os.path.join(d, "rows.txt"), "w") as f:
        # one full row below the macros, a sliver row between them, one wide row right of them
        f.write("0 0 %d %d 1000\n" % (1000 * DBU, 1 * DBU))
        f.write("%d %d %d %d 10\n" % (400 * DBU, 500 * DBU, 410 * DBU, 501 * DBU))
        f.write("%d %d %d %d 290\n" % (710 * DBU, 500 * DBU, 1000 * DBU, 501 * DBU))
    with open(os.path.join(d, "macros.txt"), "w") as f:
        f.write(
            "u_a MACA %d %d %d %d R0 LOCKED\n"
            % (100 * DBU, 100 * DBU, 400 * DBU, 900 * DBU)
        )
        f.write(
            "u_b MACB %d %d %d %d R0 LOCKED\n"
            % (410 * DBU, 100 * DBU, 710 * DBU, 900 * DBU)
        )
    with open(os.path.join(d, "insts.txt"), "w") as f:
        # inside u_a, in the sliver, in the open, and a tap cell inside u_b
        f.write(
            "c_in INVx1 %d %d %d %d PLACED\n" % (200 * DBU, 500 * DBU, 1 * DBU, 1 * DBU)
        )
        f.write(
            "c_sliver BUFx16f %d %d %d %d PLACED\n"
            % (402 * DBU, 500 * DBU, 2 * DBU, 1 * DBU)
        )
        f.write(
            "c_free NAND2 %d %d %d %d PLACED\n"
            % (800 * DBU, 500 * DBU, 1 * DBU, 1 * DBU)
        )
        f.write(
            "t0 TAPCELL_ASAP7 %d %d %d %d PLACED\n"
            % (500 * DBU, 500 * DBU, 1 * DBU, 1 * DBU)
        )


def run(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


class GeometryTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="geometry_test.")
        write_dump(self.d)

    def test_readers(self):
        s = geometry.read_summary(self.d)
        self.assertEqual(s["core_um"], [0.0, 0.0, 1000.0, 1000.0])
        self.assertEqual(len(geometry.read_rows(self.d, s["dbu"])), 3)
        macros = geometry.read_macros(self.d, s["dbu"])
        self.assertEqual([m["name"] for m in macros], ["u_a", "u_b"])
        self.assertEqual(macros[0]["status"], "LOCKED")
        insts = geometry.read_insts(self.d, s["dbu"])
        self.assertEqual(insts[0][2:4], (200.5, 500.5))

    def test_containment_and_fragment_width(self):
        s = geometry.read_summary(self.d)
        macros = geometry.read_macros(self.d, s["dbu"])
        rows = geometry.read_rows(self.d, s["dbu"])
        self.assertEqual(geometry.containing_macro(macros, 200, 500), 0)
        self.assertEqual(geometry.containing_macro(macros, 405, 500), -1)
        self.assertEqual(geometry.fragment_width_at(rows, 405, 500.5), 10.0)
        self.assertEqual(geometry.fragment_width_at(rows, 405, 700), -1)

    def test_free(self):
        out = run(geometry.cmd_free, self.d)
        self.assertIn("2 macros", out)
        self.assertIn("3 row fragments", out)
        self.assertIn("5-20 um 1", out)

    def test_inside_skips_tap_cells(self):
        out = run(geometry.cmd_inside, self.d)
        self.assertIn("4 non-macro instances, 3 logic; 1 logic cells", out)
        self.assertIn("in u_a", out)

    def test_failed(self):
        names = os.path.join(self.d, "failed.txt")
        with open(names, "w") as f:
            f.write("c_in\nc_sliver\nc_free\nnot_there\n")
        out = run(geometry.cmd_failed, self.d, names)
        self.assertIn("4 names, 3 found", out)
        self.assertIn("inside a macro footprint: 1", out)
        self.assertIn("row fragment under 10 um: 0, 10-30 um: 1", out)

    def test_main_usage(self):
        self.assertEqual(geometry.main(["geometry.py"]), 2)


if __name__ == "__main__":
    unittest.main()
