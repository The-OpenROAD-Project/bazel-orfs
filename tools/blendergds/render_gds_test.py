#!/usr/bin/env python3
"""Tests for render_gds.py helper functions.

The bpy-touching code path (``main``) needs real Blender; these tests
cover only the pure-Python helpers — argument splitting, argparse,
python-tag detection, wheel staging, phase logging, and layerstack
trimming. Wheel staging is exercised against a small in-test wheel
fixture so we don't need any real wheels.
"""

import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
import unittest.mock as mock
import zipfile
from pathlib import Path

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import render_gds  # noqa: E402

try:
    import yaml  # noqa: F401

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


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


class TestLogPhase(unittest.TestCase):
    """_log_phase writes one grep-friendly line per phase boundary."""

    def _capture(self, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render_gds._log_phase(*args, **kwargs)
        return buf.getvalue()

    def test_writes_phase_marker(self):
        out = self._capture("startup")
        # Format is "render_gds.py [<phase>] VmRSS=… VmPeak=…" — the
        # bracketed phase name is what action-log greps key on.
        self.assertIn("[startup]", out)
        self.assertIn("VmRSS=", out)
        self.assertIn("VmPeak=", out)

    def test_appends_extra(self):
        out = self._capture("gdsii-imported", extra="meshes=42 polygons=123")
        self.assertIn("[gdsii-imported]", out)
        self.assertIn("meshes=42 polygons=123", out)

    def test_no_extra_means_no_trailing_blank(self):
        out = self._capture("addon-registered")
        # The function appends " {extra}" only when extra is truthy; the
        # bare-phase line must not end with a stray space + newline.
        self.assertTrue(out.endswith("\n"))
        self.assertFalse(out.endswith(" \n"))

    def test_survives_missing_proc(self):
        # On platforms without /proc/self/status (or when the file isn't
        # readable), the OSError must not propagate — VmRSS / VmPeak just
        # fall back to "?" and the rest of the line still prints.
        with mock.patch("builtins.open", side_effect=OSError("nope")):
            out = self._capture("startup")
        self.assertIn("[startup]", out)
        self.assertIn("VmRSS=?", out)
        self.assertIn("VmPeak=?", out)


class TestTrimLayerstack(unittest.TestCase):
    """_trim_layerstack returns None on every well-defined error path so
    callers can fall through to the addon's default stackup."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addon_root = Path(self.tmp) / "addon_root"
        self.addon_root.mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_addon(self, pdk_configs=None):
        m = types.ModuleType("fake_addon")
        if pdk_configs is not None:
            m.PDK_CONFIGS = pdk_configs
        return m

    def test_pdk_without_preset_returns_none(self):
        # GF180MCU is a real BlenderGDS PDK but has no preset in
        # _LAYER_PRESETS — fall-through is required so non-sky130 designs
        # get the full default stack rather than an empty trim.
        addon = self._make_addon({"GF180MCU": {"config_path": "x.yaml"}})
        result = render_gds._trim_layerstack(
            addon, str(self.addon_root), "GF180MCU", self.tmp
        )
        self.assertIsNone(result)

    def test_addon_missing_pdk_configs_returns_none(self):
        addon = self._make_addon(pdk_configs=None)
        # SKY130 has a preset but the addon doesn't carry PDK_CONFIGS at
        # all — should not crash.
        result = render_gds._trim_layerstack(
            addon, str(self.addon_root), "SKY130", self.tmp
        )
        self.assertIsNone(result)

    def test_missing_config_path_key_returns_none(self):
        addon = self._make_addon({"SKY130": {}})  # no config_path
        result = render_gds._trim_layerstack(
            addon, str(self.addon_root), "SKY130", self.tmp
        )
        self.assertIsNone(result)

    def test_missing_yaml_file_returns_none(self):
        addon = self._make_addon({"SKY130": {"config_path": "does_not_exist.yaml"}})
        result = render_gds._trim_layerstack(
            addon, str(self.addon_root), "SKY130", self.tmp
        )
        self.assertIsNone(result)

    @unittest.skipIf(not _HAS_YAML, "pyyaml not available in test toolchain")
    def test_trims_to_preset_keeping_yaml_order(self):
        # Build a layerstack YAML with the SKY130 preset's keys + extras;
        # the trimmed output must contain exactly the preset keys, in the
        # order they appear in the input file. Bottom-up extrusion in
        # the addon depends on YAML iteration order.
        cfg = self.addon_root / "stack.yaml"
        cfg.write_text(
            "li1:\n  height: 0.1\n"
            "nwell:\n  height: 0.2\n"
            "mcon:\n  height: 0.3\n"
            "met3:\n  height: 0.4\n"
            "via4:\n  height: 0.5\n"
            "met4:\n  height: 0.6\n"
            "met5:\n  height: 0.7\n",
        )
        addon = self._make_addon({"SKY130": {"config_path": "stack.yaml"}})

        result = render_gds._trim_layerstack(
            addon, str(self.addon_root), "SKY130", self.tmp
        )
        self.assertIsNotNone(result)
        out_path, kept, missing = result

        # Preset for SKY130: ["nwell", "met3", "via4", "met4", "met5"].
        # The dropped ones (li1, mcon) must not appear; the preserved
        # ones must appear in the same order they had in the source.
        self.assertEqual(kept, ["nwell", "met3", "via4", "met4", "met5"])
        self.assertEqual(missing, set())
        self.assertTrue(out_path.is_file())
        body = out_path.read_text()
        self.assertNotIn("li1:", body)
        self.assertNotIn("mcon:", body)
        self.assertIn("nwell:", body)
        self.assertIn("met5:", body)

    @unittest.skipIf(not _HAS_YAML, "pyyaml not available in test toolchain")
    def test_reports_missing_preset_layers(self):
        # If the source YAML lacks one of the preset's layers, _trim
        # still returns the partial trim plus the missing set so the
        # caller can log it (visibility — silent omission would hide
        # PDK-side rename drift).
        cfg = self.addon_root / "partial.yaml"
        cfg.write_text("nwell:\n  height: 0.2\nmet5:\n  height: 0.7\n")
        addon = self._make_addon({"SKY130": {"config_path": "partial.yaml"}})

        out_path, kept, missing = render_gds._trim_layerstack(
            addon,
            str(self.addon_root),
            "SKY130",
            self.tmp,
        )
        self.assertEqual(kept, ["nwell", "met5"])
        self.assertEqual(missing, {"met3", "via4", "met4"})


if __name__ == "__main__":
    unittest.main()
