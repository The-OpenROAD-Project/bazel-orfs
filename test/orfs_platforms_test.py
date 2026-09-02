"""ORFS_BAZEL_PLATFORMS and MODULE.bazel's orfs_designs() must agree.

MODULE.bazel cannot load(), so the platform list is spelled out there for
orfs_designs() and again in orfs_source.bzl, where ORFS_BAZEL_PLATFORMS
drives design BUILD generation. The two have to match: a platform in the
generator but not in orfs_designs() invents a BUILD whose design() call
DESIGNS cannot resolve, and a platform in orfs_designs() but not the
generator silently stops generating BUILDs for it after the ORFS cleanup
deletes them.
"""

import re
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent


def _string_list(text, start):
    """The Starlark string list beginning at `start` in `text`."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return re.findall(r'"([^"]+)"', text[start : i + 1])
    raise AssertionError("unterminated list at offset %d" % start)


def _generator_platforms():
    src = (_ROOT / "orfs_source.bzl").read_text()
    m = re.search(r"^ORFS_BAZEL_PLATFORMS\s*=\s*", src, re.M)
    assert m, "ORFS_BAZEL_PLATFORMS not found in orfs_source.bzl"
    return _string_list(src, m.end())


def _orfs_designs_platforms():
    src = (_ROOT / "MODULE.bazel").read_text()
    m = re.search(r"orfs_designs\(", src)
    assert m, "orfs_designs() not found in MODULE.bazel"
    call = src[m.start() : src.index("\n)", m.start())]
    m2 = re.search(r"platforms\s*=\s*", call)
    assert m2, "platforms= not found in orfs_designs()"
    return _string_list(call, m2.end())


class TestOrfsPlatforms(unittest.TestCase):
    def test_lists_agree(self):
        self.assertEqual(_generator_platforms(), _orfs_designs_platforms())

    def test_lists_are_not_empty(self):
        # A regex that silently matched nothing would make the comparison
        # above trivially true.
        self.assertGreater(len(_generator_platforms()), 1)

    def test_asap7_is_present(self):
        # The platform every small CI design uses; its absence would be a
        # parse failure rather than a real config.
        self.assertIn("asap7", _generator_platforms())


if __name__ == "__main__":
    unittest.main()
