import json
import os
import tempfile
import unittest

import partition_macros

SLICE = """// verilog_slice: Inner Inner
module Outer(input clk);
  Inner u_inner(.clk(clk));
  ram_a u_ram(.clk(clk));
endmodule
(* blackbox *) module Inner(input clk);
endmodule
module ram_a(input clk);
endmodule
module \\ram_b$x (input clk);
endmodule
"""


class PartitionMacrosTest(unittest.TestCase):
    def test_reached_is_the_slice_stubs(self):
        macros = {"ram_a": {}, "ram_c": {}, "Inner_x": {}}
        self.assertEqual(["ram_a"], partition_macros.reached(macros, [SLICE]))

    def test_escaped_name(self):
        self.assertIn("ram_b$x", partition_macros.slice_modules(SLICE))

    def test_union_of_slices(self):
        other = "module ram_c(input clk);\nendmodule\n"
        macros = {"ram_a": {}, "ram_c": {}}
        self.assertEqual(
            ["ram_a", "ram_c"], partition_macros.reached(macros, [SLICE, other])
        )

    def test_writes_only_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            libs = {}
            for name in ["ram_a", "ram_c"]:
                libs[name] = os.path.join(tmp, name + "_pre_layout.lib")
                with open(libs[name], "w") as f:
                    f.write("library({}) {{}}\n".format(name))
            macros = {
                name: {
                    "lib": libs[name],
                    "lefs": [name + ".lef"],
                    "gds": [name + ".gds"],
                }
                for name in libs
            }
            macros_json = os.path.join(tmp, "macros.json")
            with open(macros_json, "w") as f:
                json.dump(macros, f)
            slice_v = os.path.join(tmp, "slice.v")
            with open(slice_v, "w") as f:
                f.write(SLICE)
            out = os.path.join(tmp, "out")
            partition_macros.main(
                ["--macros-json", macros_json, "--out-dir", out, slice_v]
            )
            copy = os.path.join(out, "ram_a", "ram_a_pre_layout.lib")
            with open(copy) as f:
                self.assertEqual("library(ram_a) {}\n", f.read())
            self.assertFalse(os.path.exists(os.path.join(out, "ram_c")))
            with open(os.path.join(out, "libs.txt")) as f:
                self.assertEqual(copy, f.read())
            with open(os.path.join(out, "macros.mk")) as f:
                self.assertEqual(
                    [
                        "export ADDITIONAL_GDS += ram_a.gds",
                        "export ADDITIONAL_LEFS += ram_a.lef",
                        "export ADDITIONAL_LIBS += " + copy,
                    ],
                    f.read().splitlines(),
                )

    def test_no_macros(self):
        with tempfile.TemporaryDirectory() as tmp:
            macros_json = os.path.join(tmp, "macros.json")
            with open(macros_json, "w") as f:
                json.dump({"ram_c": {"lib": "", "lefs": [], "gds": []}}, f)
            slice_v = os.path.join(tmp, "slice.v")
            with open(slice_v, "w") as f:
                f.write(SLICE)
            out = os.path.join(tmp, "out")
            partition_macros.main(
                ["--macros-json", macros_json, "--out-dir", out, slice_v]
            )
            for name in ["macros.mk", "libs.txt"]:
                with open(os.path.join(out, name)) as f:
                    self.assertEqual("", f.read())


if __name__ == "__main__":
    unittest.main()
