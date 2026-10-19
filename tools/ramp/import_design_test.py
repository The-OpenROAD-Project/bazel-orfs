"""import_design against the pinned ORFS: gcd imported, and what it refuses."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import import_design

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW = os.path.dirname(os.path.abspath(os.environ["ORFS_MAKEFILE"]))
MAKE = os.path.abspath(os.environ["IMPORT_MAKE"])
GCD = os.path.join(FLOW, "designs", "asap7", "gcd")


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        os.environ["BUILD_WORKSPACE_DIRECTORY"] = self.ws
        os.environ["BUILD_WORKING_DIRECTORY"] = self.ws
        with open(os.path.join(self.ws, "MODULE.bazel"), "w") as f:
            f.write('module(name = "bazel-orfs")\n')

    def run_import(self, design_dir, *extra):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = import_design.main(
                [design_dir, "--orfs", FLOW, "--make", MAKE] + list(extra)
            )
        return rc, out.getvalue(), err.getvalue()

    def read(self, *path):
        with open(os.path.join(self.ws, *path)) as f:
            return f.read()

    def test_gcd(self):
        rc, out, err = self.run_import(GCD)
        self.assertEqual(rc, 0, err)
        pkg = os.path.join("imported", "asap7", "gcd")
        build = self.read(pkg, "BUILD.bazel")
        self.assertTrue(build.startswith(import_design.MARKER))
        for line in [
            'name = "gcd",',
            'pdk = "@orfs//flow:asap7",',
            '"SDC_FILE": ["constraint.sdc"],',
            'verilog_files = ["designs/src/gcd/gcd.v"],',
            '"CORE_UTILIZATION": "65",',
            '"PLACE_DENSITY": "0.35",',
            '"SYNTH_USE_SYN": "1",',
        ]:
            self.assertIn(line, build)
        # The platform's own settings are not the design's.
        self.assertNotIn("TECH_LEF", build)
        self.assertEqual(
            self.read(pkg, "config.mk"), open(os.path.join(GCD, "config.mk")).read()
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.ws, pkg, "designs/src/gcd/gcd.v"))
        )
        self.assertIn("bazelisk build //imported/asap7/gcd:gcd_synth", out)

    def test_reimport_replaces(self):
        self.assertEqual(self.run_import(GCD)[0], 0)
        stray = os.path.join(self.ws, "imported", "asap7", "gcd", "stray.v")
        open(stray, "w").close()
        self.assertEqual(self.run_import(GCD)[0], 0)
        self.assertFalse(os.path.exists(stray))

    def test_refuses_to_replace_what_it_did_not_write(self):
        dest = os.path.join(self.ws, "mine")
        os.makedirs(dest)
        open(os.path.join(dest, "README"), "w").close()
        rc, _, err = self.run_import(GCD, "--dest", dest)
        self.assertEqual(rc, 1)
        self.assertIn("is not an import: refusing to replace it", err)
        self.assertTrue(os.path.exists(os.path.join(dest, "README")))

    def test_refuses_outside_a_clone(self):
        os.remove(os.path.join(self.ws, "MODULE.bazel"))
        rc, _, err = self.run_import(GCD)
        self.assertEqual(rc, 1)
        self.assertIn("is not a bazel-orfs clone", err)

    def test_refuses_blocks(self):
        rc, _, err = self.run_import(os.path.join(HERE, "testdata", "blocks"))
        self.assertEqual(rc, 1)
        self.assertIn("sets BLOCKS", err)
        self.assertIn("tools/ramp/import_design.py is the file to patch", err)

    def test_refuses_a_missing_file(self):
        rc, _, err = self.run_import(os.path.join(HERE, "testdata", "missing_file"))
        self.assertEqual(rc, 1)
        self.assertIn("SDC_FILE names", err)
        self.assertIn("no_such_constraint.sdc, which does not exist", err)


if __name__ == "__main__":
    unittest.main()
