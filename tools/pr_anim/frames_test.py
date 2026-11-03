"""frames.py: the pointer is drawn where the mouse is, the APNG animates."""

import os
import tempfile
import unittest

from PIL import Image

import frames as F


class CursorKindTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(F.cursor_kind("col-resize"), "col-resize")
        self.assertEqual(F.cursor_kind("ew-resize"), "col-resize")
        self.assertEqual(F.cursor_kind("progress"), "progress")
        self.assertEqual(F.cursor_kind("wait"), "wait")
        self.assertEqual(F.cursor_kind("pointer"), "pointer")
        self.assertEqual(F.cursor_kind("text"), "text")

    def test_url_cursor_falls_back_to_its_keyword(self):
        self.assertEqual(F.cursor_kind('url("x.cur"), progress'), "progress")

    def test_unknown_is_an_arrow(self):
        for value in ("auto", "default", "", None, "grab"):
            self.assertEqual(F.cursor_kind(value), "arrow")


class DrawPointerTest(unittest.TestCase):
    def changed(self, kind):
        """The bounding box of the pixels draw_pointer changed."""
        image = Image.new("RGB", (200, 200), (128, 128, 128))
        F.draw_pointer(image, 100, 100, kind)
        diff = Image.eval(image.convert("L"), lambda v: 255 if v != 128 else 0)
        return diff.getbbox()

    def test_arrow_hot_spot_is_its_tip(self):
        left, top, right, bottom = self.changed("arrow")
        self.assertLessEqual(abs(left - 100), 2)
        self.assertLessEqual(abs(top - 100), 2)
        self.assertGreater(bottom - top, 15)

    def test_col_resize_is_centred(self):
        left, top, right, bottom = self.changed("col-resize")
        self.assertLess(left, 92)
        self.assertGreater(right, 108)

    def test_progress_adds_a_spinner_below_right(self):
        arrow = self.changed("arrow")
        progress = self.changed("progress")
        self.assertGreater(progress[2], arrow[2])
        self.assertGreater(progress[3], arrow[3])

    def test_every_kind_draws(self):
        for kind in ("arrow", "col-resize", "progress", "wait", "pointer", "text"):
            self.assertIsNotNone(self.changed(kind), kind)


class WriteApngTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        self.out = os.path.join(self.dir, "a.png")

    def frames(self, n, size=(320, 200)):
        return [Image.new("RGB", size, (i * 40 % 256, 0, 0)) for i in range(n)]

    def test_animates_and_loops(self):
        F.write_apng(self.frames(3), [100, 200, 300], self.out)
        with Image.open(self.out) as im:
            self.assertEqual(im.n_frames, 3)
            self.assertEqual(im.info.get("loop"), 0)
            durations = []
            for i in range(im.n_frames):
                im.seek(i)
                durations.append(im.info["duration"])
        self.assertEqual(durations, [100, 200, 300])

    def test_scales_down_to_width(self):
        F.write_apng(self.frames(2, (640, 400)), [50, 50], self.out, width=320)
        with Image.open(self.out) as im:
            self.assertEqual(im.size, (320, 200))

    def test_writes_no_text_metadata(self):
        F.write_apng(self.frames(2), [50, 50], self.out)
        with open(self.out, "rb") as f:
            data = f.read()
        for chunk in (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME"):
            self.assertNotIn(chunk, data)

    def test_mismatched_durations_are_refused(self):
        with self.assertRaises(ValueError):
            F.write_apng(self.frames(2), [50], self.out)

    def test_no_frames_is_refused(self):
        with self.assertRaises(ValueError):
            F.write_apng([], [], self.out)


if __name__ == "__main__":
    unittest.main()
