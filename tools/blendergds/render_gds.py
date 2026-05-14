"""Headless driver for the BlenderGDS addon.

Invoked from a Bazel action as:

    blender --background --factory-startup --python render_gds.py -- \\
        --gds <design.gds> \\
        --addon-root <dir-with-__init__.py-and-wheels> \\
        --pdk SKY130 \\
        [--out <out.blend>] \\
        [--out-html <out.html> --html-template <template.html> \\
         --model-viewer-js <model-viewer.min.js>]

Unpacks the bundled wheels into a tmp dir, prepends them and the addon
to sys.path, registers the addon as the `import_gdsii` package, sets the
PDK scene properties the addon expects, then calls
`bpy.ops.import_scene.gdsii`.

Writes one or both outputs:
- `--out`      saves the scene as a Blender file.
- `--out-html` exports the scene as glTF (.glb) via Blender's built-in
               io_scene_gltf2 core addon, then base64-embeds it together
               with the model-viewer web component into the HTML template
               so the resulting file is a single self-contained viewer
               page.

Standalone — has no bazel-orfs dependencies and is designed to be
upstreamable to aesc-silicon/BlenderGDS as a headless entry point.
"""

import argparse
import base64
import importlib.util
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


def _split_argv():
    """Return Blender's pass-through args (everything after `--`)."""
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gds", required=True, help="Path to the input GDSII file.")
    parser.add_argument(
        "--addon-root",
        required=True,
        help=(
            "Directory containing the BlenderGDS addon (__init__.py, "
            "configs/, wheels/). Typically the @blendergds// repo root."
        ),
    )
    parser.add_argument(
        "--pdk",
        required=True,
        help=(
            "BlenderGDS PDK key (e.g. SKY130, GF180MCU, IHP_SG13G2). "
            "Must match a key in the addon's PDK_CONFIGS dict."
        ),
    )
    parser.add_argument("--out", help="If set, save the scene to this .blend path.")
    parser.add_argument(
        "--out-html",
        help=(
            "If set, export the scene as glTF and base64-embed it into "
            "the HTML template, writing a single self-contained viewer."
        ),
    )
    parser.add_argument(
        "--html-template",
        help="Path to viewer_template.html (required with --out-html).",
    )
    parser.add_argument(
        "--model-viewer-js",
        help="Path to model-viewer.min.js (required with --out-html).",
    )
    parser.add_argument(
        "--title",
        default="ORFS layout",
        help="Page title rendered into the HTML output.",
    )
    args = parser.parse_args(_split_argv())
    if not args.out and not args.out_html:
        parser.error("at least one of --out / --out-html must be set")
    if args.out_html and not (args.html_template and args.model_viewer_js):
        parser.error("--out-html requires --html-template and --model-viewer-js")
    return args


def _python_tag():
    """Return the cpXY tag matching this Blender's Python (e.g. 'cp311')."""
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def _stage_wheels(wheels_dir: Path, dest: Path) -> None:
    """Extract every wheel that matches this Python's ABI into `dest`.

    Wheels named *-pyX-none-any.whl (pure Python) and *-<cpXY>-* (binary)
    are unzipped flat into `dest`, which is then put on sys.path.
    """
    cp_tag = _python_tag()
    for whl in sorted(wheels_dir.glob("*.whl")):
        name = whl.name
        # Accept either pure-Python wheels or wheels tagged for this cpython.
        if cp_tag not in name and "py3-none-any" not in name:
            continue
        with zipfile.ZipFile(whl) as zf:
            zf.extractall(dest)
    if not any(dest.iterdir()):
        sys.exit(
            f"render_gds.py: no wheels matched Python tag {cp_tag} under {wheels_dir}"
        )


def _load_addon_module(addon_root: Path):
    """Import the BlenderGDS addon as the `import_gdsii` package."""
    init_py = addon_root / "__init__.py"
    if not init_py.is_file():
        sys.exit(f"render_gds.py: no __init__.py at {init_py}")

    spec = importlib.util.spec_from_file_location(
        "import_gdsii",
        init_py,
        submodule_search_locations=[str(addon_root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_gdsii"] = module
    spec.loader.exec_module(module)
    return module


def _write_html(
    template_path: Path,
    model_viewer_js_path: Path,
    glb_bytes: bytes,
    title: str,
    out_path: Path,
) -> None:
    """Fill the viewer template with the glTF payload and the model-viewer JS."""
    template = template_path.read_text(encoding="utf-8")
    model_viewer_js = model_viewer_js_path.read_text(encoding="utf-8")
    glb_b64 = base64.b64encode(glb_bytes).decode("ascii")
    html = (
        template.replace("{{TITLE}}", title)
        .replace("{{MODEL_VIEWER_JS}}", model_viewer_js)
        .replace("{{GLB_B64}}", glb_b64)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def main():
    args = _parse_args()

    gds_path = Path(args.gds).resolve()
    addon_root = Path(args.addon_root).resolve()
    wheels_dir = addon_root / "wheels"

    if not gds_path.is_file():
        sys.exit(f"render_gds.py: GDS not found: {gds_path}")
    if not wheels_dir.is_dir():
        sys.exit(f"render_gds.py: wheels/ dir not found under {addon_root}")

    # Stage wheels into a temp site-packages and put it on sys.path BEFORE
    # importing the addon (which imports numpy/gdstk/klayout/yaml at module
    # scope).
    tmp = Path(tempfile.mkdtemp(prefix="blendergds-"))
    site = tmp / "site-packages"
    site.mkdir()
    try:
        _stage_wheels(wheels_dir, site)
        sys.path.insert(0, str(site))

        # bpy is provided by Blender; importing it before this point would
        # leak partial init in --background mode.
        import bpy  # noqa: E402

        addon = _load_addon_module(addon_root)
        addon.register()

        # The addon's register_properties() declares four scene props via
        # the legacy `bpy.types.Scene.X = StringProperty(...)` form. In
        # Blender 4.2 that registration is unreliable for empty-default
        # string props, so we only force the one that actually deviates
        # from the addon's default (the PDK key). The other three keep
        # their addon defaults — use_custom_config=False, custom_*=""—
        # which is what we want anyway.
        bpy.context.scene.gdsii_pdk_selection = args.pdk

        result = bpy.ops.import_scene.gdsii(
            filepath=str(gds_path),
            setup_scene=True,
            create_collection=True,
            merge_layers=True,
            color_scheme="realistic",
        )
        if "FINISHED" not in result:
            sys.exit(f"render_gds.py: import_scene.gdsii returned {result!r}")

        if args.out:
            out_path = Path(args.out).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(out_path), copy=True)

        if args.out_html:
            # io_scene_gltf2 ships with Blender as a core addon but is not
            # active under --factory-startup. Enable it before exporting.
            bpy.ops.preferences.addon_enable(module="io_scene_gltf2")

            glb_tmp = tmp / "scene.glb"
            export_result = bpy.ops.export_scene.gltf(
                filepath=str(glb_tmp),
                export_format="GLB",
                export_apply=True,
                export_yup=True,
                export_lights=False,
                export_cameras=False,
                use_active_scene=True,
            )
            if "FINISHED" not in export_result:
                sys.exit(f"render_gds.py: export_scene.gltf returned {export_result!r}")

            _write_html(
                template_path=Path(args.html_template).resolve(),
                model_viewer_js_path=Path(args.model_viewer_js).resolve(),
                glb_bytes=glb_tmp.read_bytes(),
                title=args.title,
                out_path=Path(args.out_html).resolve(),
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
