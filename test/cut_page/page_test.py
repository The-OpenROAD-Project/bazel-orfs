"""The module-cut search's page in a real browser, on a fixed state.

aes_state.json is a state the aes search pushed, with one arm running.
The page, served by the search's own server, is loaded by Chrome for
Testing's headless shell: it must log no error to the console, show every
arm with the running one marked, and draw a screenshot that is not blank.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zlib

from python.runfiles import runfiles

import record
import serve

R = runfiles.Create()


def png_colours(path):
    """The distinct pixel bytes of an 8-bit RGB(A) PNG's first rows: a
    blank page has one."""
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    i = 8
    idat = b""
    width = channels = None
    while i < len(data):
        n = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        body = data[i + 8 : i + 8 + n]
        if kind == b"IHDR":
            width = int.from_bytes(body[:4], "big")
            channels = {2: 3, 6: 4}[body[9]]
        elif kind == b"IDAT":
            idat += body
        i += 12 + n
    raw = zlib.decompress(idat)
    stride = 1 + width * channels
    # filter bytes make raw rows unreadable as pixels, but a blank image
    # compresses to identical rows after the first: count distinct rows
    rows = {
        raw[r * stride + 1 : (r + 1) * stride]
        for r in range(1, min(400, len(raw) // stride))
    }
    return len(rows)


class PageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(R.Rlocation(sys.argv[1])) as f:
            state = json.load(f)
        with open(R.Rlocation(sys.argv[2])) as f:
            page = f.read()
        cls.chrome = R.Rlocation(sys.argv[3])
        cls.state = state
        cls.srv = serve.Server("127.0.0.1", 0, "tok", page, lambda: state)
        cls.srv.start(heartbeat=False)
        cls.url = "http://127.0.0.1:%d/?token=tok" % cls.srv.port
        cls.tmp = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        cls.png = os.path.join(cls.tmp, "page.png")
        profile = os.path.join(cls.tmp, "profile")
        _, cls.console = record.chrome(
            cls.chrome, profile, cls.url, "1600x760", "png", cls.png
        )
        cls.dom, c = record.chrome(cls.chrome, profile, cls.url, "1600x760", "dom")
        cls.console += c

    def test_no_console_errors(self):
        errors = [l for l in self.console if "ERROR" in l or "Uncaught" in l]
        self.assertEqual(errors, [])

    def test_every_arm_shown_and_the_running_one_marked(self):
        shown = record.arm_states(self.dom)
        want = {
            a["id"]: ("running" if a["status"] == "running" else "done")
            for a in self.state["arms"]
        }
        self.assertEqual(shown, want)

    def test_the_period_plot_has_a_dot_per_finished_arm(self):
        done = [a for a in self.state["arms"] if a["P"] is not None]
        self.assertIn("★ best", self.dom)
        self.assertIn("kept module types", self.dom)
        self.assertGreaterEqual(self.dom.count("<circle"), len(done))

    def test_the_screenshot_is_not_blank(self):
        self.assertGreater(png_colours(self.png), 20)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
