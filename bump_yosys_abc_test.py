"""Enforce the yosys<->abc lockstep pairing on this repo's MODULE.bazel.

The bump path only *warns* on a pairing violation: BCR availability and
yosys release cadence don't always line up, and blocking the bumper on
that would be more disruptive than the lurking quality risk.  The hard
check lives here instead, on the same ``check_yosys_abc_pair`` the
``--check-yosys-abc`` CLI entrypoint uses, so a mismatched pin cannot
land on main.
"""

import os
import unittest

import bump_impl

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


class TestPairingCheck(unittest.TestCase):
    """The check itself, so a green repo check means something."""

    def test_mismatched_pair_fails(self):
        content = (
            'bazel_dep(name = "abc", version = "0.62-yosyshq")\n'
            'bazel_dep(name = "yosys", version = "0.64")\n'
        )
        ok, msg = bump_impl.check_yosys_abc_pair(content)
        self.assertFalse(ok)
        self.assertIn("expects abc", msg)

    def test_unknown_yosys_series_fails(self):
        content = (
            'bazel_dep(name = "abc", version = "0.1-yosyshq")\n'
            'bazel_dep(name = "yosys", version = "0.1")\n'
        )
        ok, msg = bump_impl.check_yosys_abc_pair(content)
        self.assertFalse(ok)
        self.assertIn("no known abc pairing", msg)


class TestRepoModuleFile(unittest.TestCase):
    def test_module_bazel_declares_a_known_pair(self):
        with open(os.path.join(REPO_ROOT, "MODULE.bazel")) as f:
            ok, msg = bump_impl.check_yosys_abc_pair(f.read())

        # An empty message is the both-declared-and-matched verdict; the
        # "only one of yosys/abc is declared" note also comes back ok, but
        # this root module must always pin both in lockstep.
        self.assertEqual((ok, msg), (True, ""))


if __name__ == "__main__":
    unittest.main()
