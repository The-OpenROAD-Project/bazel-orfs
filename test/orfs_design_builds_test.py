"""Does the generator agree with the BUILD files ORFS still ships?

bazel-orfs generates a BUILD for any flow/designs directory that lacks
one (patch_cmds in MODULE.bazel), which is what lets ORFS stop carrying
~150 near-identical files. The risk is a wrong guess: pick "include"
where ORFS said "verilog" and the target name changes, so every label
referring to it breaks -- and it breaks at the far end, in some other
design's config.

So for every design BUILD ORFS *does* still ship whose body is one of the
canonical forms, assert the generator's rules would choose that same form
from the directory's contents. While ORFS carries the files this compares
generation against the real answer; once ORFS deletes them there is
nothing left to disagree with, and the target-list diff in
docs/orfs-design-builds.md is the check that matters.
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

# Mirrors the patch_cmds rules in MODULE.bazel.
#
# config.mk only. A files() group ("verilog", "include", "lef", ...) is
# decided by which label other designs reference, not by what the
# directory holds -- src/cva6 declares files("verilog") while holding no
# .v/.sv, and prim/rtl holds both .sv and .svh but declares
# files("include"). So those BUILDs stay in ORFS; see
# docs/orfs-design-builds.md.
_RULES = [
    ("design", lambda names: "config.mk" in names),
]

_CANONICAL = re.compile(
    r'^load\(\s*"[^"]*"\s*,\s*"(design|files)"\s*\)\s*'
    r'(?:design\(\s*config\s*=\s*"config\.mk"\s*,?\s*\)'
    r'|files\(\s*"(verilog|lef|lib|gds|include)"\s*\))\s*$'
)


def _strip(text):
    """Drop comments and blank lines, collapse whitespace."""
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return " ".join(" ".join(lines).split())


def _canonical_form(text):
    """The group this BUILD declares, or None if it is bespoke."""
    match = _CANONICAL.match(_strip(text))
    if not match:
        return None
    return "design" if match.group(1) == "design" else match.group(2)


def _generated_form(names):
    for form, matches in _RULES:
        if matches(names):
            return form
    return None


def _designs_root():
    """A flow/designs tree to check against, or None.

    Set ORFS_DESIGNS_DIR to run this against a real checkout:

        ORFS_DESIGNS_DIR=$(bazel info output_base)/external/orfs+/flow/designs \\
          python3 test/orfs_design_builds_test.py

    Deliberately not wired into runfiles: covering it would mean dragging
    all ~173 design BUILD files plus their sources into every test run,
    and the property that actually matters after the ORFS cleanup is the
    target-list diff in docs/orfs-design-builds.md, not this. The rule
    table below is tested unconditionally.
    """
    root = os.environ.get("ORFS_DESIGNS_DIR")
    if root and os.path.isdir(root):
        return root
    return None


class TestGeneratorAgreesWithOrfs(unittest.TestCase):
    def setUp(self):
        self.root = _designs_root()
        if self.root is None:
            self.skipTest("set ORFS_DESIGNS_DIR to check a real tree")

    def test_canonical_builds_would_be_regenerated_identically(self):
        checked = 0
        disagreements = []
        for dirpath, _, filenames in os.walk(self.root):
            if "BUILD" not in filenames:
                continue
            with open(os.path.join(dirpath, "BUILD"), encoding="utf-8") as fp:
                declared = _canonical_form(fp.read())
            if declared != "design":
                # Either bespoke, or a files() group the generator
                # deliberately does not attempt (see the note on _RULES).
                # Nothing to agree about: the generator never touches a
                # directory that already has a BUILD.
                continue
            checked += 1
            generated = _generated_form(filenames)
            if generated != declared:
                disagreements.append(
                    "%s: ORFS says %r, generator would say %r"
                    % (os.path.relpath(dirpath, self.root), declared, generated)
                )
        self.assertEqual([], disagreements)
        self.assertGreater(checked, 0, "found no canonical design BUILDs to check")


class TestRules(unittest.TestCase):
    """The rule table itself, independent of any checkout."""

    def test_config_mk_wins_over_sources(self):
        # A design directory routinely holds both; picking "verilog" here
        # would replace the flow targets with a filegroup.
        self.assertEqual("design", _generated_form(["config.mk", "macros.v", "io.tcl"]))

    def test_file_groups_are_not_guessed(self):
        """The cases that make guessing a files() group unsafe.

        src/cva6 declares files("verilog") holding no .v/.sv at all, and
        prim/rtl holds both .sv and .svh but declares files("include").
        Neither is recoverable from the directory, so the generator must
        decline rather than guess -- these BUILDs stay in ORFS.
        """
        self.assertIsNone(_generated_form(["gcd.v", "top.sv"]))
        self.assertIsNone(_generated_form(["prim_assert.sv", "x.svh"]))
        self.assertIsNone(_generated_form(["fakeram45_64x32.lef"]))
        self.assertIsNone(_generated_form(["README.md"]))
        self.assertIsNone(_generated_form([]))

    def test_canonical_form_ignores_comments_and_spacing(self):
        text = """# a comment

load("//flow/designs:design.bzl", "design")

design(
    config = "config.mk",
)
"""
        self.assertEqual("design", _canonical_form(text))

    def test_bespoke_build_is_not_canonical(self):
        text = 'filegroup(name = "include", srcs = glob(["**/*.v"]))'
        self.assertIsNone(_canonical_form(text))


def _generator_script():
    """The patch_cmds generator, read out of MODULE.bazel.

    Extracted rather than copied: a second copy would drift from the one
    that actually runs, and this generator has already shipped broken
    twice -- once with quote escaping that collapsed inside the Starlark
    string (emitting `load(@orfs_designs//:designs.bzl, design)`), once
    generating packages under platforms ORFS does not expose to bazel.
    Against the pinned ORFS it writes nothing, because every design under
    a bazel platform already has a BUILD, so without this the only thing
    exercising it is a future ORFS that has deleted them.
    """
    module = pathlib.Path(__file__).resolve().parents[1] / "MODULE.bazel"
    text = module.read_text()
    start = text.index('module_name = "orfs"')
    block = text[start : text.index("\n)", start)]
    open_marker = 'patch_cmds = [\n        """'
    body_start = block.index(open_marker) + len(open_marker)
    return block[body_start : block.index('"""', body_start)]


class TestGeneratorScript(unittest.TestCase):
    """Run the real generator against a fixture tree."""

    def setUp(self):
        self.script = _generator_script()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _design(self, platform, name, files=("config.mk",), build=None):
        d = os.path.join(self.tmp, "flow", "designs", platform, name)
        os.makedirs(d, exist_ok=True)
        for f in files:
            open(os.path.join(d, f), "w").close()
        if build is not None:
            with open(os.path.join(d, "BUILD"), "w") as fp:
                fp.write(build)
        return d

    def _run(self):
        subprocess.run(["bash", "-c", self.script], cwd=self.tmp, check=True)

    def test_writes_a_loadable_build_for_a_design_without_one(self):
        d = self._design("asap7", "widget")
        self._run()
        with open(os.path.join(d, "BUILD"), encoding="utf-8") as fp:
            content = fp.read()

        # The bug that shipped: escaping collapsed and the quotes were
        # eaten by the shell, producing load(@orfs_designs//:designs.bzl,
        # design) -- which bazel rejects with "invalid character: '@'".
        self.assertIn('load("@orfs_designs//:designs.bzl", "design")', content)
        self.assertIn('design(config = "config.mk")', content)
        self.assertEqual("design", _canonical_form(content))

    def test_leaves_an_existing_build_alone(self):
        bespoke = 'filegroup(name = "include", srcs = glob(["**/*.sv"]))\n'
        d = self._design("asap7", "bespoke", build=bespoke)
        self._run()
        with open(os.path.join(d, "BUILD"), encoding="utf-8") as fp:
            self.assertEqual(bespoke, fp.read())

    def test_skips_platforms_orfs_does_not_expose_to_bazel(self):
        # gf12 and gt2n ship no BUILD files and are absent from the
        # platforms list ORFS passes to orfs_designs, so a generated
        # design() there could never resolve against DESIGNS.
        for platform in ("gf12", "gt2n"):
            d = self._design(platform, "ariane133")
            self._run()
            self.assertFalse(
                os.path.exists(os.path.join(d, "BUILD")),
                "generated a BUILD under %s" % platform,
            )

    def test_skips_directories_without_a_config_mk(self):
        d = self._design("asap7", "srcish", files=("top.sv", "top.v"))
        self._run()
        self.assertFalse(os.path.exists(os.path.join(d, "BUILD")))

    def test_is_idempotent(self):
        d = self._design("asap7", "widget")
        self._run()
        with open(os.path.join(d, "BUILD"), encoding="utf-8") as fp:
            first = fp.read()
        self._run()
        with open(os.path.join(d, "BUILD"), encoding="utf-8") as fp:
            self.assertEqual(first, fp.read())


if __name__ == "__main__":
    unittest.main()
