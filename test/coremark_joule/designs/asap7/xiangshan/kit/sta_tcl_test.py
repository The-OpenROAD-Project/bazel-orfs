"""check/sta.tcl on a kit of two flip-flops, in seconds: the script a
tool's results are tested with reads the layout README.pdf describes and
prints the minimum period, and its difference from TOOL_PERIOD_PS.

  sta_tcl_test.py <opensta> <sta.tcl> <SEQ lib> <INVBUF lib.gz>
"""

import gzip
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ARGS = sys.argv[1:]
sys.argv[1:] = []

NETLIST = """module XSTile (clock, in, out);
  input clock;
  input in;
  output out;
  wire n1;
  wire n2;
  DFFHQNx1_ASAP7_75t_R r1 (.CLK(clock), .D(in), .QN(n1));
  INVx1_ASAP7_75t_R u1 (.A(n1), .Y(n2));
  DFFHQNx1_ASAP7_75t_R r2 (.CLK(clock), .D(n2), .QN(out));
endmodule
"""

SDC = """create_clock -name clk -period 500 [get_ports clock]
set_max_delay -ignore_clock_latency 400 -from [get_ports in] -to [all_registers]
set_max_delay -ignore_clock_latency 400 -from [all_registers] -to [get_ports out]
"""

SPEF = """*SPEF "IEEE 1481-1998"
*DESIGN "XSTile"
*DATE "0"
*VENDOR "kit test"
*PROGRAM "kit test"
*VERSION "0"
*DESIGN_FLOW "NETLIST_TYPE_VERILOG"
*DIVIDER /
*DELIMITER :
*BUS_DELIMITER [ ]
*T_UNIT 1 PS
*C_UNIT 1 FF
*R_UNIT 1 KOHM
*L_UNIT 1 HENRY

*PORTS
clock I
in I
out O

*D_NET clock 2.0
*CONN
*P clock I
*I r1:CLK I
*I r2:CLK I
*CAP
1 clock 2.0
*RES
1 clock r1:CLK 0.1
2 clock r2:CLK 0.1
*END

*D_NET in 1.0
*CONN
*P in I
*I r1:D I
*CAP
1 in 1.0
*RES
1 in r1:D 0.1
*END

*D_NET n1 30.0
*CONN
*I r1:QN O
*I u1:A I
*CAP
1 r1:QN 30.0
*RES
1 r1:QN u1:A 2.0
*END

*D_NET n2 1.0
*CONN
*I u1:Y O
*I r2:D I
*CAP
1 u1:Y 1.0
*RES
1 u1:Y r2:D 0.1
*END

*D_NET out 1.0
*CONN
*I r2:QN O
*P out O
*CAP
1 r2:QN 1.0
*RES
1 r2:QN out 0.1
*END
"""


class StaTclTest(unittest.TestCase):
    def test_two_flops(self):
        opensta, sta_tcl, seq, invbuf = ARGS
        with tempfile.TemporaryDirectory() as kit:
            for d in ("check", "cells/lib", "macros/lib", "constraints", "results"):
                os.makedirs(os.path.join(kit, d))
            shutil.copyfile(sta_tcl, os.path.join(kit, "check", "sta.tcl"))
            shutil.copyfile(
                seq, os.path.join(kit, "cells", "lib", os.path.basename(seq))
            )
            with gzip.open(invbuf, "rb") as f, open(
                os.path.join(kit, "cells", "lib", "invbuf.lib"), "wb"
            ) as g:
                g.write(f.read())
            for path, text in (
                ("constraints/XSTile.sdc", SDC),
                ("results/XSTile.v", NETLIST),
                ("results/XSTile.spef", SPEF),
            ):
                with open(os.path.join(kit, path), "w") as f:
                    f.write(text)
            env = dict(os.environ, TOOL_PERIOD_PS="100")
            run = subprocess.run(
                [
                    os.path.abspath(opensta),
                    "-no_init",
                    "-no_splash",
                    "-exit",
                    "check/sta.tcl",
                ],
                cwd=kit,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )
            self.assertEqual(run.returncode, 0, run.stdout)
            m = re.search(r"OpenSTA minimum period (\d+) ps", run.stdout)
            self.assertTrue(m, run.stdout)
            period = int(m.group(1))
            # a flop's clock-to-output, an inverter driving 30 fF, a setup
            self.assertGreater(period, 20, run.stdout)
            self.assertLess(period, 500, run.stdout)
            self.assertIn("r1/QN -> r2/D", run.stdout)
            self.assertNotIn("Warning", run.stdout)
            self.assertRegex(
                run.stdout, r"tool minimum period 100 ps, OpenSTA - tool = [+-]\d+ ps"
            )


if __name__ == "__main__":
    unittest.main()
