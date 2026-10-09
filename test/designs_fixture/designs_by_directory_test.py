"""Each design directory gets its own config, even when it shares a
DESIGN_NICKNAME with another.

asap7/tiny-variant includes asap7/tiny's config.mk, and with it the
nickname "tiny". @orfs_designs keyed DESIGNS by nickname, and the variant,
parsed last, replaced the base design's config: the tiny package then
built at the variant's CORE_UTILIZATION. argv[1] is a JSON object of
directory -> the arguments DESIGNS holds for it.
"""

import json
import sys
import unittest

DESIGNS = json.loads(sys.argv[1])


class DesignsByDirectoryTest(unittest.TestCase):
    def test_base_keeps_its_own_config(self):
        self.assertEqual(DESIGNS["tiny"]["CORE_UTILIZATION"], "40")

    def test_variant_gets_its_own_config(self):
        self.assertEqual(DESIGNS["tiny-variant"]["CORE_UTILIZATION"], "30")


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
