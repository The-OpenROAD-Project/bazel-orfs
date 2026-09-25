"""deploy.tpl: a deployed tree holds copies of the design's build outputs.

The runfiles a deploy copies are symlinks. Those that point into this
configuration's bazel-out/<cfg>/bin (the previous stage's results, a
memories directory) must arrive as copies, so an edit in the tree cannot
write through into a bazel action output. Exec-configuration tools and
nested .runfiles trees stay links.

Lays out a fake exec root and runfiles tree, renders the template the way
the rules do, and runs it with --install.
"""

import os
import subprocess
import tempfile
import unittest


def write(path, text, mode=0o555):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)


def link(target, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    os.symlink(target, path)


class DeployCopiesTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="deploy_tpl.")
        bin_dir = os.path.join(self.root, "execroot/bazel-out/k8-fastbuild/bin")
        exec_dir = os.path.join(self.root, "execroot/bazel-out/k8-opt-exec/bin")
        self.odb = os.path.join(bin_dir, "pkg/results/1_synth.odb")
        write(self.odb, "odb\n")
        write(os.path.join(bin_dir, "pkg/memories/mem.json"), "{}\n")
        write(os.path.join(bin_dir, "pkg/make_flow"), '#!/bin/sh\necho MAKE "$@"\n')
        write(os.path.join(exec_dir, "tool/tool.sh"), "#!/bin/sh\n")
        os.makedirs(os.path.join(bin_dir, "pkg/flow_deps.sh.runfiles/_main"))

        self.deploy = os.path.join(self.root, "deploy")
        main = self.deploy + ".runfiles/_main"
        for rel in [
            "pkg/results/1_synth.odb",
            "pkg/memories",
            "pkg/make_flow",
            "pkg/flow_deps.sh.runfiles",
        ]:
            link(os.path.join(bin_dir, rel), os.path.join(main, rel))
        link(os.path.join(exec_dir, "tool/tool.sh"), os.path.join(main, "tool/tool.sh"))
        write(os.path.join(main, "pkg/config.mk"), "export DESIGN_NAME = flow\n", 0o644)
        self.main = main

        with open("deploy.tpl") as f:
            text = f.read()
        for k, v in {
            "${CONFIG}": "pkg/config.mk",
            "${GENFILES}": "pkg/config.mk",
            "${MAKE}": "pkg/make_flow",
            "${NAME}": "flow_deps",
            "${PACKAGE}": "pkg",
            "${RENAMES}": "",
        }.items():
            text = text.replace(k, v)
        write(self.deploy, text, 0o755)

        self.out = os.path.join(self.root, "out")
        self.run_deploy()
        self.dst = os.path.join(self.out, "_main")

    def run_deploy(self):
        env = dict(os.environ, BUILD_WORKSPACE_DIRECTORY=os.path.join(self.root, "ws"))
        r = subprocess.run(
            [self.deploy, "--install", self.out],
            cwd=self.main,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_results_are_copies(self):
        odb = os.path.join(self.dst, "pkg/results/1_synth.odb")
        self.assertFalse(os.path.islink(odb))
        with open(odb) as f:
            self.assertEqual(f.read(), "odb\n")

    def test_an_edit_stays_in_the_tree(self):
        odb = os.path.join(self.dst, "pkg/results/1_synth.odb")
        os.chmod(odb, 0o644)
        with open(odb, "w") as f:
            f.write("edited\n")
        with open(self.odb) as f:
            self.assertEqual(f.read(), "odb\n")

    def test_the_make_script_still_runs(self):
        make = os.path.join(self.dst, "pkg/make_flow")
        self.assertFalse(os.path.islink(make))
        r = subprocess.run([make, "do-floorplan"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MAKE do-floorplan", r.stdout)

    def test_a_directory_output_is_a_copy(self):
        mem = os.path.join(self.dst, "pkg/memories")
        self.assertFalse(os.path.islink(mem))
        self.assertTrue(os.path.isfile(os.path.join(mem, "mem.json")))

    def test_a_second_deploy_over_the_tree(self):
        # The copies from the first deploy are where the runfiles' links land
        # the second time; the tree ends up with copies again.
        self.run_deploy()
        odb = os.path.join(self.dst, "pkg/results/1_synth.odb")
        self.assertFalse(os.path.islink(odb))
        self.assertFalse(os.path.islink(os.path.join(self.dst, "pkg/memories")))

    def test_a_relative_install_is_relative_to_where_bazel_run_was_invoked(self):
        # bazel run executes the deploy from its runfiles tree and says where
        # the user was in BUILD_WORKING_DIRECTORY; a relative --install means
        # a directory there, not one inside the tree being copied.
        cwd = os.path.join(self.root, "user_cwd")
        os.makedirs(cwd)
        env = dict(
            os.environ,
            BUILD_WORKSPACE_DIRECTORY=os.path.join(self.root, "ws"),
            BUILD_WORKING_DIRECTORY=cwd,
        )
        r = subprocess.run(
            [self.deploy, "--install", "rel/tree"],
            cwd=self.main,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        odb = os.path.join(cwd, "rel/tree/_main/pkg/results/1_synth.odb")
        self.assertTrue(os.path.isfile(odb), r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.main, "rel")))
        self.assertIn("installed to: %s/rel/tree\n" % cwd, r.stdout)

    def test_tools_and_runfiles_trees_stay_links(self):
        self.assertTrue(os.path.islink(os.path.join(self.dst, "tool/tool.sh")))
        self.assertTrue(
            os.path.islink(os.path.join(self.dst, "pkg/flow_deps.sh.runfiles"))
        )


if __name__ == "__main__":
    unittest.main()
