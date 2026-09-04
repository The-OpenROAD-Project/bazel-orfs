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

Source directories (flow/designs/src/**) are the one place the generator
does guess a files() group from contents, and only where neither ORFS nor
the recorded set (orfs_design_builds.bzl) provides a BUILD. So the
invariant there is weaker and stated exactly: every canonical files()
BUILD ORFS ships is either recorded verbatim or reproduced by the rule.
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

# Mirrors the generator in orfs_source.bzl.
#
# Under a platform: config.mk only. A files() group ("verilog", "include",
# "lef", ...) is decided by which label other designs reference, not by
# what the directory holds -- src/cva6 declares files("verilog") while
# holding no .v/.sv, and prim/rtl holds both .sv and .svh but declares
# files("include"). Those BUILDs are recorded, not generated; see
# docs/orfs-design-builds.md.
_RULES = [
    ("design", lambda names: "config.mk" in names),
]

# Under flow/designs/src: a files() group by content, for a directory
# that has no BUILD from any source. Wrong for prim/rtl (.sv + .svh,
# declares "include") and for src/cva6 (no sources, declares "verilog"),
# which is exactly why those two are recorded and this rule never reaches
# them.
_SRC_RULES = [
    ("verilog", lambda names: any(n.endswith((".v", ".sv")) for n in names)),
    ("include", lambda names: any(n.endswith(".svh") for n in names)),
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


def _generated_form(names, rules=_RULES):
    for form, matches in rules:
        if matches(names):
            return form
    return None


def _src_form(names):
    return _generated_form(names, _SRC_RULES)


def _recorded_paths():
    """The repo-relative paths in RECORDED_BUILDS, or an empty set.

    Read as Starlark-that-is-also-Python, the same way
    orfs_recorded_builds_test.py does. The file is a data dep of the
    bazel test; when run by hand from the repo root it is found there.
    """
    path = pathlib.Path(__file__).resolve().parents[1] / "orfs_design_builds.bzl"
    if not path.exists():
        return set()
    ns = {}
    exec(path.read_text(), ns)  # noqa: S102 - our own generated data file
    return set(ns["RECORDED_BUILDS"])


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
                # Either bespoke, or a files() group; those are checked
                # by test_shipped_files_groups_are_recorded_or_reproduced.
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

    def test_shipped_files_groups_are_recorded_or_reproduced(self):
        """Every shipped canonical files() BUILD under src/ is covered.

        Either it is in RECORDED_BUILDS, so it comes back verbatim, or
        the content rule reproduces it. A shipped group that is neither
        would silently change name the day ORFS deletes the file.
        """
        recorded = _recorded_paths()
        src_root = os.path.join(self.root, "src")
        checked = 0
        uncovered = []
        for dirpath, _, filenames in os.walk(src_root):
            if "BUILD" not in filenames:
                continue
            with open(os.path.join(dirpath, "BUILD"), encoding="utf-8") as fp:
                declared = _canonical_form(fp.read())
            if declared in (None, "design"):
                continue
            checked += 1
            rel = os.path.relpath(dirpath, self.root)
            if "flow/designs/%s/BUILD" % rel in recorded:
                continue
            if _src_form(filenames) != declared:
                uncovered.append(
                    "%s: ORFS says %r, rule would say %r, not recorded"
                    % (rel, declared, _src_form(filenames))
                )
        self.assertEqual([], uncovered)
        self.assertGreater(checked, 0, "found no canonical files() BUILDs to check")


class TestRules(unittest.TestCase):
    """The rule table itself, independent of any checkout."""

    def test_config_mk_wins_over_sources(self):
        # A design directory routinely holds both; picking "verilog" here
        # would replace the flow targets with a filegroup.
        self.assertEqual("design", _generated_form(["config.mk", "macros.v", "io.tcl"]))

    def test_file_groups_are_not_guessed_under_a_platform(self):
        """A platform directory without config.mk gets nothing.

        The files() BUILDs under platforms (swerv_wrapper/lef, lib,
        chameleon/gds, ...) are recorded, and their group names are not
        derivable from contents in general. The design rule declines.
        """
        self.assertIsNone(_generated_form(["gcd.v", "top.sv"]))
        self.assertIsNone(_generated_form(["fakeram45_64x32.lef"]))
        self.assertIsNone(_generated_form(["README.md"]))
        self.assertIsNone(_generated_form([]))

    def test_src_groups_are_guessed_from_contents(self):
        """Under src/, contents decide -- where nothing else exists.

        This is the guessing the platform rule refuses, allowed here
        because the rule runs only in a directory with no shipped and no
        recorded BUILD, where the alternative is no package at all.
        """
        self.assertEqual("verilog", _src_form(["CoreMiniAxi.sv"]))
        self.assertEqual("verilog", _src_form(["gcd.v", "README.md"]))
        self.assertEqual("include", _src_form(["defs.svh"]))
        self.assertIsNone(_src_form(["README.md"]))
        self.assertIsNone(_src_form([]))

    def test_src_rule_would_be_wrong_for_the_recorded_exceptions(self):
        """The two shapes that make the rule unsafe in general.

        prim/rtl holds .sv and .svh and declares files("include");
        src/cva6 holds no sources and declares files("verilog"). The rule
        gets both wrong, which is why they are carried in RECORDED_BUILDS
        and the generator never reaches them. Pinned so that nobody
        "fixes" the rule to cover them and loses the recording.
        """
        self.assertEqual("verilog", _src_form(["prim_assert.sv", "x.svh"]))
        self.assertIsNone(_src_form(["README.md"]))

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
    """The design-BUILD generator, read out of orfs_source.bzl.

    Extracted rather than copied: a second copy would drift from the one
    that actually runs, and this generator has already shipped broken
    twice -- once with quote escaping that collapsed inside the Starlark
    string (emitting `load(@orfs_designs//:designs.bzl, design)`), once
    generating packages under platforms ORFS does not expose to bazel.
    Against the pinned ORFS it writes nothing, because every design under
    a bazel platform already has a BUILD, so without this the only thing
    exercising it is a future ORFS that has deleted them.

    It moved here from MODULE.bazel's archive_override when ORFS became
    an extension-created http_archive; the platform list it interpolates
    is held against orfs_designs() by //test:orfs_platforms_test.
    """
    src = pathlib.Path(__file__).resolve().parents[1] / "orfs_source.bzl"
    text = src.read_text()
    open_marker = '_GENERATE_DESIGN_BUILDS = """'
    body_start = text.index(open_marker) + len(open_marker)
    body = text[body_start : text.index('"""', body_start)]
    # The Starlark source is a .format() template: {platforms} is the
    # substitution and {{ }} are escaped shell braces.
    platforms = " ".join(_generator_platforms())
    return body.replace("{platforms}", platforms).replace("{{", "{").replace("}}", "}")


def _generator_platforms():
    """ORFS_BAZEL_PLATFORMS, the list the generator interpolates."""
    src = pathlib.Path(__file__).resolve().parents[1] / "orfs_source.bzl"
    text = src.read_text()
    start = text.index("ORFS_BAZEL_PLATFORMS = [")
    return re.findall(r'"([^"]+)"', text[start : text.index("]", start)])


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

    def _src(self, name, files=(), build=None):
        d = os.path.join(self.tmp, "flow", "designs", "src", name)
        os.makedirs(d, exist_ok=True)
        for f in files:
            open(os.path.join(d, f), "w").close()
        if build is not None:
            with open(os.path.join(d, "BUILD"), "w") as fp:
                fp.write(build)
        return d

    def _run(self):
        subprocess.run(["bash", "-c", self.script], cwd=self.tmp, check=True)

    def _read(self, d):
        with open(os.path.join(d, "BUILD"), encoding="utf-8") as fp:
            return fp.read()

    def test_nested_block_design_is_covered(self):
        # Hierarchical flows nest a block's design directory inside its
        # parent's. ORFS ships three:
        #   asap7/riscv32i-mock-sram/fakeram7_256x32
        #   gf180/uart-blocks/uart_rx
        #   ihp-sg13g2/i2c-gpio-expander/I2cDeviceCtrl
        # A `$platform/*` walk missed all three, and a fixture with only
        # flat designs did not notice. This is that fixture case.
        self._design("asap7", "riscv32i-mock-sram")
        self._design("asap7", "riscv32i-mock-sram/fakeram7_256x32")
        self._run()
        nested = os.path.join(
            self.tmp,
            "flow/designs/asap7/riscv32i-mock-sram/fakeram7_256x32/BUILD",
        )
        self.assertTrue(os.path.exists(nested), "nested design got no BUILD")
        with open(nested, encoding="utf-8") as fp:
            self.assertIn('design(config = "config.mk")', fp.read())

    def test_nested_design_with_its_own_build_is_left_alone(self):
        self._design("asap7", "parent")
        self._design(
            "asap7",
            "parent/block",
            build='# hand written\nload(":x.bzl", "y")\n',
        )
        self._run()
        with open(
            os.path.join(self.tmp, "flow/designs/asap7/parent/block/BUILD"),
            encoding="utf-8",
        ) as fp:
            self.assertIn("hand written", fp.read())

    def test_a_directory_without_config_mk_gets_nothing(self):
        # The recursive walk keys on config.mk, so intermediate
        # directories that merely hold sources must not become packages.
        self._design("asap7", "holder", files=())
        self._run()
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp, "flow/designs/asap7/holder/BUILD")),
        )

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

    def test_src_directory_with_sources_gets_files_verilog(self):
        # The coralnpu shape: ORFS #4474 added src/coralnpu/CoreMiniAxi.sv
        # with no BUILD, and asap7/coralnpu's config.mk references the
        # file by label.
        d = self._src("coralnpu", files=("CoreMiniAxi.sv",))
        self._run()
        content = self._read(d)
        self.assertIn('load("@orfs_designs//:designs.bzl", "files")', content)
        self.assertIn('files("verilog")', content)
        self.assertEqual("verilog", _canonical_form(content))

    def test_src_directory_with_only_headers_gets_files_include(self):
        d = self._src("hdrs", files=("defs.svh",))
        self._run()
        self.assertEqual("include", _canonical_form(self._read(d)))

    def test_src_directory_with_sources_and_headers_gets_verilog(self):
        # The prim/rtl shape. The rule says verilog; ORFS says include.
        # That is why prim/rtl is recorded -- this test pins what the
        # rule does so the recording is known to be load-bearing.
        d = self._src("prim", files=("prim_assert.sv", "prim_assert.svh"))
        self._run()
        self.assertEqual("verilog", _canonical_form(self._read(d)))

    def test_src_directory_without_sources_gets_nothing(self):
        for name, files in (("readme", ("README.md",)), ("empty", ())):
            d = self._src(name, files=files)
            self._run()
            self.assertFalse(
                os.path.exists(os.path.join(d, "BUILD")),
                "generated a BUILD for src/%s" % name,
            )
        # src/ itself holds no sources either.
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp, "flow/designs/src/BUILD")),
        )

    def test_src_directory_with_a_build_is_left_alone(self):
        # The recorded BUILDs are written before the generator runs, so
        # this is how src/cva6 keeps files("verilog") over no sources
        # and prim/rtl keeps files("include") over .sv + .svh.
        recorded = 'load("//flow/designs:design.bzl", "files")\n\nfiles("include")\n'
        d = self._src("prim_rtl", files=("x.sv", "x.svh"), build=recorded)
        self._run()
        self.assertEqual(recorded, self._read(d))

    def test_nested_src_directory_is_covered(self):
        # cva6 and mempool_group nest sources several levels deep, and
        # each level that holds sources is its own package.
        d = self._src("deep/rtl/src", files=("x.sv",))
        self._src("deep", files=("README.md",))
        self._run()
        self.assertEqual("verilog", _canonical_form(self._read(d)))
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp, "flow/designs/src/deep/BUILD")),
        )

    def test_src_generation_is_idempotent(self):
        d = self._src("again", files=("a.v",))
        self._run()
        first = self._read(d)
        self._run()
        self.assertEqual(first, self._read(d))


class TestAutoFloorplanScope(unittest.TestCase):
    """Which design packages get floorplan-derivation targets.

    design() emits <name>_auto_floorplan_data/_pin only for a package
    whose last two path components form a DESIGNS key -- "asap7/gcd".
    ORFS's three nested block designs sit a level deeper
    (asap7/riscv32i-mock-sram/fakeram7_256x32,
    gf180/uart-blocks/uart_rx,
    ihp-sg13g2/i2c-gpio-expander/I2cDeviceCtrl), so their last two
    components are "riscv32i-mock-sram/fakeram7_256x32", which is not a
    key, and they get no targets.

    That is intended rather than accidental: a block's floorplan is
    derived as part of its parent's flow, not on its own. Pinned here so
    the silence is a decision and not a surprise, and so that widening
    the lookup later is a deliberate act.
    """

    NESTED = [
        "flow/designs/asap7/riscv32i-mock-sram/fakeram7_256x32",
        "flow/designs/gf180/uart-blocks/uart_rx",
        "flow/designs/ihp-sg13g2/i2c-gpio-expander/I2cDeviceCtrl",
    ]

    def test_a_nested_package_is_not_a_designs_key(self):
        for pkg in self.NESTED:
            with self.subTest(pkg=pkg):
                parts = pkg.split("/")
                # What design() looks up.
                key = parts[-2] + "/" + parts[-1]
                # A real key is <platform>/<design>; these are not.
                self.assertNotIn(key, ("asap7/gcd", "gf180/uart-blocks"))
                self.assertEqual(len(pkg.split("/")), 5)

    def test_the_parent_is_a_designs_key(self):
        # The parent is where the derivation belongs, and it does get
        # targets.
        for pkg in self.NESTED:
            with self.subTest(pkg=pkg):
                parent = "/".join(pkg.split("/")[:-1])
                parts = parent.split("/")
                self.assertEqual(len(parts), 4)
                self.assertEqual(parts[0] + "/" + parts[1], "flow/designs")


if __name__ == "__main__":
    unittest.main()
