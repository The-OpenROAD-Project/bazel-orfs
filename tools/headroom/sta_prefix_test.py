"""sta_prefix.py: a block's modules renamed, its top and library cells not."""

import os
import tempfile
import unittest

import sta_prefix

NETLIST = """module Sub (a);
 input a;
endmodule
module \\$paramod$x (a);
 input a;
endmodule
module MemBlock (a);
 input a;
 Sub u0 (.a(a));
 \\$paramod$x u1 (.a(a));
 BUFx2_ASAP7_75t_R b (.A(a));
endmodule
"""


class Prefix(unittest.TestCase):
    def prefixed(self):
        d = tempfile.mkdtemp()
        src, dst = os.path.join(d, "in.v"), os.path.join(d, "out.v")
        with open(src, "w") as f:
            f.write(NETLIST)
        sta_prefix.main("MemBlock", src, dst)
        with open(dst) as f:
            return f.read()

    def test_modules_and_instances_renamed(self):
        out = self.prefixed()
        self.assertIn("module MemBlock__Sub (a);", out)
        self.assertIn(" MemBlock__Sub u0 (.a(a));", out)

    def test_escaped_names_stay_escaped(self):
        out = self.prefixed()
        self.assertIn("module \\MemBlock__$paramod$x (a);", out)
        self.assertIn(" \\MemBlock__$paramod$x u1 (.a(a));", out)

    def test_top_and_library_cells_keep_their_names(self):
        out = self.prefixed()
        self.assertIn("module MemBlock (a);", out)
        self.assertIn(" BUFx2_ASAP7_75t_R b (.A(a));", out)

    def test_repair_nets_take_their_local_names(self):
        d = tempfile.mkdtemp()
        src, dst = os.path.join(d, "in.v"), os.path.join(d, "out.v")
        with open(src, "w") as f:
            f.write(
                "module Sub (a);\n input a;\n wire \\iq/net7 ;\n"
                " BUFx2_ASAP7_75t_R b (.A(a), .Y(\\iq/net7 ));\nendmodule\n"
                "module Flt (a);\n input a;\n Sub iq (.a(a));\nendmodule\n"
            )
        sta_prefix.main("Flt", src, dst)
        with open(dst) as f:
            out = f.read()
        # the SPEF names it iq/net7: net7 inside the instance iq
        self.assertIn(" wire net7 ;", out)
        self.assertIn(".Y(net7 )", out)


if __name__ == "__main__":
    unittest.main()
