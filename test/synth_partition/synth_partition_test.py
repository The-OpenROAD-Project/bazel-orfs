#!/usr/bin/env python3
"""Tests for synth_partition.sh's kept_modules.json parser.

The earlier sed-based parser ``s/.*\\[//;s/\\].*//`` was greedy and
collapsed any module name that contained '[' or ']' (slang elaborates
parameterised instances to names like
``tcdm_adapter$mempool_group.gen_tiles[0].i_tile.gen_banks[3]``) into
the literal "0". The fix switched to ``grep -oE '"[^"]+"' | tail -n +2``.

This test pins down the parsing surface: feed a JSON fixture, run the
parser snippet from synth_partition.sh on it, assert the output module
list. Independent of yosys.
"""

import os
import subprocess
import tempfile
import unittest

# The exact parser line in synth_partition.sh, isolated. If
# synth_partition.sh's parsing logic changes, update this string so the
# test exercises the real script's regex.
PARSER_CMD = 'grep -oE \'"[^"]+"\' "$KEPT_JSON" | tail -n +2 | sed \'s/"//g\''


def _run_parser(json_text):
    """Run the parser snippet against a temp JSON file. Returns the list
    of module names (one per line, in input order)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(json_text)
        path = f.name
    try:
        result = subprocess.run(
            ["bash", "-c", PARSER_CMD],
            env={**os.environ, "KEPT_JSON": path},
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        os.unlink(path)
    return [line for line in result.stdout.splitlines() if line]


class TestKeptModulesParser(unittest.TestCase):
    def test_plain_module_names(self):
        modules = _run_parser('{"modules": ["foo", "bar", "baz"]}')
        self.assertEqual(modules, ["foo", "bar", "baz"])

    def test_slang_bracket_indices_not_collapsed(self):
        # Regression: greedy 's/.*\\[//;s/\\].*//' collapsed this name
        # to "0". The new parser must preserve the full string.
        elaborated = "tcdm_adapter$mempool_group.gen_tiles[0].i_tile.gen_banks[3]"
        modules = _run_parser('{"modules": ["' + elaborated + '", "second"]}')
        self.assertEqual(modules, [elaborated, "second"])

    def test_multiple_bracket_indices_preserved(self):
        # Names with several [N] segments must round-trip intact.
        names = [
            "core.tile[0]",
            "core.tile[12].bank[7].adapter",
        ]
        modules = _run_parser('{"modules": ["' + names[0] + '", "' + names[1] + '"]}')
        self.assertEqual(modules, names)

    def test_empty_module_list(self):
        modules = _run_parser('{"modules": []}')
        self.assertEqual(modules, [])

    def test_pretty_printed_json(self):
        # The parser must work on indented JSON too (json.dump default).
        text = (
            "{\n" '  "modules": [\n' '    "foo",\n' '    "bar.baz[0]"\n' "  ]\n" "}\n"
        )
        modules = _run_parser(text)
        self.assertEqual(modules, ["foo", "bar.baz[0]"])

    def test_skips_modules_key_itself(self):
        # The first quoted string in the JSON is the "modules" key — the
        # `tail -n +2` step drops it. If the script ever moves to a JSON
        # shape with a different first key, this test will catch it.
        modules = _run_parser('{"modules": ["only"]}')
        self.assertNotIn("modules", modules)
        self.assertEqual(modules, ["only"])


def _log_name(partition_id, module):
    """log_name() from synth_partition.sh itself, run on its own."""
    script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "synth_partition.sh"
    )
    if not os.path.exists(script):
        script = os.environ["SYNTH_PARTITION_SH"]
    text = open(script).read()
    start = text.index("log_name() {")
    end = text.index("\n}\n", start) + 3
    result = subprocess.run(
        ["bash", "-c", text[start:end] + 'log_name "$1"', "_", module],
        env={**os.environ, "PARTITION_ID": partition_id},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


class TestLogName(unittest.TestCase):
    def test_a_short_name_is_kept_whole(self):
        self.assertEqual(_log_name("3", "alu"), "1_2_yosys_partition_3_alu.log")

    def test_a_pinned_long_module_fits_the_file_system(self):
        # bp_be_top's calculator, partition named after it and the module
        # appended again: 300+ characters, over the 255-byte limit
        m = "bp_be_calculator_top_vaddr_width_p56_paddr_width_p22_asid_width_p10_branch_metadata_fwd_width_p36_core_els_p1_num_lce_p2_lce_sets_p64_cce_block_size_in_bytes_p64"
        n = _log_name(m, m[:80])
        self.assertLessEqual(len(n.encode()), 255)
        self.assertTrue(n.startswith("1_2_yosys_partition_bp_be_calculator_top"))
        self.assertTrue(n.endswith(".log"))

    def test_two_long_names_with_one_prefix_stay_apart(self):
        a = "x" * 190 + "a"
        b = "x" * 190 + "b"
        self.assertNotEqual(_log_name(a, "m"), _log_name(b, "m"))


if __name__ == "__main__":
    unittest.main()
