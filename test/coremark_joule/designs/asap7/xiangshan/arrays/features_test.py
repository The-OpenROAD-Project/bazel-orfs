"""The front end end to end on a design small enough to read: an 8-entry
CAM written as XiangShan's generator writes its queues (data_<i> and
valid_<i>, each written where a broadcast index equals i), its match
reduced across entries, and a submodule kept a blackbox.

    features_test.py <yosys> <slang.so> <fold_entries.tcl>

Checked, each as the feature that makes XSTile's blocks extractable:
the entries found and every one following one rule; the index comparison
decoded once in the parent; the match left in the entry cell (the read
side); the blackbox kept an instance of the block; the extraction proven
equal to the design and the negative control proven different; and
slang's per-instance copies of the entry cell folded onto one module.
"""

import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
N = 8


SUB = "module Sub(input [7:0] a, output [7:0] y);\n  assign y = a ^ 8'h5a;\nendmodule\n"


def cam():
    lines = [
        "module Cam(input clock, input reset, input we, input [2:0] widx,",
        "           input [7:0] wdata, input [7:0] q, output hit, output [7:0] mixed);",
        "  wire [7:0] wd;",
        "  Sub sub (.a(wdata), .y(wd));",
    ]
    for i in range(N):
        lines += [
            f"  reg [7:0] data_{i};",
            f"  reg valid_{i};",
            "  always @(posedge clock) begin",
            f"    if (reset) valid_{i} <= 1'b0;",
            f"    else if (we && widx == 3'd{i}) valid_{i} <= 1'b1;",
            f"    if (we && widx == 3'd{i}) data_{i} <= wd;",
            "  end",
        ]
    match = " | ".join(f"(valid_{i} && data_{i} == q)" for i in range(N))
    lines += [
        f"  assign hit = {match};",
        "  assign mixed = " + " ^ ".join(f"data_{i}" for i in range(N)) + ";",
        "endmodule",
    ]
    return "\n".join(lines) + "\n"


def run(*args):
    # under Bazel the interpreter runs with PYTHONSAFEPATH, so a script
    # does not see the modules beside it unless told
    env = dict(os.environ, PYTHONPATH=HERE)
    r = subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, cwd=HERE, env=env
    )
    return r.returncode, r.stdout + r.stderr


class Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # runfiles paths, made absolute: the steps run beside their scripts
        cls.yosys, cls.slang, cls.fold = map(os.path.abspath, sys.argv[1:4])
        cls.work = os.environ.get("TEST_TMPDIR", HERE)
        cls.src = os.path.join(cls.work, "cam.sv")
        with open(cls.src, "w") as f:
            f.write(SUB + cam())
        cls.proc = os.path.join(cls.work, "cam.json")
        rc, log = run(
            "proc_json.py", cls.yosys, cls.slang, cls.src, "Cam", cls.proc, "Sub"
        )
        assert rc == 0, log
        cls.found = run("entries.py", cls.proc, "Cam")[1]
        cls.extracted = os.path.join(cls.work, "extracted.json")
        rc, cls.extract_log = run("extract.py", cls.proc, "Cam", cls.extracted)
        assert rc == 0, cls.extract_log
        cls.stats = dict(re.findall(r"(\w+) (\d+)", cls.extract_log))

    def test_entries_follow_one_rule(self):
        self.assertIn("uniform: 8 of 8 entries follow one rule", self.found)
        self.assertEqual(self.stats["entries"], str(N))

    def test_index_decoded_once(self):
        self.assertEqual(self.stats["decoded_once"], "1")
        self.assertEqual(self.stats["index_sites_left"], "0")

    def test_match_in_the_cell(self):
        # each entry's compare against q stays in its cell; one bit leaves
        self.assertIn("read side: 1 bits leave each entry's read cone", self.found)

    def test_blackbox_kept(self):
        top = json.load(open(self.extracted))["modules"]["Cam"]
        types = [c["type"] for c in top["cells"].values()]
        self.assertEqual(types.count("Sub"), 1)
        self.assertEqual(types.count("CamEntry"), N)

    def test_extraction_equal(self):
        rc, log = run("check.py", self.yosys, self.proc, self.extracted, "Cam")
        self.assertEqual(rc, 0, log)
        self.assertIn("check: Cam: equivalent", log)

    def test_control_differs(self):
        rc, log = run(
            "check.py", self.yosys, self.proc, self.extracted, "Cam", "mutate"
        )
        self.assertEqual(rc, 0, log)
        self.assertIn("check: Cam: NOT equivalent", log)

    def test_fold(self):
        verilog = os.path.join(self.work, "extracted.v")
        r = subprocess.run(
            [
                self.yosys,
                "-q",
                "-p",
                f"read_json {self.extracted}; hierarchy -top Cam; write_verilog -noattr {verilog}",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        # the blackbox's definition stays the core's, as in XSTile
        sub = os.path.join(self.work, "sub.sv")
        with open(sub, "w") as f:
            f.write(SUB)
        listing = os.path.join(self.work, "modules.txt")
        script = os.path.join(self.work, "fold.tcl")
        with open(script, "w") as f:
            f.write(
                "yosys -import\n"
                f"plugin -i {self.slang}\n"
                "yosys read_slang --keep-hierarchy --top Cam "
                f"--blackboxed-module Sub {verilog} {sub}\n"
                "yosys hierarchy -check -top Cam\n"
                f"source {self.fold}\n"
                f"yosys tee -q -o {listing} select -list-mod =*\n"
            )
        env = dict(os.environ, DESIGN_NAME="Cam", XS_FOLD_MODULES="CamEntry")
        r = subprocess.run(
            [self.yosys, "-q", "-c", script], capture_output=True, text=True, env=env
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"CamEntry, {N} copies folded onto one", r.stdout)
        modules = sorted(m.strip().lstrip("\\") for m in open(listing) if m.strip())
        self.assertEqual(modules, ["Cam", "CamEntry", "Sub"])


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
