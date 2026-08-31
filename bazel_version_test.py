"""Keep the Bazel floor in MODULE.bazel equal to .bazelversion.

``module(bazel_compatibility = ...)`` is the only version floor an obsolete
Bazel cannot walk past: it is checked during module resolution, before
anything is fetched or built, and it applies to downstream consumers of
bazel-orfs as well as to this repo.  ``.bazelversion``, by contrast, is a
bazelisk convention — a distro ``bazel``, or a consumer with its own
``.bazelversion``, never sees ours.

The two therefore have to be maintained together, and this test is what
makes that happen: bumping ``.bazelversion`` without moving the floor turns
the build red, with the fix named in the failure.  README.md quotes the
floor to consumers, so it is held to the same version.
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# The sole >= constraint inside the root module()'s bazel_compatibility list.
FLOOR = re.compile(r"""bazel_compatibility\s*=\s*\[\s*['"]>=([^'"]+)['"]""")


def read(name):
    with open(os.path.join(REPO_ROOT, name), encoding="utf-8") as handle:
        return handle.read()


class BazelVersionTest(unittest.TestCase):
    def floor(self, filename):
        match = FLOOR.search(read(filename))
        self.assertIsNotNone(
            match,
            '%s declares no `bazel_compatibility = [">=<version>"]`; without '
            "it an obsolete Bazel gets no hard failure." % filename,
        )
        return match.group(1)

    def test_module_floor_matches_bazelversion(self):
        pinned = read(".bazelversion").strip()
        floor = self.floor("MODULE.bazel")
        self.assertEqual(
            floor,
            pinned,
            "MODULE.bazel's bazel_compatibility floor (>=%s) has drifted from "
            ".bazelversion (%s). Set the floor to the pinned version — a stale "
            "floor lets an obsolete Bazel through." % (floor, pinned),
        )

    def test_readme_quotes_the_same_floor(self):
        pinned = read(".bazelversion").strip()
        floor = self.floor("README.md")
        self.assertEqual(
            floor,
            pinned,
            "README.md tells users the minimum Bazel is %s, but .bazelversion "
            "pins %s. Update the Requirements section." % (floor, pinned),
        )


if __name__ == "__main__":
    unittest.main()
