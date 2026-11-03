"""The scenes in scenes/ load, and every step is one record.py runs."""

import glob
import os
import runpy
import unittest

ACTIONS = {
    "wait_for",
    "move",
    "click",
    "dblclick",
    "drag",
    "key",
    "eval",
    "recording",
    "ws_delay",
    "wait",
    "frame",
}
OPTIONS = {"steps", "anchor", "dx", "dy", "by", "optional", "timeout"}
SCENES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenes")


class ScenesTest(unittest.TestCase):
    def test_every_step_is_known(self):
        paths = glob.glob(os.path.join(SCENES, "1*.py"))
        self.assertGreater(len(paths), 0)
        for path in paths:
            scene = runpy.run_path(path)
            self.assertIn("CLIP", scene, path)
            for step in scene["STEPS"]:
                actions = ACTIONS & set(step)
                self.assertEqual(len(actions), 1, (path, step))
                self.assertLessEqual(set(step) - ACTIONS, OPTIONS, (path, step))


if __name__ == "__main__":
    unittest.main()
