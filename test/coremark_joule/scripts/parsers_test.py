#!/usr/bin/env python3
"""Unit tests for the study's parsers.

Every number the study reports passes through one of these, and each one
reads a format some other project is free to change: CoreMark's report
text, and the ELF layout GCC emits. A silent parse failure here would
not look like a failure -- it would look like a measurement.
"""

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cm_per_mhz  # noqa: E402
import elf2hex  # noqa: E402
from check_coremark import check, check_stack, parse  # noqa: E402

# A faithful CoreMark report for the study's configuration: the 2K
# performance profile, the constant timer, and the "at least 10 secs"
# error that the constant timer makes unavoidable. Kept verbatim rather
# than generated, so a change in CoreMark's output shows up here as a
# test failure instead of as a missing measurement.
#
# The stack-used line is the port layer's, not CoreMark's: portable_fini
# reports how much of crt0.S's paint the stack consumed, which is what
# shows the hardened data memory was big enough for the run (§5.1).
GOOD_REPORT = """2K performance run parameters for coremark.
CoreMark Size    : 666
Total ticks      : 1
Total time (secs): 1
Iterations/Sec   : 3
ERROR! Must execute for at least 10 secs for a valid result!
Iterations       : 3
Compiler version : GCC13.2.0
Compiler flags   : -march=rv32im -mabi=ilp32 -O3
Memory location  : STATIC
seedcrc          : 0xe9f5
[0]crclist       : 0xe714
[0]crcmatrix     : 0x1fd7
[0]crcstate      : 0x8e3a
[0]crcfinal      : 0xa14c
stack-used 388 of 4604
Errors detected
"""


class CheckCoremarkTest(unittest.TestCase):
    def test_good_report_passes(self):
        """The known-good CRCs for the 2K performance profile."""
        self.assertEqual([], check(GOOD_REPORT))

    def test_coremark_own_error_does_not_fail_the_run(self):
        """The gate must ignore CoreMark's "10 secs" error.

        The port stubs the timer to a constant so the two iteration
        counts print identical text, which makes this error appear in
        every run. Gating on CoreMark's error count would fail every
        correct measurement the study makes.
        """
        self.assertIn("Must execute for at least 10 secs", GOOD_REPORT)
        self.assertEqual([], check(GOOD_REPORT))

    def test_wrong_crc_fails(self):
        """A core that computes the wrong answer must not pass."""
        bad = GOOD_REPORT.replace("0xe714", "0xdead")
        problems = check(bad)
        self.assertEqual(1, len(problems))
        self.assertIn("crclist", problems[0])
        self.assertIn("0xdead", problems[0])

    def test_each_crc_is_checked(self):
        """All three, not just the first one parsed."""
        for original in ("0xe714", "0x1fd7", "0x8e3a"):
            with self.subTest(crc=original):
                self.assertEqual(1, len(check(GOOD_REPORT.replace(original, "0x0000"))))

    def test_missing_stack_report_fails(self):
        """A run with no stack-used line has not shown its memory sufficed.

        The line is evidence, not decoration: the data memory is
        hardened with the core and sized just above the largest image,
        so a run that does not report its high-water mark has left the
        one question that sizing raises unanswered.
        """
        problems = check(GOOD_REPORT.replace("stack-used 388 of 4604\n", ""))
        self.assertEqual(1, len(problems))
        self.assertIn("no stack-used line", problems[0])

    def test_stack_within_budget_passes(self):
        self.assertEqual([], check_stack("stack-used 388 of 4604\n"))

    def test_stack_over_budget_fails(self):
        """Half the headroom is the limit, not all of it.

        By the time the paint is gone all the way to _end the stack has
        already written past it, so the observable failure would be a
        corrupted .bss rather than a reported overflow.
        """
        problems = check_stack("stack-used 3000 of 4604\n")
        self.assertEqual(1, len(problems))
        self.assertIn("high-water mark", problems[0])

    def test_last_stack_line_wins(self):
        """Only the final report counts, so a re-run in one log is read
        as the run that finished."""
        self.assertEqual(
            [], check_stack("stack-used 4000 of 4604\nstack-used 388 of 4604\n")
        )

    def test_truncated_run_fails(self):
        """A run cut off by the cycle budget never reaches the report."""
        problems = check("2K performance run parameters for coremark.\n")
        self.assertEqual(1, len(problems))
        self.assertIn("no seedcrc", problems[0])

    def test_empty_output_fails(self):
        """A core that never wrote a character must not pass silently."""
        self.assertNotEqual([], check(""))

    def test_unknown_profile_fails(self):
        """A changed TOTAL_DATA_SIZE must not be checked against the wrong CRCs.

        CoreMark's seedcrc identifies the profile, so a data-size change
        that moved the expected CRCs is caught here rather than showing
        up as three CRC mismatches that look like a broken core.
        """
        other = GOOD_REPORT.replace("0xe9f5", "0x8a02")
        problems = check(other)
        self.assertEqual(1, len(problems))
        self.assertIn("not a profile this study knows", problems[0])

    def test_parse_ignores_unrelated_lines(self):
        seedcrc, fields = parse(GOOD_REPORT)
        self.assertEqual("0xe9f5", seedcrc)
        self.assertEqual("0xe714", fields["crclist"])
        self.assertNotIn("Size", fields)


class CmPerMhzTest(unittest.TestCase):
    def test_cycles_file_carries_more_than_the_count(self):
        """The harness also records where CoreMark first printed.

        That line places the SAIF window. Reading the file as a single
        integer worked until it was added, so the format is pinned here.
        """
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c")
            with open(p, "w") as f:
                f.write("3723728\nfirst_output 3693242\n")
            self.assertEqual(3723728, cm_per_mhz.read_count(p))

    def test_build_flags_come_from_the_report(self):
        """A number must be traceable to the binary that produced it.

        CoreMark echoes COMPILER_VERSION and COMPILER_FLAGS, so the
        result carries them rather than relying on whichever BUILD file
        happened to be checked out when someone reads the JSON.
        """
        report = "CoreMark 1.0 : 0 / GCC13.2.0 -march=rv32im -O3\n"
        self.assertEqual("GCC13.2.0 -march=rv32im -O3", cm_per_mhz.build_flags(report))

    def test_build_flags_absent_is_not_an_error(self):
        self.assertIsNone(cm_per_mhz.build_flags(GOOD_REPORT))

    def test_coremark_per_mhz_arithmetic(self):
        """1e6 / cycles-per-iteration, with cycles-per-iteration a delta."""
        with tempfile.TemporaryDirectory() as d:
            c2 = os.path.join(d, "2")
            c3 = os.path.join(d, "3")
            report = os.path.join(d, "r")
            out = os.path.join(d, "o.json")
            # 1e6 / 1000000 == 1.0 exactly, so a wrong operand order or a
            # swapped numerator shows up as something other than 1.0.
            open(c2, "w").write("500000\n")
            open(c3, "w").write("1500000\n")
            open(report, "w").write(GOOD_REPORT)

            rc = cm_per_mhz.main(
                [
                    "cm_per_mhz",
                    "--cycles-2",
                    c2,
                    "--cycles-3",
                    c3,
                    "--report",
                    report,
                    "--out",
                    out,
                ]
            )
            self.assertEqual(0, rc)

            import json

            result = json.load(open(out))
            self.assertEqual(1000000, result["cycles_per_iteration"])
            self.assertAlmostEqual(1.0, result["coremark_per_mhz"])

    def test_non_positive_delta_is_rejected(self):
        """Equal counts mean the two runs were not what they claim to be.

        The same image run twice, or an extra iteration that did no work,
        would otherwise divide by zero or produce a negative rate that
        looks like a very fast core.
        """
        with tempfile.TemporaryDirectory() as d:
            c2 = os.path.join(d, "2")
            c3 = os.path.join(d, "3")
            report = os.path.join(d, "r")
            open(c2, "w").write("1000\n")
            open(c3, "w").write("1000\n")
            open(report, "w").write(GOOD_REPORT)

            rc = cm_per_mhz.main(
                [
                    "cm_per_mhz",
                    "--cycles-2",
                    c2,
                    "--cycles-3",
                    c3,
                    "--report",
                    report,
                    "--out",
                    os.path.join(d, "o.json"),
                ]
            )
            self.assertEqual(1, rc)


def _elf32(segments):
    """Build a minimal little-endian ELF32 with the given PT_LOAD segments.

    Synthesised rather than checked in: a committed binary fixture cannot
    be read in a review, and the point of these tests is the placement
    arithmetic, not GCC's output.
    """
    ehsize = 0x34
    phentsize = 0x20
    phoff = ehsize
    body_off = phoff + phentsize * len(segments)

    headers = b""
    body = b""
    for vaddr, data, memsz in segments:
        offset = body_off + len(body)
        headers += struct.pack(
            "<IIIIIIII",
            1,  # p_type = PT_LOAD
            offset,
            vaddr,
            vaddr,  # p_paddr
            len(data),  # p_filesz
            memsz,  # p_memsz
            6,  # p_flags
            4,  # p_align
        )
        body += data

    header = bytearray(ehsize)
    header[0:4] = b"\x7fELF"
    header[4] = 1  # ELFCLASS32
    header[5] = 1  # ELFDATA2LSB
    struct.pack_into("<I", header, 0x1C, phoff)
    struct.pack_into("<HH", header, 0x2A, phentsize, len(segments))
    return bytes(header) + headers + body


class Elf2HexTest(unittest.TestCase):
    def test_segments_land_at_their_addresses(self):
        blob = _elf32(
            [
                (0, b"\x01\x02\x03\x04", 4),
                (16, b"\xaa\xbb\xcc\xdd", 4),
            ]
        )
        image, written = elf2hex.to_words(elf2hex.load_segments(blob), words=8)
        self.assertEqual(8, written)
        self.assertEqual(b"\x01\x02\x03\x04", bytes(image[0:4]))
        self.assertEqual(b"\xaa\xbb\xcc\xdd", bytes(image[16:20]))
        # The gap between them must be zero, not left uninitialised: an X
        # in RAM propagates through a gate-level netlist long before the
        # first instruction runs.
        self.assertEqual(b"\x00" * 12, bytes(image[4:16]))

    def test_bss_is_zero_filled(self):
        """p_memsz beyond p_filesz is .bss and must reach the image as zeros."""
        blob = _elf32([(0, b"\xff\xff\xff\xff", 12)])
        image, _ = elf2hex.to_words(elf2hex.load_segments(blob), words=4)
        self.assertEqual(b"\xff\xff\xff\xff", bytes(image[0:4]))
        self.assertEqual(b"\x00" * 8, bytes(image[4:12]))

    def test_program_too_large_is_an_error(self):
        """Truncating would surface much later as a CRC mismatch."""
        blob = _elf32([(0, b"\x00" * 64, 64)])
        with self.assertRaises(elf2hex.ElfError) as caught:
            elf2hex.to_words(elf2hex.load_segments(blob), words=4)
        self.assertIn("runs past", str(caught.exception))

    def test_non_elf_is_rejected(self):
        with self.assertRaises(elf2hex.ElfError):
            elf2hex.load_segments(b"not an elf at all")

    def test_no_loadable_segments_is_rejected(self):
        with self.assertRaises(elf2hex.ElfError):
            elf2hex.load_segments(_elf32([]))


if __name__ == "__main__":
    unittest.main()
