"""Each design directory gets its own config, even when it shares a
DESIGN_NICKNAME with another.

Variants that include a base design's config.mk share its nickname
(asap7/picorv32-regfile and -seed2/-seed3, coralnpu-regfile and
coralnpu-regfile-mux). @orfs_designs once keyed DESIGNS by nickname, and
the last variant parsed replaced the base design's config: picorv32-regfile
ran seed 3, coralnpu-regfile the mux spec. argv[1] is a JSON object of
directory -> the arguments and sources DESIGNS holds for it.
"""

import json
import sys
import unittest

DESIGNS = json.loads(sys.argv[1])


class DesignsByDirectoryTest(unittest.TestCase):
    def spec_package(self, design):
        (label,) = DESIGNS[design]["sources"]["AUTO_MEMORIES_REGFILES"]
        return label

    def test_seed_variants_keep_their_own_seed(self):
        self.assertNotIn("GPL_RANDOM_SEED", DESIGNS["picorv32-regfile"]["arguments"])
        self.assertEqual(
            DESIGNS["picorv32-regfile-seed2"]["arguments"]["GPL_RANDOM_SEED"], "2"
        )
        self.assertEqual(
            DESIGNS["picorv32-regfile-seed3"]["arguments"]["GPL_RANDOM_SEED"], "3"
        )

    def test_mux_variants_do_not_replace_their_base(self):
        for base in ("coralnpu-regfile", "swerv_wrapper-regfile"):
            self.assertNotIn("-mux", self.spec_package(base), base)
            self.assertNotEqual(
                DESIGNS[base]["sources"]["AUTO_MEMORIES_REGFILES"],
                DESIGNS[base + "-mux"]["sources"]["AUTO_MEMORIES_REGFILES"],
            )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
