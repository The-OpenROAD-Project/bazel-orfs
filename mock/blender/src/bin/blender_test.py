#!/usr/bin/env python3
"""Tests for the mock-blender entry point and its fake bpy module."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import blender  # noqa: E402


class TestParseBlenderArgv(unittest.TestCase):
    def test_python_and_inner_args(self):
        script, inner = blender._parse_blender_argv(
            ["--background", "--factory-startup", "--python", "/s.py",
             "--", "--gds", "x.gds", "--out", "/o.blend"],
        )
        self.assertEqual(script, "/s.py")
        self.assertEqual(inner, ["--gds", "x.gds", "--out", "/o.blend"])

    def test_no_double_dash_means_empty_inner(self):
        script, inner = blender._parse_blender_argv(
            ["--background", "--python", "/s.py"],
        )
        self.assertEqual(script, "/s.py")
        self.assertEqual(inner, [])

    def test_no_python_returns_none(self):
        script, inner = blender._parse_blender_argv(
            ["--background", "--factory-startup"],
        )
        self.assertIsNone(script)
        self.assertEqual(inner, [])

    def test_short_b_flag_accepted(self):
        # Real Blender accepts -b as a short form of --background.
        script, _ = blender._parse_blender_argv(
            ["-b", "--python", "/s.py"],
        )
        self.assertEqual(script, "/s.py")


class TestFakeBpyOps(unittest.TestCase):
    def test_op_call_returns_finished_set(self):
        bpy = blender.make_fake_bpy()
        result = bpy.ops.import_scene.gdsii(filepath="x.gds")
        self.assertEqual(result, {"FINISHED"})

    def test_op_call_is_recorded(self):
        bpy = blender.make_fake_bpy()
        bpy.ops.import_scene.gdsii(filepath="x.gds", setup_scene=True)
        # _calls is a list of (op_name, args, kwargs) tuples.
        self.assertEqual(len(bpy._calls), 1)
        name, args, kwargs = bpy._calls[0]
        self.assertEqual(name, "import_scene.gdsii")
        self.assertEqual(args, ())
        self.assertEqual(kwargs["filepath"], "x.gds")
        self.assertTrue(kwargs["setup_scene"])

    def test_save_as_mainfile_writes_blend_stub(self):
        bpy = blender.make_fake_bpy()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.blend")
            bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
            self.assertTrue(os.path.isfile(out))
            with open(out, "rb") as f:
                self.assertTrue(f.read().startswith(b"BLENDER"))

    def test_export_scene_gltf_writes_glb_stub(self):
        bpy = blender.make_fake_bpy()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "scene.glb")
            bpy.ops.export_scene.gltf(filepath=out, export_format="GLB")
            self.assertTrue(os.path.isfile(out))
            with open(out, "rb") as f:
                self.assertEqual(f.read(4), b"glTF")

    def test_scene_attribute_assignment(self):
        # Mirrors `bpy.context.scene.gdsii_pdk_selection = "SKY130"`.
        bpy = blender.make_fake_bpy()
        bpy.context.scene.gdsii_pdk_selection = "SKY130"
        self.assertEqual(bpy.context.scene.gdsii_pdk_selection, "SKY130")

    def test_types_scene_addon_style_attr_assignment(self):
        # Addons commonly do `bpy.types.Scene.X = StringProperty(...)`.
        # The stub Scene is a plain class so this just works.
        bpy = blender.make_fake_bpy()
        bpy.types.Scene.gdsii_pdk_selection = "default"
        self.assertEqual(bpy.types.Scene.gdsii_pdk_selection, "default")


class TestEndToEnd(unittest.TestCase):
    """Run a tiny script through mock-blender's main() and assert the
    stub bpy behaviour reaches it."""

    def test_inner_script_sees_fake_bpy(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "probe.py")
            marker = os.path.join(tmp, "out.blend")
            Path(script).write_text(
                "import bpy\n"
                "import sys\n"
                "marker = sys.argv[1]\n"
                "bpy.context.scene.gdsii_pdk_selection = 'TEST_PDK'\n"
                "result = bpy.ops.import_scene.gdsii(filepath='x.gds')\n"
                "assert result == {'FINISHED'}, result\n"
                "bpy.ops.wm.save_as_mainfile(filepath=marker, copy=True)\n",
            )
            rc = blender.main(
                ["--background", "--factory-startup",
                 "--python", script, "--", marker],
            )
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(marker))

    def test_version_probe(self):
        # Some build steps probe `blender --version`; mirror real
        # Blender's output enough for substring matches.
        # We capture stdout by redirecting in this test process.
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = blender.main(["--version"])
        self.assertEqual(rc, 0)
        self.assertIn("Blender", buf.getvalue())

    def test_script_systemexit_propagates_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "exit.py")
            Path(script).write_text("import sys\nsys.exit(7)\n")
            rc = blender.main(
                ["--background", "--python", script, "--"],
            )
            self.assertEqual(rc, 7)


if __name__ == "__main__":
    unittest.main()
