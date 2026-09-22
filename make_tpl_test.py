"""make.tpl: a deployed tree runs its own stage's targets and refuses another stage's.

Renders the template the way the rules do, with a stub make that echoes
its arguments, and runs it as sh.
"""

import os
import subprocess
import sys
import tempfile
import unittest


def render(stage, label="//pkg:flow_" + "x"):
    d = tempfile.mkdtemp(prefix="make_tpl.")
    stub = os.path.join(d, "make_stub")
    with open(stub, "w") as f:
        f.write('#!/bin/sh\necho "STUB $@"\n')
    os.chmod(stub, 0o755)
    with open("make.tpl") as f:
        text = f.read()
    for k, v in {
        "${MAKE_PATH}": stub,
        "${YOSYS_PATH}": "",
        "${OPENROAD_PATH}": "/bin/true",
        "${OPENROAD_QT_PATH}": "/bin/true",
        "${OPENSTA_PATH}": "/bin/true",
        "${KLAYOUT_PATH}": "/bin/true",
        "${STDBUF_PATH}": "",
        "${FLOW_HOME}": d,
        "${DEPLOY_STAGE}": stage,
        "${DEPLOY_LABEL}": label,
        '"$@"': 'DESIGN_CONFIG="config.mk" "$@"',
    }.items():
        text = text.replace(k, v)
    path = os.path.join(d, "make")
    with open(path, "w") as f:
        f.write(text)
    return path


def run(make, *args, env=None):
    e = dict(os.environ)
    e.pop("FLOW_HOME", None)
    e.pop("ORFS_DEPLOY_ANY_STAGE", None)
    if env:
        e.update(env)
    return subprocess.run(["sh", make] + list(args), capture_output=True, text=True, env=e)


class DeployStageTest(unittest.TestCase):
    def test_own_stage_and_its_substeps_pass(self):
        make = render("floorplan")
        for target in ["do-floorplan", "do-2_2_floorplan_macro", "do-1_3_floorplan_to_place", "run", "gui_floorplan", "SKIP_REPORT_METRICS=1"]:
            r = run(make, target)
            self.assertEqual(r.returncode, 0, (target, r.stderr))
            self.assertIn("STUB", r.stdout, target)

    def test_another_stage_is_refused_with_the_pointer(self):
        make = render("floorplan", label="//test:xs_floorplan")
        for target in ["do-place", "do-3_3_place_gp", "do-cts", "do-synth", "do-yosys-canonicalize"]:
            r = run(make, target)
            self.assertEqual(r.returncode, 2, (target, r.stderr))
            self.assertNotIn("STUB", r.stdout)
            self.assertIn("deployed for the floorplan stage", r.stderr)
            self.assertIn("//test:xs_floorplan", r.stderr)
            self.assertIn("_deps -- --install", r.stderr)

    def test_bare_stage_targets_are_still_refused(self):
        make = render("floorplan")
        r = run(make, "place")
        self.assertEqual(r.returncode, 2)
        self.assertIn("refusing target 'place'", r.stderr)

    def test_the_hatch_warns_and_runs(self):
        make = render("floorplan")
        r = run(make, "do-place", env={"ORFS_DEPLOY_ANY_STAGE": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING", r.stderr)
        self.assertIn("STUB", r.stdout)

    def test_a_second_stage_table(self):
        make = render("place")
        self.assertEqual(run(make, "do-3_4_place_resized").returncode, 0)
        self.assertEqual(run(make, "do-place").returncode, 0)
        self.assertEqual(run(make, "do-floorplan").returncode, 2)
        self.assertEqual(run(make, "do-4_1_cts").returncode, 2)

    def test_gds_and_abstract_trees(self):
        # deploy_stage_of("6_gds") is "gds", which runs the final targets;
        # deploy_stage_of("7_abstract") is "abstract".
        make = render("gds")
        self.assertEqual(run(make, "do-6_report").returncode, 0)
        self.assertEqual(run(make, "do-5_2_route").returncode, 2)
        make = render("abstract")
        self.assertEqual(run(make, "do-generate_abstract").returncode, 0)
        self.assertEqual(run(make, "do-7_1_abstract").returncode, 0)
        self.assertEqual(run(make, "do-final").returncode, 2)

    def test_the_build_itself_is_not_fenced(self):
        # Inside a bazel action FLOW_HOME comes from the environment and the
        # tree is not a deployed one; the action runs what the rule asks.
        make = render("floorplan")
        d = os.path.dirname(make)
        bin_dir = os.path.join(d, "bin")
        os.mkdir(bin_dir)
        os.symlink(os.path.join(d, "make_stub"), os.path.join(bin_dir, "make"))
        path = bin_dir + os.pathsep + os.environ.get("PATH", "")
        r = run(make, "do-place", env={"FLOW_HOME": d, "PATH": path})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("STUB", r.stdout)

    def test_the_injected_design_config_is_passed_through(self):
        make = render("floorplan")
        r = run(make, "do-floorplan")
        self.assertIn('DESIGN_CONFIG=config.mk do-floorplan', r.stdout)

    def test_no_stage_means_no_restriction(self):
        make = render("")
        self.assertEqual(run(make, "do-place").returncode, 0)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])) or ".")
    unittest.main()
