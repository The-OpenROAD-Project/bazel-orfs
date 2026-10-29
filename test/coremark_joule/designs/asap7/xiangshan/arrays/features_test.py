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

A second design, a queue whose entries are freed below a bound, checks
thresholds: x >= i + 1 and x < i + 1, written as firtool folds them for
each i (VirtualLoadQueue's entryHitBound), read as one form and decoded
once.

A third, a CAM with a priority select in banks of four, checks a read
side that differs between entries (LoadQueueRAW): entry i's match is
read through one inverter per entry above it in its bank, a different
number in every entry, and the match itself is what every entry has.
Its match registers against q1 and q2, named as firtool names a vector
(m_r, m_r_1, ..., m_r_15; word p * 8 + i entry i's on port p, as
Uncache's f1_ptagMatches_r), are two arrays of the eight entries.
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


def threshold_queue():
    """Entry i frees when lo < i + 1 and bound >= i + 1, both written as
    firtool writes them: a reduction of the top bits at a power of two,
    x[3] alone at 8, a comparison elsewhere."""

    def ge(x, k):  # x >= k, 4 bits
        if k & (k - 1) == 0:
            top = k.bit_length() - 1
            return f"{x}[3]" if top == 3 else f"(|{x}[3:{top}])"
        return f"({x} > 4'd{k - 1})"

    def lt(x, k):  # x < k, 4 bits
        if k == 1:
            return f"({x} == 4'h0)"
        if k & (k - 1) == 0:
            top = k.bit_length() - 1
            return f"(~{x}[3])" if top == 3 else f"(~|{x}[3:{top}])"
        return f"({x} < 4'd{k})"

    lines = [
        "module Queue(input clock, input reset, input we, input [2:0] widx,",
        "             input [7:0] wdata, input [3:0] lo, input [3:0] bound,",
        "             output any, output [7:0] mixed);",
    ]
    for i in range(N):
        lines += [
            f"  reg [7:0] data_{i};",
            f"  reg live_{i};",
            f"  wire free_{i} = {lt('lo', i + 1)} & {ge('bound', i + 1)};",
            "  always @(posedge clock) begin",
            f"    if (reset) live_{i} <= 1'b0;",
            f"    else if (we && widx == 3'd{i}) live_{i} <= 1'b1;",
            f"    else if (free_{i}) live_{i} <= 1'b0;",
            f"    if (we && widx == 3'd{i}) data_{i} <= wdata;",
            "  end",
        ]
    lines += [
        "  assign any = " + " | ".join(f"live_{i}" for i in range(N)) + ";",
        "  assign mixed = " + " ^ ".join(f"data_{i}" for i in range(N)) + ";",
        "endmodule",
    ]
    return "\n".join(lines) + "\n"


def priority_cam():
    lines = [
        "module PriCam(input clock, input reset, input we, input [2:0] widx,",
        "              input [7:0] wdata, input [7:0] q0, input [7:0] q1, input [7:0] q2,",
        "              output [7:0] first, output any, output [15:0] seen);",
    ]
    for i in range(N):
        lines += [
            f"  reg [7:0] data_{i};",
            f"  reg valid_{i};",
            "  always @(posedge clock) begin",
            f"    if (reset) valid_{i} <= 1'b0;",
            f"    else if (we && widx == 3'd{i}) valid_{i} <= 1'b1;",
            f"    if (we && widx == 3'd{i}) data_{i} <= wdata;",
            "  end",
            f"  wire hit_{i} = valid_{i} && data_{i} == q0;",
        ]
    for i in range(N):
        # the first hit in its bank of four, each lower entry inverted
        # where it is used, as firtool writes it
        lower = "".join(f" & ~hit_{j}" for j in range(i - i % 4, i))
        lines.append(f"  assign first[{i}] = hit_{i}{lower};")
    lines.append("  assign any = " + " | ".join(f"hit_{i}" for i in range(N)) + ";")
    regs = []
    for p in range(2):
        for i in range(N):
            k = p * N + i
            name = "m_r" if k == 0 else f"m_r_{k}"
            regs.append(name)
            lines += [
                f"  reg {name};",
                f"  always @(posedge clock) {name} <= valid_{i} && data_{i} == q{p + 1};",
            ]
    lines += [
        "  assign seen = {" + ", ".join(reversed(regs)) + "};",
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


class Thresholds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yosys, cls.slang = map(os.path.abspath, sys.argv[1:3])
        cls.work = os.environ.get("TEST_TMPDIR", HERE)
        src = os.path.join(cls.work, "queue.sv")
        with open(src, "w") as f:
            f.write(threshold_queue())
        cls.proc = os.path.join(cls.work, "queue.json")
        rc, log = run("proc_json.py", cls.yosys, cls.slang, src, "Queue", cls.proc)
        assert rc == 0, log
        cls.found = run("entries.py", cls.proc, "Queue")[1]
        cls.kept = os.path.join(cls.work, "queue_kept.json")
        rc, log = run("extract.py", cls.proc, "Queue", cls.kept, "--keep-idx")
        assert rc == 0, log
        cls.extracted = os.path.join(cls.work, "queue_extracted.json")
        rc, log = run("extract.py", cls.proc, "Queue", cls.extracted)
        assert rc == 0, log
        cls.stats = dict(re.findall(r"(\w+) (\d+)", log))

    def test_entries_follow_one_rule(self):
        self.assertIn("uniform: 8 of 8 entries follow one rule", self.found)
        # live_<i>, freed below the bound, in the cell with data_<i>
        self.assertNotIn("left inline", self.found)

    def test_thresholds_decoded_once(self):
        # widx == i, lo < i + 1 and bound >= i + 1: one decoder each
        self.assertEqual(self.stats["decoded_once"], "3")
        self.assertEqual(self.stats["index_sites_left"], "0")

    def test_index_kept_equal(self):
        rc, log = run("check.py", self.yosys, self.proc, self.kept, "Queue")
        self.assertEqual(rc, 0, log)
        self.assertIn("check: Queue: equivalent", log)

    def test_decoded_equal(self):
        rc, log = run("check.py", self.yosys, self.proc, self.extracted, "Queue")
        self.assertEqual(rc, 0, log)
        self.assertIn("check: Queue: equivalent", log)

    def test_control_differs(self):
        rc, log = run(
            "check.py", self.yosys, self.proc, self.extracted, "Queue", "mutate"
        )
        self.assertEqual(rc, 0, log)
        self.assertIn("check: Queue: NOT equivalent", log)


class ReadSides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yosys, cls.slang = map(os.path.abspath, sys.argv[1:3])
        cls.work = os.environ.get("TEST_TMPDIR", HERE)
        src = os.path.join(cls.work, "pricam.sv")
        with open(src, "w") as f:
            f.write(priority_cam())
        cls.proc = os.path.join(cls.work, "pricam.json")
        rc, log = run("proc_json.py", cls.yosys, cls.slang, src, "PriCam", cls.proc)
        assert rc == 0, log
        cls.found = run("entries.py", cls.proc, "PriCam")[1]
        cls.extracted = os.path.join(cls.work, "pricam_extracted.json")
        rc, log = run("extract.py", cls.proc, "PriCam", cls.extracted)
        assert rc == 0, log

    def test_entries_follow_one_rule(self):
        self.assertIn("uniform: 8 of 8 entries follow one rule", self.found)
        self.assertNotIn("left inline", self.found)

    def test_common_read_side_in_the_cell(self):
        # the match leaves each entry once; the inverters stay outside
        self.assertIn("read side: 1 bits leave each entry's read cone", self.found)

    def test_port_registers_are_entries(self):
        # data, valid and both ports' m_r: every register in the entries
        self.assertIn("(100%)", self.found)

    def test_extraction_equal(self):
        rc, log = run("check.py", self.yosys, self.proc, self.extracted, "PriCam")
        self.assertEqual(rc, 0, log)
        self.assertIn("check: PriCam: equivalent", log)

    def test_control_differs(self):
        rc, log = run(
            "check.py", self.yosys, self.proc, self.extracted, "PriCam", "mutate"
        )
        self.assertEqual(rc, 0, log)
        self.assertIn("check: PriCam: NOT equivalent", log)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
