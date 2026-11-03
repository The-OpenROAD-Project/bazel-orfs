"""The kit's tools on small inputs, and README's template against the
repo's own plan, KPI and resources: a fact the template names that the
repo no longer has, or one it has that nothing names, fails here first."""

import glob
import gzip
import io
import json
import os
import re
import tarfile
import tempfile
import unittest

import itf_gen
import kit
import render_md

HERE = os.path.dirname(os.path.abspath(__file__))
XS = os.path.normpath(os.path.join(HERE, ".."))

LEF = """
LAYER M1
  TYPE ROUTING ;
  WIDTH 0.018 ;
  SPACING 0.018 ;
END M1
LAYER V1
  TYPE CUT ;
  WIDTH 0.018 ;
END V1
LAYER M2
  TYPE ROUTING ;
  WIDTH 0.024 ;
  SPACING 0.024 ;
END M2
LAYER V2
  TYPE CUT ;
  CUTCLASS Vx WIDTH 0.024 LENGTH 0.032 ;
END V2
LAYER M3
  TYPE ROUTING ;
  WIDTH 0.032 ;
  SPACING 0.032 ;
END M3
LAYER Pad
  TYPE ROUTING ;
  WIDTH 1.0 ;
END Pad
"""

SETRC = """
set_layer_rc -layer M1 -resistance 7.0E-02 -capacitance 1e-10
set_layer_rc -layer M2 -resistance 3.0E-02 -capacitance 1.7E-01
set_layer_rc -layer M3 -resistance 1.2E-02 -capacitance 1.6E-01
set_layer_rc -via V1 -resistance 1.72E-02
set_layer_rc -via V2 -resistance 1.18E-02
"""


class ItfTest(unittest.TestCase):
    def test_model_reproduces_setrc(self):
        layers, cuts = itf_gen.parse_lef(LEF)
        self.assertEqual([n for n, _, _ in layers], ["M1", "M2", "M3"])
        levels, vias = itf_gen.stack(layers, cuts, itf_gen.parse_setrc(SETRC))
        for lv in levels[1:]:
            c = itf_gen.cap_per_um(lv["er"], lv["w"], lv["s"], lv["t"], lv["h"])
            self.assertAlmostEqual(c, lv["c_um"], places=9)
            self.assertAlmostEqual(lv["rpsq"] / 1000.0 / lv["w"], lv["r_um"], places=12)
        self.assertEqual(levels[0]["er"], itf_gen.ER_DEFAULT)
        self.assertAlmostEqual(vias[1]["area"], 0.024 * 0.032)
        self.assertAlmostEqual(vias[0]["rpv"], 17.2)

    def test_missing_via_stops(self):
        layers, cuts = itf_gen.parse_lef(LEF)
        rc = itf_gen.parse_setrc(
            SETRC.replace("set_layer_rc -via V2 -resistance 1.18E-02", "")
        )
        with self.assertRaises(SystemExit):
            itf_gen.stack(layers, cuts, rc)


class SdcTest(unittest.TestCase):
    DESIGN = "set clk_period 2000\nif { 1 } {\n  source $::env(PLATFORM_DIR)/constraints.sdc\n}\n"

    def test_inlined_once(self):
        out = kit.inline_sdc(
            self.DESIGN, "create_clock -period $clk_period [get_ports clock]\n"
        )
        self.assertNotIn("PLATFORM_DIR", out)
        self.assertIn("  create_clock -period $clk_period", out)

    def test_not_sourced_stops(self):
        with self.assertRaises(SystemExit):
            kit.inline_sdc("set clk_period 2000\n", "x\n")


class ArchiveTest(unittest.TestCase):
    def build(self, d, name):
        lib = os.path.join(d, "a.lib.gz")
        with gzip.open(lib, "wb") as f:
            f.write(b"library (a) {}\n")
        out = os.path.join(d, name)
        ar = kit.Archive(out)
        ar.add_file("cells/lib/a.lib.gz", lib)
        ar.add_bytes("README.txt", b"x")
        ar.add_dir("results")
        ar.close()
        return out

    def test_deterministic_and_decompressed(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.build(d, "a.tar.gz"), self.build(d, "b.tar.gz")
            self.assertEqual(open(a, "rb").read(), open(b, "rb").read())
            with tarfile.open(a) as t:
                names = t.getnames()
                self.assertIn(kit.ROOT + "/cells/lib/a.lib", names)
                self.assertEqual(
                    t.extractfile(kit.ROOT + "/cells/lib/a.lib").read(),
                    b"library (a) {}\n",
                )

    def test_unpack_refuses_outside_paths(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.tar.gz")
            with tarfile.open(bad, "w:gz") as t:
                info = tarfile.TarInfo("../escape")
                info.size = 1
                t.addfile(info, io.BytesIO(b"x"))
            with self.assertRaises(SystemExit):
                kit.main(["unpack", "--in", bad, "--dir", d])

    def test_resolve_is_exact(self):
        files = ["x/platforms/asap7/lef/a.lef", "x/platforms/asap7/lef/b.lef"]
        self.assertEqual(
            kit.resolve([("cell_lef", "lef/a.lef")], files)[0][2], files[0]
        )
        with self.assertRaises(SystemExit):
            kit.resolve([("cell_lef", "lef/c.lef")], files)


class TemplateTest(unittest.TestCase):
    def test_unknown_and_unused_stop(self):
        with self.assertRaises(SystemExit):
            render_md.render("{{a}} {{b}}", {"a": "1"})
        with self.assertRaises(SystemExit):
            render_md.render("{{a}}", {"a": "1", "b": "2"})

    def test_template_against_the_repo(self):
        """The real template, plan, KPI and resources, with facts made up
        from the register-file specs: every placeholder filled, every fact
        used."""
        regfiles = sorted(glob.glob(os.path.join(XS, "*.regfile")))
        self.assertTrue(regfiles)
        macros = {
            "array_64x64": {
                "w_um": 10.0,
                "h_um": 5.0,
                "instances": ["l2top/a/b/m0", "l2top/a/c/m1"],
            }
        }
        for path in regfiles:
            module = render_md.parse_regfile(path)["module"]
            macros[module] = {
                "w_um": 1.0,
                "h_um": 1.0,
                "instances": ["core/%s" % module],
            }
        with tempfile.TemporaryDirectory() as d:
            facts = os.path.join(d, "facts.json")
            with open(facts, "w") as f:
                json.dump(
                    {
                        "top": "XSTile",
                        "ports": 386,
                        "cells": 100,
                        "flops": 10,
                        "clock_gates": 1,
                        "std_area_um2": 1e6,
                        "checks": {
                            "loops": 0,
                            "no_clock": 0,
                            "multiple_clock": 0,
                            "undriven": 0,
                            "multidriven": 0,
                        },
                        "macros": macros,
                    },
                    f,
                )
            pin = os.path.join(d, "pin.json")
            with open(pin, "w") as f:
                json.dump({"netlist_sha256": "0" * 64, "date": "2026-11-03"}, f)
            ports = os.path.join(d, "ports.json")
            with open(ports, "w") as f:
                json.dump(
                    [
                        {"name": "clock", "dir": "input", "width": 1},
                        {"name": "io_chi_tx_dat_flit", "dir": "output", "width": 385},
                    ],
                    f,
                )
            out = os.path.join(d, "out.md")
            render_md.main(
                [
                    "--template",
                    os.path.join(HERE, "EXPORT.md"),
                    "--out",
                    out,
                    "--svg",
                    os.path.join(d, "floorplan.svg"),
                    "--facts",
                    facts,
                    "--plan",
                    os.path.join(XS, "plan", "plan.json"),
                    "--plan-bzl",
                    os.path.join(XS, "plan", "plan.bzl"),
                    "--kpi",
                    os.path.join(XS, "kpi.json"),
                    "--resources",
                    os.path.join(XS, "resources.json"),
                    "--ab",
                    os.path.join(XS, "arrays", "ab.json"),
                    "--blocks",
                    os.path.join(HERE, "blocks.json"),
                    "--module-bazel",
                    os.path.join(XS, "..", "..", "..", "..", "..", "MODULE.bazel"),
                    "--sta",
                    os.path.join(HERE, "sta.tcl"),
                    "--rtl-ports",
                    ports,
                    "--pin",
                    pin,
                ]
                + regfiles
            )
            text = open(out).read()
            self.assertNotIn("{{", text)
            self.assertIn("| `array_64x64` | 64 | 64 | 2 |", text)
            self.assertIn("`l2top/a`", text)
            self.assertTrue(
                re.search(r"<svg[^>]*>", open(os.path.join(d, "floorplan.svg")).read())
            )


if __name__ == "__main__":
    unittest.main()
