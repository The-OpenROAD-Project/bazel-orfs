"""The first two sentences of the video encode, with sound, at the size the
format promises: a broken voice, script or encoder fails here in seconds,
not after the full render.

argv: the voice .onnx and its .json.
"""

import os
import re
import subprocess
import sys
import unittest

import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import video  # noqa: E402

ONNX, CONFIG = sys.argv[1:3]


def probe(path):
    """ffmpeg's description of a file's streams (it exits 1 with no output
    file, after printing them)."""
    r = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    return r.stdout


class VideoTest(unittest.TestCase):
    def render(self, script, fmt):
        tmp = os.environ["TEST_TMPDIR"]
        out = os.path.join(tmp, "%s.mp4" % fmt)
        srt = os.path.join(tmp, "%s.srt" % fmt)
        self.assertEqual(
            video.main(
                [
                    "video.py",
                    "--script",
                    script,
                    "--format",
                    fmt,
                    "--voice-onnx",
                    ONNX,
                    "--voice-json",
                    CONFIG,
                    "--out",
                    out,
                    "--srt",
                    srt,
                    "--test",
                ]
            ),
            0,
        )
        return probe(out), open(srt).read()

    def check(self, script, fmt, size):
        streams, captions = self.render(script, fmt)
        self.assertRegex(streams, r"Video: h264.*%dx%d" % size)
        self.assertIn("Audio: aac", streams)
        seconds = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", streams)
        self.assertGreater(float(seconds.group(3)) + 60 * int(seconds.group(2)), 2)
        self.assertEqual(captions.count(" --> "), 2)

    def test_landscape(self):
        self.check("full", "landscape", (1920, 1080))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
