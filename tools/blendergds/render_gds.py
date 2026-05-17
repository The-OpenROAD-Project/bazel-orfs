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
import traceback
import zipfile
from pathlib import Path


# Per-PDK "bling and fun" layer preset.  Each entry is the subset of
# the addon's bundled layerstack YAML we keep when trimming for a
# browser-loadable viewer:
#
#   * One substrate layer (paints the chip's transistor regions as a
#     coloured background, so the viewer doesn't look like a bare
#     metal stack floating in space).
#   * The topmost 2-3 metal layers + the highest via stack between
#     them (macros and top-level routing -- the visually distinctive
#     bits that say "this is microwatt", "this is gcd", etc.).
#
# The dense interconnect / contact / lower-metal layers (mcon, licon,
# li1, met1, met2, via, via2 on sky130) are dropped wholesale.  They
# carry most of the polygon count but read as featureless noise at
# any zoom level that fits a 10mm² chip on a laptop screen.
#
# Effect on microwatt sky130hd: drops ~26M input polygons down to
# ~200K; the Blender per-layer extrusion that previously cost ~5-7 min
# + 16 GB RSS becomes seconds and tens of MB.  The resulting GLB lands
# under ~80 MB, the base64-embedded HTML under ~110 MB -- well inside
# any browser tab's working budget.
#
# PDKs not in the table fall through to the unfiltered addon default
# stack (gcd-class designs already fit; bigger designs in other PDKs
# will need their own preset added here).
_LAYER_PRESETS = {
    "SKY130": ["nwell", "met3", "via4", "met4", "met5"],
}


def _trim_layerstack(addon_module, addon_root, pdk_selection, tmpdir):
    """Build a trimmed layerstack YAML containing only the entries listed
    in _LAYER_PRESETS[pdk_selection], in the original YAML's order.

    Returns the path to the trimmed YAML to feed back into the addon via
    `gdsii_use_custom_config=True` + `gdsii_config_path=<this>`, or None
    if the PDK has no preset (fall through to the addon's default stack).
    """
    preset = _LAYER_PRESETS.get(pdk_selection)
    if not preset:
        return None
    pdk_info = getattr(addon_module, "PDK_CONFIGS", {}).get(pdk_selection, {})
    rel = pdk_info.get("config_path")
    if not rel:
        return None
    yamlfile = Path(addon_root) / rel
    if not yamlfile.is_file():
        return None

    import yaml  # staged via the addon's wheels

    full = yaml.safe_load(yamlfile.read_text(encoding="utf-8"))
    keep = set(preset)
    # Preserve YAML insertion order so z-stack semantics in the addon
    # (bottom-up extrusion + layered rendering) match the bundled file.
    trimmed = {name: data for name, data in full.items() if name in keep}
    missing = keep - trimmed.keys()
    out = Path(tmpdir) / "trimmed_layerstack.yaml"
    out.write_text(yaml.safe_dump(trimmed, default_flow_style=False, sort_keys=False))
    return out, list(trimmed.keys()), missing


def _log_phase(phase: str, extra: str = "") -> None:
    """Print a single-line phase marker with VmRSS / VmPeak.

    Blender's --background mode produces a lot of output; these prefixed
    lines make it easy to grep the action log for the failing phase
    (e.g. addon-register, klayout-merge inside gdsii operator, gltf-export,
    html-write) and to see exactly where RSS spikes before an OOM.
    """
    rss = peak = "?"
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss = line.split(":", 1)[1].strip()
                elif line.startswith("VmPeak:"):
                    peak = line.split(":", 1)[1].strip()
    except OSError:
        pass
    msg = f"render_gds.py [{phase}] VmRSS={rss} VmPeak={peak}"
    if extra:
        msg += f" {extra}"
    print(msg, flush=True)


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

    _log_phase("startup", extra=f"gds={gds_path} ({gds_path.stat().st_size} bytes)")

    # Stage wheels into a temp site-packages and put it on sys.path BEFORE
    # importing the addon (which imports numpy/gdstk/klayout/yaml at module
    # scope).
    tmp = Path(tempfile.mkdtemp(prefix="blendergds-"))
    site = tmp / "site-packages"
    site.mkdir()
    try:
        _stage_wheels(wheels_dir, site)
        sys.path.insert(0, str(site))
        _log_phase("wheels-staged")

        # bpy is provided by Blender; importing it before this point would
        # leak partial init in --background mode.
        import bpy  # noqa: E402

        addon = _load_addon_module(addon_root)
        addon.register()
        _log_phase("addon-registered")

        # The addon's register_properties() declares four scene props via
        # the legacy `bpy.types.Scene.X = StringProperty(...)` form. In
        # Blender 4.2 that registration is unreliable for empty-default
        # string props, so we only force the ones we actually need to
        # deviate from the addon's defaults.
        bpy.context.scene.gdsii_pdk_selection = args.pdk

        # Pre-trim the PDK layerstack to a "bling and fun" subset.  This
        # MUST happen before bpy.ops.import_scene.gdsii because the
        # addon's per-layer extrusion loop reads the layerstack YAML
        # and pays full RAM/time cost for every entry; dropping entries
        # at the YAML level is what lets a 562 MB GDS (microwatt) finish
        # in seconds rather than 5-7 minutes + 16 GB RSS.  No-op for
        # PDKs without a preset and for designs whose full stack is
        # already small enough.
        trimmed = _trim_layerstack(addon, addon_root, args.pdk, tmp)
        if trimmed is not None:
            yaml_path, kept_layers, missing = trimmed
            bpy.context.scene.gdsii_use_custom_config = True
            bpy.context.scene.gdsii_config_path = str(yaml_path)
            _log_phase(
                "layerstack-trimmed",
                extra=(
                    f"kept={kept_layers} "
                    + (f"missing={sorted(missing)} " if missing else "")
                    + f"yaml={yaml_path}"
                ),
            )

        try:
            result = bpy.ops.import_scene.gdsii(
                filepath=str(gds_path),
                setup_scene=True,
                create_collection=True,
                merge_layers=True,
                color_scheme="realistic",
            )
        except Exception:
            _log_phase("gdsii-import-exception")
            traceback.print_exc()
            sys.exit("render_gds.py: import_scene.gdsii raised — see traceback above")
        if "FINISHED" not in result:
            _log_phase("gdsii-import-nonfinished", extra=f"result={result!r}")
            sys.exit(f"render_gds.py: import_scene.gdsii returned {result!r}")

        mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
        total_polys = sum(len(o.data.polygons) for o in mesh_objs)
        total_verts = sum(len(o.data.vertices) for o in mesh_objs)
        _log_phase(
            "gdsii-imported",
            extra=f"meshes={len(mesh_objs)} polygons={total_polys} verts={total_verts}",
        )

        if args.out:
            out_path = Path(args.out).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(out_path), copy=True)
            _log_phase("blend-saved", extra=f"{out_path.stat().st_size} bytes")

        if args.out_html:
            # io_scene_gltf2 ships with Blender as a core addon but is not
            # active under --factory-startup. Enable it before exporting.
            bpy.ops.preferences.addon_enable(module="io_scene_gltf2")
            _log_phase("gltf-addon-enabled")

            glb_tmp = tmp / "scene.glb"
            try:
                export_result = bpy.ops.export_scene.gltf(
                    filepath=str(glb_tmp),
                    export_format="GLB",
                    export_apply=True,
                    export_yup=True,
                    export_lights=False,
                    export_cameras=False,
                    use_active_scene=True,
                    # Per-corner attribute exports use foreach_get under the
                    # hood and Blender 4.2's RNA bridge stores the element
                    # count in a signed int32.  Microwatt's mcon layer alone
                    # has ~9.3M extruded polygons × 6 faces × 4 corners ≈
                    # 223M corner-normals = 669M float32 values, which
                    # overflows int32 and yields:
                    #
                    #   Error: Array length mismatch
                    #          (expected -464636871, got 609104952)
                    #   RuntimeError: internal error setting the array
                    #
                    # in gltf2_blender_gather_primitives_extract.__get_normals.
                    # Disabling normals (and the other per-corner attributes
                    # gated by foreach_get -- tangents, vertex colors)
                    # short-circuits the failing path before it allocates
                    # the oversized buffer.  model-viewer falls back to
                    # face-derived flat normals, which is the right look
                    # for a chip-layout scene anyway (no smooth shading).
                    export_normals=False,
                    export_tangents=False,
                    export_attributes=False,
                    export_vertex_color="NONE",
                )
            except Exception:
                _log_phase("gltf-export-exception")
                traceback.print_exc()
                sys.exit(
                    "render_gds.py: export_scene.gltf raised — see traceback above"
                )
            if "FINISHED" not in export_result:
                _log_phase("gltf-export-nonfinished", extra=f"result={export_result!r}")
                sys.exit(f"render_gds.py: export_scene.gltf returned {export_result!r}")
            _log_phase("gltf-exported", extra=f"glb={glb_tmp.stat().st_size} bytes")

            _write_html(
                template_path=Path(args.html_template).resolve(),
                model_viewer_js_path=Path(args.model_viewer_js).resolve(),
                glb_bytes=glb_tmp.read_bytes(),
                title=args.title,
                out_path=Path(args.out_html).resolve(),
            )
            _log_phase(
                "html-written",
                extra=f"out={Path(args.out_html).stat().st_size} bytes",
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
