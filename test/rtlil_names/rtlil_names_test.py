"""The RTLIL name-mangling rules synth_partition.sh's top partition
resolves SYNTH_KEEP_MODULES by (rtlil_names.py).

This is pure string logic with no synthesis in it, and it was wrong in a
way that only appeared on designs which parameterize their submodules:
the first version matched `^module \\` alone, found none of the
parameterized spellings, and SYNTH_KEEP_MODULES then rejected names that
were present in the design under a mangled form. Its shell successor was
right and quadratic: a whole core's checkpoint took hours.

cases.tsv carries the spellings as data rather than as literals, because
escaping backslash-and-dollar names through layers of quoting is how a
test ends up asserting something other than what it reads.

  rtlil_names_test.py <cases.tsv>
"""

import io
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

import rtlil_names

CASES = sys.argv[1]
sys.argv[1:] = []

# One spelling per module, as a real checkpoint has. Reusing the
# demangling table here would put two spellings of serv_alu in one
# design, and "which one wins" would be the assertion rather than "does
# it resolve at all".
MODULES = [
    "\\cmj_imem",
    "$paramod\\serv_alu\\W=1",
    "$paramod$6d68\\serv_rf_ram",
    "\\ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp",
]


class BaseNameTest(unittest.TestCase):
    def test_cases(self):
        with open(CASES) as f:
            rows = [line.rstrip("\n").split("\t") for line in f if line.strip()]
        self.assertTrue(rows)
        for name, want in rows:
            self.assertEqual(rtlil_names.base_name(name), want, name)


class ResolveTest(unittest.TestCase):
    def test_every_spelling_resolves(self):
        got = rtlil_names.resolve(
            [
                "serv_alu",
                "serv_rf_ram",
                "cmj_imem",
                "ifu_bp_ctl",
                "definitely_not_here",
            ],
            MODULES,
        )
        self.assertEqual(got["serv_alu"], "$paramod\\serv_alu\\W=1")
        self.assertEqual(got["serv_rf_ram"], "$paramod$6d68\\serv_rf_ram")
        self.assertEqual(got["cmj_imem"], "\\cmj_imem")
        # present only as a uniquified instance: resolves to it
        self.assertEqual(got["ifu_bp_ctl"], "\\ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp")
        # absent: nothing, so the caller reports it rather than
        # blackboxing a module that does not exist
        self.assertIsNone(got["definitely_not_here"])

    def test_exact_before_uniquified_wherever_it_sits(self):
        modules = ["\\Foo$Top.a", "\\Foo$Top.b", "\\Foo"]
        self.assertEqual(rtlil_names.resolve(["Foo"], modules)["Foo"], "\\Foo")
        self.assertEqual(
            rtlil_names.resolve(["Foo"], modules[:2])["Foo"], "\\Foo$Top.a"
        )

    def test_a_name_with_a_dollar_finds_its_instances(self):
        modules = ["\\Foo$Bar$Top.a"]
        got = rtlil_names.resolve(["Foo", "Foo$Bar", "Fo"], modules)
        self.assertEqual(got["Foo"], "\\Foo$Bar$Top.a")
        self.assertEqual(got["Foo$Bar"], "\\Foo$Bar$Top.a")
        self.assertIsNone(got["Fo"])

    def test_checkpoint_modules(self):
        text = [
            "attribute \\top 1\n",
            "module \\top\n",
            "  wire \\a\n",
            "end\n",
            "module $paramod\\x\\W=1\n",
        ]
        self.assertEqual(
            rtlil_names.checkpoint_modules(text), ["\\top", "$paramod\\x\\W=1"]
        )

    def test_a_whole_core_in_seconds(self):
        """300,000 uniquified modules and 300 names: what a slang-elaborated
        core's checkpoint looks like to the top partition."""
        modules = ["\\Mod%d$XSTile.core.a%d" % (i % 3000, i) for i in range(300000)]
        names = ["Mod%d" % i for i in range(300)]
        start = time.monotonic()
        got = rtlil_names.resolve(names, modules)
        self.assertLess(time.monotonic() - start, 10.0)
        self.assertEqual(got["Mod7"], "\\Mod7$XSTile.core.a7")


class MainTest(unittest.TestCase):
    def checkpoint(self, d):
        path = os.path.join(d, "c.rtlil")
        with open(path, "w") as f:
            f.write("".join("module %s\nend\n" % m for m in MODULES))
        return path

    def test_prints_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with redirect_stdout(out):
                rtlil_names.main(
                    ["rtlil_names.py", self.checkpoint(d), "cmj_imem", "serv_alu"]
                )
            self.assertEqual(
                out.getvalue().splitlines(), ["\\cmj_imem", "$paramod\\serv_alu\\W=1"]
            )

    def test_missing_stops_naming_it(self):
        with tempfile.TemporaryDirectory() as d:
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(SystemExit) as stop:
                rtlil_names.main(
                    ["rtlil_names.py", self.checkpoint(d), "serv_alu", "nope"]
                )
            self.assertEqual(stop.exception.code, 1)
            self.assertIn("'nope'", err.getvalue())
            self.assertIn("serv_alu", err.getvalue())


if __name__ == "__main__":
    unittest.main()
