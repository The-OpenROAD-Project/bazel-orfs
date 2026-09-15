#!/usr/bin/env python3
"""The premise of the whole measurement, as a test.

CoreMark's cost per iteration is taken as the difference in cycles
between a three-iteration run and a two-iteration run. That subtraction
is only exactly one iteration if the two binaries are otherwise the same
program: same code, same constants, same amount of printing. CoreMark
makes that possible by taking the iteration count from a volatile global
(seed4_volatile), so the count cannot be folded into generated code --
but only if the port keeps it volatile and keeps the timer constant,
which is a property of files in this repository and can therefore rot.

So it is asserted rather than assumed: .text and .rodata byte-identical,
and .data differing in exactly the four bytes that hold the count.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elf_sections import read_sections  # noqa: E402


def _runfile(name):
    return os.path.join(os.environ["TEST_SRCDIR"], os.environ["TEST_WORKSPACE"], name)


# One 32-bit and one 64-bit build. The property is about CoreMark's
# sources rather than about a word size, but the 64-bit compiler makes
# different constant-folding decisions, so it is worth checking both.
_ISAS = ("rv32i", "rv64gc")


class IterationDeltaTest(unittest.TestCase):
    def setUp(self):
        base = "test/coremark_joule/sw"
        self.builds = {
            isa: (
                read_sections(_runfile("{}/coremark_{}_2.elf".format(base, isa))),
                read_sections(_runfile("{}/coremark_{}_3.elf".format(base, isa))),
            )
            for isa in _ISAS
        }

    def test_code_is_identical(self):
        """Generated code must not depend on the iteration count.

        If this fails, the count has been constant-folded somewhere --
        seed4_volatile lost its volatile, or something started reading
        ITERATIONS directly -- and the cycle difference is no longer one
        iteration of work.
        """
        for isa, (two, three) in self.builds.items():
            for section in (".text", ".rodata"):
                with self.subTest(isa=isa, section=section):
                    self.assertEqual(
                        two[section],
                        three[section],
                        "{} differs between the 2- and 3-iteration {} ELFs".format(
                            section, isa
                        ),
                    )

    def test_data_differs_in_exactly_one_word(self):
        """Exactly the iteration count, and nothing else, may differ."""
        for isa, (two, three) in self.builds.items():
            with self.subTest(isa=isa):
                a = two[".data"]
                b = three[".data"]
                self.assertEqual(len(a), len(b), ".data changed size")

                differing = [i for i in range(len(a)) if a[i] != b[i]]
                self.assertEqual(
                    1,
                    len(differing),
                    ".data differs at {} byte(s); expected exactly the low "
                    "byte of seed4_volatile".format(len(differing)),
                )

                offset = differing[0]
                lo = offset & ~3
                word_a = int.from_bytes(a[lo : lo + 4], "little")
                word_b = int.from_bytes(b[lo : lo + 4], "little")
                self.assertEqual((2, 3), (word_a, word_b))

    def test_bss_is_not_in_the_image(self):
        """.bss is NOBITS, so crt0 zeroing it is what the program sees."""
        for isa, (two, _) in self.builds.items():
            with self.subTest(isa=isa):
                self.assertEqual(b"", two[".bss"])


if __name__ == "__main__":
    unittest.main()
