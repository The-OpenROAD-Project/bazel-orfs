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


if __name__ == "__main__":
    unittest.main()
