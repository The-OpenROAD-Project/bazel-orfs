import json
import os
import subprocess
import tempfile
import unittest

class MergeArgumentsTest(unittest.TestCase):
    def test_merge_no_filter(self):
        with tempfile.TemporaryDirectory() as d:
            json1 = os.path.join(d, "1.json")
            json2 = os.path.join(d, "2.json")
            out = os.path.join(d, "out.mk")
            
            with open(json1, "w") as f: json.dump({"A": "1", "B": "2"}, f)
            with open(json2, "w") as f: json.dump({"B": "3", "C": "4"}, f)
            
            subprocess.check_call(["python3", "private/merge_arguments.py", out, json1, json2])
            
            with open(out) as f:
                content = f.read()
            
            self.assertIn("export A?=1\n", content)
            self.assertIn("export B?=3\n", content)
            self.assertIn("export C?=4\n", content)

    def test_merge_with_filter(self):
        with tempfile.TemporaryDirectory() as d:
            json1 = os.path.join(d, "1.json")
            filter_json = os.path.join(d, "filter.json")
            out = os.path.join(d, "out.mk")
            
            with open(json1, "w") as f: json.dump({"ALLOWED": "1", "FILTERED": "2", "UNKNOWN": "3"}, f)
            with open(filter_json, "w") as f: json.dump({"allowed": ["ALLOWED"], "known": ["ALLOWED", "FILTERED"]}, f)
            
            subprocess.check_call(["python3", "private/merge_arguments.py", out, "--filter", filter_json, json1])
            
            with open(out) as f:
                content = f.read()
            
            self.assertIn("export ALLOWED?=1\n", content)
            self.assertNotIn("export FILTERED?=2\n", content)
            self.assertIn("export UNKNOWN?=3\n", content)

if __name__ == "__main__":
    unittest.main()
