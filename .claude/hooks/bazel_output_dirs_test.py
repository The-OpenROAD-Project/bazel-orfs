"""bazel_output_dirs.py adds a checkout's own output base to its local
settings, keeps what is there, and adds nothing before the first build."""

import json
import os
import tempfile
import unittest

import bazel_output_dirs


def make_checkout(root, with_build=True):
    project = os.path.join(root, "checkout")
    os.makedirs(project)
    if with_build:
        base = os.path.join(root, "cache", "_bazel_u", "0123abcd")
        out = os.path.join(base, "execroot", "_main", "bazel-out")
        os.makedirs(os.path.join(out, "k8-fastbuild", "bin"))
        os.symlink(out, os.path.join(project, "bazel-out"))
        os.symlink(
            os.path.join(out, "k8-fastbuild", "bin"), os.path.join(project, "bazel-bin")
        )
        os.symlink(
            os.path.join(base, "execroot", "_main"),
            os.path.join(project, "bazel-checkout"),
        )
        return project, os.path.realpath(base)
    return project, None


def local_settings(project):
    with open(os.path.join(project, ".claude", "settings.local.json")) as f:
        return json.load(f)


class BazelOutputDirs(unittest.TestCase):
    def test_adds_the_output_base_once(self):
        with tempfile.TemporaryDirectory() as root:
            project, base = make_checkout(root)
            self.assertTrue(bazel_output_dirs.update(project))
            self.assertEqual(
                local_settings(project)["permissions"]["additionalDirectories"], [base]
            )
            # idempotent: a second session writes nothing
            self.assertFalse(bazel_output_dirs.update(project))

    def test_keeps_existing_settings(self):
        with tempfile.TemporaryDirectory() as root:
            project, base = make_checkout(root)
            os.makedirs(os.path.join(project, ".claude"))
            with open(
                os.path.join(project, ".claude", "settings.local.json"), "w"
            ) as f:
                json.dump(
                    {
                        "permissions": {
                            "allow": ["Bash(ls:*)"],
                            "additionalDirectories": ["/x"],
                        }
                    },
                    f,
                )
            self.assertTrue(bazel_output_dirs.update(project))
            s = local_settings(project)
            self.assertEqual(s["permissions"]["allow"], ["Bash(ls:*)"])
            self.assertEqual(s["permissions"]["additionalDirectories"], ["/x", base])

    def test_nothing_before_the_first_build(self):
        with tempfile.TemporaryDirectory() as root:
            project, _ = make_checkout(root, with_build=False)
            self.assertFalse(bazel_output_dirs.update(project))
            self.assertFalse(
                os.path.exists(os.path.join(project, ".claude", "settings.local.json"))
            )


if __name__ == "__main__":
    unittest.main()
