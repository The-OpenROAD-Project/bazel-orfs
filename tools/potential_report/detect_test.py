"""The detectors on fixtures whose shapes are known."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect  # noqa: E402
import whatif  # noqa: E402

YOSYS = None
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def design(name, top):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "d.json")
        subprocess.run(
            [
                YOSYS,
                "-q",
                "-p",
                "read_verilog -sv %s/%s.v; hierarchy -top %s; proc; opt_clean; write_json %s"
                % (HERE, name, top, out),
            ],
            check=True,
        )
        with open(out) as f:
            return json.load(f)


def kinds(findings):
    return sorted((f["kind"], f.get("n")) for f in findings)


class Detect(unittest.TestCase):
    def test_cam(self):
        f = detect.detect(design("cam16", "Cam16"))
        self.assertEqual(
            kinds(f), [("broadcast", 16), ("reduction", None), ("replicated", 16)]
        )
        (b,) = [x for x in f if x["kind"] == "broadcast"]
        self.assertEqual((b["port"], b["width"], b["key_bit_loads"]), ("key", 8, 16))

    def test_const_index(self):
        f = detect.detect(design("const_index", "ConstIndex"))
        # The pointers compared with the index are a decoder, not a CAM key.
        self.assertEqual(kinds(f), [("const_index", 32), ("replicated", 32)])
        (c,) = [x for x in f if x["kind"] == "const_index"]
        self.assertEqual(
            (c["port"], c["compares_per_leaf"], c["operands"], c["width"]),
            ("idx", 2, 2, 5),
        )

    def test_age_matrix(self):
        f = detect.detect(design("age8", "Age8"))
        self.assertEqual(kinds(f), [("matrix", 8)])
        self.assertEqual(f[0]["bits"], 28)

    def test_flat_cam(self):
        f = detect.detect(design("flat_cam", "FlatCam"))
        self.assertEqual(kinds(f), [("flat_cam", 16)])
        self.assertEqual(f[0]["width"], 10)

    def test_register_file_is_not_ours(self):
        self.assertEqual(detect.detect(design("rf2r1w", "Rf2r1w")), [])

    def test_plain_logic(self):
        self.assertEqual(detect.detect(design("plain", "Plain")), [])

    def test_uniquified_names(self):
        self.assertEqual(
            detect.base_name("RobEntryCell$Rob.robEntryCells_7"), "RobEntryCell"
        )
        self.assertEqual(detect.base_name("\\CamEntry"), "CamEntry")


class WhatIf(unittest.TestCase):
    def test_flattening_shares_the_decode(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "w")
            read = "read_verilog -sv %s/const_index.v" % HERE
            kept = whatif.run(
                YOSYS, read, "ConstIndex", ["IdxEntry"], False, log + ".kept"
            )
            flat = whatif.run(
                YOSYS, read, "ConstIndex", ["IdxEntry"], True, log + ".flat"
            )
        self.assertLess(flat["cells"], 0.9 * kept["cells"])


if __name__ == "__main__":
    YOSYS = os.path.abspath(sys.argv.pop(1))
    unittest.main()
