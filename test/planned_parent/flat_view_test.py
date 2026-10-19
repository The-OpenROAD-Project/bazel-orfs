"""The flat view puts each block back in its macro's place, connected.

tools/flat_view replaces every instance of a block's macro in the parent
with the block's own cells. What is checked on the miniature's global
route with its blocks at CTS: each macro instance is gone, every cell of
its block is under <instance>/ and inside the macro's footprint, and every
macro pin's parent net reaches the block's cells.

    flat_view_test.py <flat_view.json>
"""

import json
import sys
import unittest


class FlatViewTest(unittest.TestCase):
    def test_blocks_in_place(self):
        with open(sys.argv[1]) as f:
            blocks = json.load(f)
        self.assertEqual(
            sorted(b["block"] for b in blocks),
            ["BlockA", "BlockB", "BlockC", "BlockD"],
            "one instance of each hardened block",
        )
        for b in blocks:
            name = b["instance"]
            self.assertEqual(b["macro_left"], 0, "%s's macro is gone" % name)
            self.assertEqual(
                b["copied"], b["block_cells"], "every cell of %s is copied" % name
            )
            self.assertEqual(b["outside"], 0, "%s's cells stay in its footprint" % name)
            self.assertGreater(b["pins"], 0, "%s has signal pins" % name)
            self.assertEqual(
                b["unjoined"], 0, "every pin of %s joins its parent net" % name
            )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
