"""Verify //pdk/asap7 stages all 256 added cells and deterministic .lib.gz."""

import fnmatch
import gzip
import re
import struct
import sys
import unittest
from pathlib import Path

EXPECTED_ADDED_STEMS = {
    "AO21BBx1",
    "AO21BBx2",
    "AO21BBx4",
    "AO21Bx1",
    "AO21Bx2",
    "AO21Bx4",
    "AO21Bx6",
    "AO22BBx1",
    "AO22BBx2",
    "AOI21x2",
    "AOI21x4",
    "AOI21x4_1",
    "AOI21x6",
    "AOI22x2",
    "INVx12",
    "MAJx1",
    "MUX2Ix1",
    "MUX2x1",
    "MUX2x3",
    "NAND2Bx1",
    "NAND2Bx2",
    "NAND2Bx2_1",
    "NAND2Bx3",
    "NAND2Bx4",
    "NAND2Bx4_1",
    "NAND2x3",
    "NAND2x4",
    "NAND2x6",
    "NAND3BBx1",
    "NAND3BBx1_1",
    "NAND3BBx4",
    "NAND3Bx1",
    "NAND3Bx1_1",
    "NAND3Bx6",
    "NAND3x4",
    "NAND4Bx1",
    "NAND4x4",
    "NOR2Bx1",
    "NOR2Bx1_1",
    "NOR2Bx2",
    "NOR2Bx2_1",
    "NOR2Bx3",
    "NOR2Bx4",
    "NOR2Bx6",
    "NOR2x4",
    "NOR2x6",
    "NOR3BBx1",
    "NOR3BBx1_1",
    "NOR3Bx1",
    "NOR3Bx1_1",
    "NOR3Bx3",
    "NOR3Bx4",
    "NOR3Bx4_1",
    "NOR3x4",
    "NOR3x8",
    "OA21BBx1",
    "OA21BBx2",
    "OA21Bx1",
    "OA21Bx2",
    "OA21Bx4",
    "OA22BBx1",
    "OAI211x1",
    "OAI21x2",
    "OAI21x4",
}

PATHS = []
BASE_PATHS = []


class PdkAsap7Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_rel = {}
        marker = "/asap7_src/"
        for p in PATHS:
            idx = p.find(marker)
            if idx != -1:
                cls.by_rel[p[idx + len(marker) :]] = Path(p)
        cls.base_by_rel = {}
        base_marker = "/flow/"
        for p in BASE_PATHS:
            idx = p.find(base_marker)
            if idx != -1:
                cls.base_by_rel[p[idx + len(base_marker) :]] = Path(p)

    def test_expected_stems_count(self):
        self.assertEqual(len(EXPECTED_ADDED_STEMS), 64)

    def test_config_mk_wires_added_libs(self):
        cfg = self.by_rel["platforms/asap7/config.mk"].read_text()
        for corner, suffix in (
            ("BC_NLDM_LIB_FILES_T", "FF_nldm_261116.lib.gz"),
            ("BC_CCS_LIB_FILES_T", "FF_ccs_261116.lib.gz"),
            ("WC_NLDM_LIB_FILES_T", "SS_nldm_261116.lib.gz"),
            ("TC_NLDM_LIB_FILES_T", "TT_nldm_261116.lib.gz"),
        ):
            self.assertIn(
                f"asap7sc7p5t_ADDED_PLACEHOLDERVT_{suffix}",
                cfg,
                f"missing ADDED lib in {corner}",
            )

    def test_lefs_and_libs_contain_all_added_cells(self):
        # Extract DONT_USE_CELLS patterns from config.mk to ensure none of the
        # 64 added cells are inadvertently masked.
        dont_use = ["*x1p*_ASAP7*", "*xp*_ASAP7*", "SDF*", "ICG*"]

        for vt, tag in (("RVT", "R"), ("LVT", "L"), ("SLVT", "SL"), ("SRAM", "SRAM")):
            lef_path = self.by_rel[
                f"platforms/asap7/lef/asap7sc7p5t_28_{tag}_1x_220121a.lef"
            ]
            lef_text = lef_path.read_text()
            macro_blocks = {
                name: block
                for block, name in re.findall(
                    r"(^MACRO\s+(\S+)\b.*?^END\s+\2\b)", lef_text, re.M | re.S
                )
            }
            lef_macros = set(macro_blocks.keys())
            base_lef = self.base_by_rel[
                f"platforms/asap7/lef/asap7sc7p5t_28_{tag}_1x_220121a.lef"
            ].read_text()
            base_vt_layers = sorted(
                set(re.findall(r"LAYER\s+(\S*VT\S*)\s*;", base_lef))
            )
            our_vt_layers = sorted(set(re.findall(r"LAYER\s+(\S*VT\S*)\s*;", lef_text)))
            self.assertEqual(
                our_vt_layers,
                base_vt_layers,
                f"VT layers in {tag} LEF ({our_vt_layers}) differ from @orfs//flow:asap7 ({base_vt_layers})",
            )
            if tag in ("R", "L", "SL"):
                for mname, mblock in macro_blocks.items():
                    self.assertIn(
                        f"LAYER {tag}VTN", mblock, f"{mname} missing {tag}VTN"
                    )
                    self.assertIn(
                        f"LAYER {tag}VTP", mblock, f"{mname} missing {tag}VTP"
                    )

            for corner in ("FF", "SS", "TT"):
                rel = f"platforms/asap7/lib/NLDM/asap7sc7p5t_ADDED_{vt}_{corner}_nldm_261116.lib.gz"
                gz_path = self.by_rel[rel]
                raw_hdr = gz_path.read_bytes()[:10]
                self.assertEqual(raw_hdr[:2], b"\x1f\x8b")
                mtime = struct.unpack("<I", raw_hdr[4:8])[0]
                self.assertEqual(mtime, 0, f"{rel} embeds non-zero gzip mtime {mtime}")

                lib_text = gzip.decompress(gz_path.read_bytes()).decode("utf-8")
                cells = set(
                    re.findall(
                        r'^\s*cell\s*\(\s*"?([A-Za-z0-9_]+)"?\s*\)', lib_text, re.M
                    )
                )
                self.assertEqual(
                    len(cells), 64, f"{rel}: expected 64 cells, got {len(cells)}"
                )

                # Every ADDED liberty cell must exist in the matching 1x LEF and
                # must not match DONT_USE_CELLS.
                missing_in_lef = cells - lef_macros
                self.assertFalse(
                    missing_in_lef, f"{rel} cells missing from LEF: {missing_in_lef}"
                )
                for cell in cells:
                    for pat in dont_use:
                        self.assertFalse(
                            fnmatch.fnmatchcase(cell, pat),
                            f"added cell {cell} unexpectedly matches DONT_USE_CELLS pattern {pat}",
                        )


if __name__ == "__main__":
    sep = sys.argv.index("--")
    PATHS[:] = sys.argv[1:sep]
    BASE_PATHS[:] = sys.argv[sep + 1 :]
    sys.argv = [sys.argv[0]]
    unittest.main()
