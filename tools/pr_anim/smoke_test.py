"""record.py in the pinned headless Chrome on a local page: frames are
taken, and the pointer follows the cursor the page asks for.

Manual: the browser needs the desktop libraries its deb.deps names, which
a CI runner may not have.
"""

import os
import sys
import tempfile
import unittest

from PIL import Image

import record


class SmokeTest(unittest.TestCase):
    def test_records_the_cursors_the_page_asks_for(self):
        browser, page, scene = sys.argv[1:4]
        out = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")), "s.png")
        rec = record.main(
            [
                "--url",
                "file://" + os.path.abspath(page),
                "--scene",
                os.path.abspath(scene),
                "--out",
                out,
                "--browser",
                browser,
                "--label",
                "smoke",
            ]
        )
        self.assertIn("col-resize", rec.cursors)
        self.assertEqual(rec.cursors[-1], "progress")
        self.assertEqual(rec.cursors[0], "arrow")
        with Image.open(out) as im:
            self.assertGreater(im.n_frames, 10)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
