#!/usr/bin/env python3
"""Unit tests for retime_modules.py"""

import json
import os
import tempfile
import unittest

from retime_modules import check, unmatched


class UnmatchedTest(unittest.TestCase):
    def test_bare_name_misses_slang_name(self):
        modules = ["Top", "RegFile$Top.core.regFile"]
        self.assertEqual(unmatched(["RegFile"], modules), ["RegFile"])

    def test_glob_and_top_match(self):
        modules = ["Top", "RegFile$Top.core.regFile"]
        self.assertEqual(unmatched(["RegFile*", "Top"], modules), [])

    def test_only_the_missing_are_named(self):
        self.assertEqual(unmatched(["a*", "b", "c"], ["a1", "c"]), ["b"])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, content):
        path = os.path.join(self.dir.name, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_sidecars_and_kept_json(self):
        sidecar = self.write("adder.name", "\\adder$top.a\n")
        kept = self.write("kept.json", json.dumps({"modules": ["counter$top.c"]}))
        spec = {
            "groups": [
                {
                    "patterns": ["adder*", "counter*", "top"],
                    "names": ["top"],
                    "name_files": [sidecar],
                    "kept_json": [kept],
                }
            ]
        }
        self.assertEqual(check(spec), [])

    def test_entry_for_another_group_is_an_error(self):
        # A partition whose SYNTH_RETIME_MODULES is its own (partition_arguments)
        # is not reached by the design's list.
        spec = {
            "groups": [
                {"patterns": ["adder"], "names": ["top"]},
                {"patterns": ["adder"], "names": ["adder"]},
            ]
        }
        errors = check(spec)
        self.assertEqual(len(errors), 1)
        self.assertIn("adder matches none", errors[0])


if __name__ == "__main__":
    unittest.main()
