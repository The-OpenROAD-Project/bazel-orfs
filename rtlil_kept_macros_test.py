#!/usr/bin/env python3
"""Unit tests for rtlil_kept_macros.py."""

import os
import tempfile
import unittest

from rtlil_kept_macros import (
    _base,
    build_base_to_full,
    collect_macros_under,
    derive_kept_macros,
    format_dict,
    parse_rtlil,
)


def _write(rtlil_text):
    """Materialise RTLIL text into a temp file. Returns path; caller unlinks."""
    f = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".rtlil",
        delete=False,
    )
    f.write(rtlil_text)
    f.close()
    return f.name


SIMPLE_RTLIL = """\
attribute \\blackbox 1
module \\sram
end
module \\helper
  cell \\sram \\u_sram
  end
end
attribute \\top 1
module \\top
  cell \\helper \\u_helper
  end
  cell \\sram \\u_top_sram
  end
end
"""


KEPT_HIERARCHY_RTLIL = """\
attribute \\blackbox 1
module \\sram_a
end
attribute \\blackbox 1
module \\sram_b
end
module \\inner_kept
  cell \\sram_b \\u_b
  end
end
module \\helper
  cell \\inner_kept \\u_inner
  end
  cell \\sram_a \\u_a
  end
end
attribute \\top 1
module \\top
  cell \\helper \\u_helper
  end
end
"""


# Slang elaborates a parameterised module instance to "Base$Path.with.dots".
SLANG_SUFFIX_RTLIL = """\
attribute \\blackbox 1
module \\sram
end
module \\worker$inst.path
  cell \\sram \\u_sram
  end
end
attribute \\top 1
module \\top
  cell \\worker$inst.path \\u_worker
  end
end
"""


class TestBase(unittest.TestCase):
    def test_strips_slang_suffix(self):
        self.assertEqual(_base("worker$inst.path"), "worker")

    def test_no_suffix_is_identity(self):
        self.assertEqual(_base("worker"), "worker")


class TestParseRtlil(unittest.TestCase):
    def test_detects_top_attribute(self):
        path = _write(SIMPLE_RTLIL)
        try:
            modules, top = parse_rtlil(path)
        finally:
            os.unlink(path)
        self.assertEqual(top, "top")
        self.assertIn("top", modules)
        self.assertIn("helper", modules)
        self.assertIn("sram", modules)

    def test_collects_cell_instances(self):
        path = _write(SIMPLE_RTLIL)
        try:
            modules, _ = parse_rtlil(path)
        finally:
            os.unlink(path)
        # top has helper and sram cells.
        top_cells = sorted(t for t, _ in modules["top"])
        self.assertEqual(top_cells, ["helper", "sram"])
        # sram is a blackbox — empty body.
        self.assertEqual(modules["sram"], [])

    def test_skips_yosys_builtin_cells(self):
        """Yosys built-in cells like $logic_not aren't real submodules."""
        rtlil = (
            "attribute \\top 1\n"
            "module \\top\n"
            "  cell $logic_not $auto$001\n"
            "  end\n"
            "end\n"
        )
        path = _write(rtlil)
        try:
            modules, _ = parse_rtlil(path)
        finally:
            os.unlink(path)
        # The $-prefixed cell type doesn't match the `\\…` regex, so it
        # never enters the cell list.
        self.assertEqual(modules["top"], [])

    def test_no_top_attribute_returns_none(self):
        rtlil = "module \\m\nend\n"
        path = _write(rtlil)
        try:
            _, top = parse_rtlil(path)
        finally:
            os.unlink(path)
        self.assertIsNone(top)


class TestBuildBaseToFull(unittest.TestCase):
    def test_groups_slang_variants(self):
        modules = {
            "worker$a": [],
            "worker$b": [],
            "top": [],
        }
        result = build_base_to_full(modules)
        self.assertEqual(sorted(result["worker"]), ["worker$a", "worker$b"])
        self.assertEqual(result["top"], ["top"])


class TestCollectMacrosUnder(unittest.TestCase):
    def test_finds_macros_in_descendants(self):
        path = _write(SIMPLE_RTLIL)
        try:
            modules, _ = parse_rtlil(path)
        finally:
            os.unlink(path)
        by_base = build_base_to_full(modules)
        found = collect_macros_under(
            "top",
            modules,
            by_base,
            kept_bases=set(),
            macro_bases={"sram"},
        )
        self.assertEqual(found, {"sram"})

    def test_stops_at_kept_descendants(self):
        # top -> helper -> {inner_kept -> sram_b, sram_a}. With inner_kept
        # marked kept, sram_b belongs to that partition, not top's.
        path = _write(KEPT_HIERARCHY_RTLIL)
        try:
            modules, _ = parse_rtlil(path)
        finally:
            os.unlink(path)
        by_base = build_base_to_full(modules)
        top_found = collect_macros_under(
            "top",
            modules,
            by_base,
            kept_bases={"inner_kept"},
            macro_bases={"sram_a", "sram_b"},
        )
        self.assertEqual(top_found, {"sram_a"})
        inner_found = collect_macros_under(
            "inner_kept",
            modules,
            by_base,
            kept_bases={"inner_kept"},
            macro_bases={"sram_a", "sram_b"},
        )
        self.assertEqual(inner_found, {"sram_b"})

    def test_descends_through_slang_suffixed_cells(self):
        path = _write(SLANG_SUFFIX_RTLIL)
        try:
            modules, _ = parse_rtlil(path)
        finally:
            os.unlink(path)
        by_base = build_base_to_full(modules)
        found = collect_macros_under(
            "top",
            modules,
            by_base,
            kept_bases=set(),
            macro_bases={"sram"},
        )
        # The walk must follow worker$inst.path even though kept_macros
        # references the base name "worker".
        self.assertEqual(found, {"sram"})


class TestDeriveKeptMacros(unittest.TestCase):
    def test_top_residue_under_top_key(self):
        # With no kept modules, every macro is in the top residue.
        path = _write(SIMPLE_RTLIL)
        try:
            modules, top = parse_rtlil(path)
        finally:
            os.unlink(path)
        derived = derive_kept_macros(
            modules,
            top,
            kept_modules=[],
            macros=["sram"],
        )
        self.assertEqual(derived, {"_top": ["sram"]})

    def test_kept_partition_subtracted_from_top(self):
        path = _write(KEPT_HIERARCHY_RTLIL)
        try:
            modules, top = parse_rtlil(path)
        finally:
            os.unlink(path)
        derived = derive_kept_macros(
            modules,
            top,
            kept_modules=["inner_kept"],
            macros=["sram_a", "sram_b"],
        )
        self.assertEqual(
            derived,
            {"inner_kept": ["sram_b"], "_top": ["sram_a"]},
        )

    def test_no_entry_for_kept_module_without_macros(self):
        # A kept module that instantiates no macros gets no entry.
        rtlil = (
            "attribute \\blackbox 1\nmodule \\sram\nend\n"
            "module \\empty_kept\nend\n"
            "attribute \\top 1\nmodule \\top\n"
            "  cell \\empty_kept \\u_e\n  end\n"
            "  cell \\sram \\u_s\n  end\n"
            "end\n"
        )
        path = _write(rtlil)
        try:
            modules, top = parse_rtlil(path)
        finally:
            os.unlink(path)
        derived = derive_kept_macros(
            modules,
            top,
            kept_modules=["empty_kept"],
            macros=["sram"],
        )
        self.assertNotIn("empty_kept", derived)
        self.assertEqual(derived["_top"], ["sram"])


class TestFormatDict(unittest.TestCase):
    def test_empty_dict(self):
        self.assertEqual(format_dict({}), "kept_macros = {}")

    def test_sorted_keys_and_values(self):
        text = format_dict({"b": ["y", "x"], "a": ["m"]})
        # The function preserves the input order of macros within each
        # value (sorting happens upstream in derive_kept_macros), but
        # keys must be sorted for paste-ready stability.
        self.assertTrue(text.startswith("kept_macros = {"))
        self.assertIn('"a":', text)
        self.assertIn('"b":', text)
        self.assertLess(text.index('"a":'), text.index('"b":'))


if __name__ == "__main__":
    unittest.main()
