"""What the page shows carries no local path."""

import unittest

import generate_cut


class ScrubTest(unittest.TestCase):
    def test_workspace_paths_become_relative(self):
        self.assertEqual(
            generate_cut.scrub("wrote /w/s/tmp/out.json", "/w/s", "/w"),
            "wrote tmp/out.json",
        )

    def test_the_home_directory_becomes_a_tilde(self):
        self.assertEqual(
            generate_cut.scrub("see /h/u/elsewhere/x.log", "/w/s", "/h/u"),
            "see ~/elsewhere/x.log",
        )

    def test_the_workspace_itself(self):
        self.assertEqual(generate_cut.scrub("in /w/s", "/w/s", "/h"), "in .")


if __name__ == "__main__":
    unittest.main()
