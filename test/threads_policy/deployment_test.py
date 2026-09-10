#!/usr/bin/env python3
"""The layout is what tells one arm's files from another's.

Every test here builds the directory shape a real deployment has, taken
from a deployed nangate45/gcd cts reproducer:

    <root>/+orfs_repositories+orfs/flow/designs/nangate45/gcd/
        results/nangate45/gcd/base/{3_place.odb,4_cts.short.mk}

The one that matters is the last: reading a sample from a different
arm's directory would be reported as that arm's result, which is the
failure this module exists to prevent.
"""

import os
import shutil
import tempfile
import unittest

import deployment


def make_tree(root, platform="nangate45", design="gcd", variants=("base",)):
    results = os.path.join(
        root, "+orfs_repositories+orfs", "flow", "designs", platform, design, "results"
    )
    for variant in variants:
        path = os.path.join(results, platform, design, variant)
        os.makedirs(path)
        open(os.path.join(path, "3_place.odb"), "w").close()
    return results


class Locate(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def test_platform_and_design_are_discovered_from_the_base_variant(self):
        make_tree(self.root)
        deploy = deployment.Deployment(self.root)
        self.assertEqual(deploy.platform, "nangate45")
        self.assertEqual(deploy.design, "gcd")

    def test_logs_are_a_sibling_of_results(self):
        results = make_tree(self.root)
        deploy = deployment.Deployment(self.root)
        self.assertEqual(
            deploy.logs_root, os.path.join(os.path.dirname(results), "logs")
        )
        self.assertTrue(deploy.logs("t8_r1").endswith("logs/nangate45/gcd/t8_r1"))

    def test_a_tree_with_no_base_variant_is_not_a_deployment(self):
        os.makedirs(os.path.join(self.root, "results", "nangate45", "gcd", "t8_r1"))
        with self.assertRaises(SystemExit):
            deployment.Deployment(self.root)

    def test_two_deployments_under_one_root_is_an_error_not_a_guess(self):
        make_tree(self.root, design="gcd")
        make_tree(self.root, design="aes")
        with self.assertRaises(SystemExit):
            deployment.Deployment(self.root)

    def test_extra_variants_do_not_change_what_is_located(self):
        # The #968 heuristic returned the deepest directory holding an
        # .odb, so a second variant changed the answer. This one keys
        # off `base`, which every deployment has and no arm writes.
        make_tree(self.root, variants=("base", "t1_r1", "t16_r2"))
        deploy = deployment.Deployment(self.root)
        self.assertEqual((deploy.platform, deploy.design), ("nangate45", "gcd"))
        self.assertTrue(deploy.results("t16_r2").endswith("gcd/t16_r2"))


class Variants(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        make_tree(self.root)
        self.deploy = deployment.Deployment(self.root)

    def test_an_arm_is_named_by_its_threads_and_repeat(self):
        self.assertEqual(deployment.arm_variant(16, 2), "t16_r2")

    def test_clone_gives_the_arm_the_previous_stage_outputs(self):
        self.deploy.clone_base("t8_r1")
        self.assertTrue(
            os.path.exists(os.path.join(self.deploy.results("t8_r1"), "3_place.odb"))
        )

    def test_clone_keeps_symlinks_as_symlinks(self):
        # base is mostly symlinks into the Bazel cache; copying their
        # bytes per arm would multiply the tree for no benefit.
        base = self.deploy.results("base")
        os.symlink("/nonexistent/3_place.sdc", os.path.join(base, "3_place.sdc"))
        self.deploy.clone_base("t8_r1")
        self.assertTrue(
            os.path.islink(os.path.join(self.deploy.results("t8_r1"), "3_place.sdc"))
        )

    def test_clone_removes_a_half_finished_previous_attempt(self):
        target = self.deploy.results("t8_r1")
        os.makedirs(target)
        open(os.path.join(target, "4_1_cts.odb"), "w").close()
        self.deploy.clone_base("t8_r1")
        self.assertFalse(os.path.exists(os.path.join(target, "4_1_cts.odb")))

    def test_clone_removes_a_stale_log_directory(self):
        logs = self.deploy.logs("t8_r1")
        os.makedirs(logs)
        open(os.path.join(logs, "4_1_cts.log"), "w").close()
        self.deploy.clone_base("t8_r1")
        self.assertFalse(os.path.exists(os.path.join(logs, "4_1_cts.log")))

    def test_two_arms_get_separate_directories(self):
        self.deploy.clone_base("t1_r1")
        self.deploy.clone_base("t16_r1")
        self.assertNotEqual(self.deploy.results("t1_r1"), self.deploy.results("t16_r1"))


if __name__ == "__main__":
    unittest.main()
