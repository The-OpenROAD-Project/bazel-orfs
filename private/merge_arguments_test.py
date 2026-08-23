import json
import os
import tempfile
import unittest
import subprocess
import sys


class TestMergeArguments(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        # Determine the path to merge_arguments.py relative to this test
        self.script_path = os.path.join(os.path.dirname(__file__), "merge_arguments.py")

    def write_json(self, name, data):
        path = os.path.join(self.temp_dir.name, name)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def run_script(self, args):
        cmd = [sys.executable, self.script_path] + args
        subprocess.check_call(cmd)

    def test_basic_merge_precedence(self):
        json1 = self.write_json("1.json", {"A": "1", "B": "1"})
        json2 = self.write_json("2.json", {"B": "2", "C": "2"})
        out_mk = os.path.join(self.temp_dir.name, "out.mk")

        self.run_script([out_mk, json1, json2])

        with open(out_mk) as f:
            content = f.read()

        expected = "export A?=1\n" "export B?=2\n" "export C?=2\n"
        self.assertEqual(content, expected)

    def test_filtering(self):
        json_data = self.write_json("data.json", {"A": "1", "B": "2", "C": "3"})
        filter_json = self.write_json("filter.json", {"drop": ["B"]})
        out_mk = os.path.join(self.temp_dir.name, "out.mk")

        self.run_script([out_mk, "--filter", filter_json, json_data])

        with open(out_mk) as f:
            content = f.read()

        expected = "export A?=1\n" "export C?=3\n"
        self.assertEqual(content, expected)

    def test_filtering_keeps_everything_not_on_the_denylist(self):
        # MORATORIUM(filter-decided-once): the script applies the denylist and
        # decides nothing. A variable unknown to ORFS variables.yaml is simply
        # never put on the denylist by dropped_variables(), which is how the
        # escape hatch survives — see private/stages.bzl.
        json_data = self.write_json("data.json", {"A": "1", "B": "2", "CUSTOM": "9"})
        filter_json = self.write_json("filter.json", {"drop": ["B"]})
        out_mk = os.path.join(self.temp_dir.name, "out.mk")

        self.run_script([out_mk, "--filter", filter_json, json_data])

        with open(out_mk) as f:
            content = f.read()

        expected = "export A?=1\n" "export CUSTOM?=9\n"
        self.assertEqual(content, expected)

    def test_empty_denylist_keeps_everything(self):
        json_data = self.write_json("data.json", {"A": "1", "B": "2"})
        filter_json = self.write_json("filter.json", {"drop": []})
        out_mk = os.path.join(self.temp_dir.name, "out.mk")

        self.run_script([out_mk, "--filter", filter_json, json_data])

        with open(out_mk) as f:
            content = f.read()

        expected = "export A?=1\n" "export B?=2\n"
        self.assertEqual(content, expected)

    def test_mk_includes(self):
        json_data = self.write_json("data.json", {"A": "1"})
        out_mk = os.path.join(self.temp_dir.name, "out.mk")

        self.run_script(
            [out_mk, "--include", "file1.mk", "--include", "file2.mk", json_data]
        )

        with open(out_mk) as f:
            content = f.read()

        expected = "export A?=1\n" "include file1.mk\n" "include file2.mk\n"
        self.assertEqual(content, expected)


if __name__ == "__main__":
    unittest.main()
