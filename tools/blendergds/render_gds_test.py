#!/usr/bin/env python3
"""Tests for render_gds.py helper functions.

The bpy-touching code path (``main``) needs real Blender; these tests
cover only the pure-Python helpers — argument splitting, argparse,
python-tag detection, and wheel staging. Wheel staging is exercised
against a small in-test wheel fixture so we don't need any real wheels.
"""

import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import render_gds  # noqa: E402


def _make_wheel(dest_dir, name, payload_files):
    """Write a one-file wheel into dest_dir and return its path."""
    whl_path = Path(dest_dir) / name
    with zipfile.ZipFile(whl_path, "w") as zf:
        for relpath, contents in payload_files.items():
            zf.writestr(relpath, contents)
    return whl_path


class TestSplitArgv(unittest.TestCase):
    def test_returns_args_after_double_dash(self):
        orig = sys.argv
        try:
            sys.argv = ["blender", "--background", "--", "--gds", "x.gds"]
            self.assertEqual(
                render_gds._split_argv(),
                ["--gds", "x.gds"],
            )
        finally:
            sys.argv = orig

    def test_empty_when_no_double_dash(self):
        orig = sys.argv
        try:
            sys.argv = ["blender", "--background"]
            self.assertEqual(render_gds._split_argv(), [])
        finally:
            sys.argv = orig

    def test_empty_after_trailing_double_dash(self):
        orig = sys.argv
        try:
            sys.argv = ["blender", "--background", "--"]
            self.assertEqual(render_gds._split_argv(), [])
        finally:
            sys.argv = orig


class TestParseArgs(unittest.TestCase):
    def _with_argv(self, after_dashes):
        orig = sys.argv
        sys.argv = ["blender", "--"] + after_dashes
        try:
            return render_gds._parse_args()
        finally:
            sys.argv = orig

    def test_blend_only(self):
        args = self._with_argv(
            [
                "--gds",
                "a.gds",
                "--addon-root",
                "/r",
                "--pdk",
                "SKY130",
                "--out",
                "/tmp/out.blend",
            ],
        )
        self.assertEqual(args.gds, "a.gds")
        self.assertEqual(args.pdk, "SKY130")
        self.assertEqual(args.out, "/tmp/out.blend")
        self.assertIsNone(args.out_html)
        self.assertEqual(args.title, "ORFS layout")

    def test_html_requires_template_and_js(self):
        # --out-html alone must error out — exits with code 2.
        with self.assertRaises(SystemExit) as ctx:
            self._with_argv(
                [
                    "--gds",
                    "a.gds",
                    "--addon-root",
                    "/r",
                    "--pdk",
                    "SKY130",
                    "--out-html",
                    "/tmp/out.html",
                ],
            )
        self.assertEqual(ctx.exception.code, 2)

    def test_must_request_at_least_one_output(self):
        # No --out and no --out-html: argparse errors out.
        with self.assertRaises(SystemExit) as ctx:
            self._with_argv(
                ["--gds", "a.gds", "--addon-root", "/r", "--pdk", "SKY130"],
            )
        self.assertEqual(ctx.exception.code, 2)

    def test_html_with_template_and_js_ok(self):
        args = self._with_argv(
            [
                "--gds",
                "a.gds",
                "--addon-root",
                "/r",
                "--pdk",
                "GF180MCU",
                "--out-html",
                "/tmp/o.html",
                "--html-template",
                "/t.html",
                "--model-viewer-js",
                "/mv.js",
                "--title",
                "My Chip",
            ],
        )
        self.assertEqual(args.out_html, "/tmp/o.html")
        self.assertEqual(args.title, "My Chip")


class TestPythonTag(unittest.TestCase):
    def test_matches_running_python(self):
        expected = f"cp{sys.version_info.major}{sys.version_info.minor}"
        self.assertEqual(render_gds._python_tag(), expected)


class TestStageWheels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wheels_dir = Path(self.tmp) / "wheels"
        self.wheels_dir.mkdir()
        self.dest = Path(self.tmp) / "site"
        self.dest.mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_extracts_pure_python_wheel(self):
        # py3-none-any wheels always match regardless of cpython version.
        _make_wheel(
            self.wheels_dir,
            "purepkg-1.0-py3-none-any.whl",
            {"purepkg/__init__.py": "VALUE = 1\n"},
        )
        render_gds._stage_wheels(self.wheels_dir, self.dest)
        self.assertTrue((self.dest / "purepkg" / "__init__.py").is_file())

    def test_extracts_wheel_matching_current_cpython(self):
        cp_tag = render_gds._python_tag()
        _make_wheel(
            self.wheels_dir,
            f"binpkg-2.0-{cp_tag}-{cp_tag}-linux_x86_64.whl",
            {"binpkg/__init__.py": "VALUE = 2\n"},
        )
        render_gds._stage_wheels(self.wheels_dir, self.dest)
        self.assertTrue((self.dest / "binpkg" / "__init__.py").is_file())

    def test_skips_wheel_for_other_cpython(self):
        # cp00 is guaranteed not to match any real Python.
        _make_wheel(
            self.wheels_dir,
            "wrongabi-3.0-cp00-cp00-linux_x86_64.whl",
            {"wrongabi/__init__.py": "VALUE = 3\n"},
        )
        # Also need at least one matching wheel so _stage_wheels doesn't
        # sys.exit on an empty extraction.
        _make_wheel(
            self.wheels_dir,
            "filler-1.0-py3-none-any.whl",
            {"filler/__init__.py": "\n"},
        )
        render_gds._stage_wheels(self.wheels_dir, self.dest)
        self.assertFalse((self.dest / "wrongabi").exists())
        self.assertTrue((self.dest / "filler").exists())

    def test_empty_extraction_exits(self):
        # No wheels match the running interpreter — _stage_wheels must
        # sys.exit rather than silently produce an unusable site dir.
        _make_wheel(
            self.wheels_dir,
            "wrongabi-3.0-cp00-cp00-linux_x86_64.whl",
            {"wrongabi/__init__.py": "\n"},
        )
        with self.assertRaises(SystemExit) as ctx:
            render_gds._stage_wheels(self.wheels_dir, self.dest)
        self.assertIn("no wheels matched", str(ctx.exception))


class TestWriteHtml(unittest.TestCase):
    def test_substitutes_template_placeholders(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            template = tmp / "t.html"
            template.write_text(
                "<title>{{TITLE}}</title>\n"
                "<script>{{MODEL_VIEWER_JS}}</script>\n"
                "<data>{{GLB_B64}}</data>\n",
            )
            mv = tmp / "mv.js"
            mv.write_text("// model-viewer\n")
            out = tmp / "out.html"
            render_gds._write_html(
                template_path=template,
                model_viewer_js_path=mv,
                glb_bytes=b"GLBDATA",
                title="A Chip",
                out_path=out,
            )
            html = out.read_text()
            self.assertIn("<title>A Chip</title>", html)
            self.assertIn("// model-viewer", html)
            # base64 of b"GLBDATA" is "R0xCREFUQQ=="
            self.assertIn("R0xCREFUQQ==", html)
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
