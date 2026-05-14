"""orfs_blender — emit `bazelisk run` targets that open a design's final
GDS in 3D, using the BlenderGDS add-on for layer-aware extrusion.

The macro produces five targets per design:
  {name}_gds       — orfs_gds; runs klayout to produce `6_final.gds`.
  {name}_gen       — runs Blender headless to save a `.blend` scene.
  {name}           — sh_binary; `bazelisk run` exec's hermetic Blender on
                     the saved scene for interactive rotate/zoom.
  {name}_html_gen  — runs Blender headless to export glTF and embed it
                     into a single self-contained HTML page.
  {name}_html      — sh_binary; `bazelisk run` opens the HTML in the
                     default browser via xdg-open. Sharable / no GUI
                     install needed on the viewer's machine.

All targets are tagged "manual" so wildcard builds don't drag in Blender
or the BlenderGDS download.
"""

load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("//private:providers.bzl", "OrfsInfo")
load("//private:rules.bzl", "orfs_gds")

# Maps the trailing component of an ORFS PDK label (e.g. `sky130hd` from
# `@orfs//flow:sky130hd`) to the BlenderGDS PDK key understood by
# import_gdsii (the addon's `gdsii_pdk_selection` scene property).
_PDK_TO_BLENDERGDS = {
    "sky130hd": "SKY130",
    "sky130hs": "SKY130",
    "gf180": "GF180MCU",
    "ihp-sg13g2": "IHP_SG13G2",
}

def _pdk_short_name(pdk):
    if not pdk:
        return None
    s = str(pdk)
    if ":" in s:
        s = s.split(":")[-1]
    return s

def _pdk_to_blendergds(pdk):
    short = _pdk_short_name(pdk)
    if short not in _PDK_TO_BLENDERGDS:
        fail(
            ("orfs_blender: no BlenderGDS stackup for PDK '{pdk}'. " +
             "Supported PDKs: {supported}. Add an entry to " +
             "_PDK_TO_BLENDERGDS in private/blender.bzl with a custom " +
             "YAML if you need another PDK.").format(
                pdk = short,
                supported = ", ".join(sorted(_PDK_TO_BLENDERGDS.keys())),
            ),
        )
    return _PDK_TO_BLENDERGDS[short]

def _find_addon_root(addon_files):
    """Locate the BlenderGDS addon root via the dir of __init__.py."""
    for f in addon_files:
        if f.basename == "__init__.py":
            return f.dirname
    fail("orfs_blender: __init__.py not found in @blendergds//:all")

def _orfs_blender_gen_impl(ctx):
    src_info = ctx.attr.src[OrfsInfo]
    gds = src_info.gds
    if gds == None:
        fail("orfs_blender: src '%s' does not provide a final GDS file. " %
             ctx.attr.src.label +
             "The src must be the output of orfs_gds (which runs klayout " +
             "on the final stage's ODB).")

    addon_root = _find_addon_root(ctx.files.addon)
    out = ctx.actions.declare_file(ctx.label.name + ".blend")

    ctx.actions.run(
        executable = ctx.executable._blender,
        arguments = [
            "--background",
            "--factory-startup",
            "--python",
            ctx.file._render_script.path,
            "--",
            "--gds",
            gds.path,
            "--addon-root",
            addon_root,
            "--pdk",
            ctx.attr.pdk_selection,
            "--out",
            out.path,
        ],
        inputs = depset(
            [gds, ctx.file._render_script] + ctx.files.addon,
        ),
        outputs = [out],
        mnemonic = "BlenderGds",
        progress_message = "BlenderGDS rendering %s" % gds.short_path,
    )

    return [DefaultInfo(files = depset([out]))]

_orfs_blender_gen = rule(
    implementation = _orfs_blender_gen_impl,
    attrs = {
        "src": attr.label(
            mandatory = True,
            providers = [OrfsInfo],
            doc = "An orfs_gds target whose OrfsInfo.gds is the final GDS.",
        ),
        "pdk_selection": attr.string(
            mandatory = True,
            doc = "BlenderGDS PDK key (e.g. SKY130, GF180MCU, IHP_SG13G2).",
        ),
        "addon": attr.label(
            default = "@blendergds//:all",
            allow_files = True,
            doc = "BlenderGDS addon files (the @blendergds// repo).",
        ),
        "_render_script": attr.label(
            default = "@bazel-orfs//tools/blendergds:render_gds.py",
            allow_single_file = True,
        ),
        "_blender": attr.label(
            default = "@bazel-orfs//tools/blender:blender",
            executable = True,
            cfg = "exec",
        ),
    },
)

def _orfs_blender_html_gen_impl(ctx):
    src_info = ctx.attr.src[OrfsInfo]
    gds = src_info.gds
    if gds == None:
        fail("orfs_blender: src '%s' does not provide a final GDS file." %
             ctx.attr.src.label)

    addon_root = _find_addon_root(ctx.files.addon)
    out = ctx.actions.declare_file(ctx.label.name + ".html")

    ctx.actions.run(
        executable = ctx.executable._blender,
        arguments = [
            "--background",
            "--factory-startup",
            "--python",
            ctx.file._render_script.path,
            "--",
            "--gds",
            gds.path,
            "--addon-root",
            addon_root,
            "--pdk",
            ctx.attr.pdk_selection,
            "--out-html",
            out.path,
            "--html-template",
            ctx.file._html_template.path,
            "--model-viewer-js",
            ctx.file._model_viewer_js.path,
            "--title",
            ctx.attr.title or ctx.label.name,
        ],
        inputs = depset(
            [
                gds,
                ctx.file._render_script,
                ctx.file._html_template,
                ctx.file._model_viewer_js,
            ] + ctx.files.addon,
        ),
        outputs = [out],
        mnemonic = "BlenderGdsHtml",
        progress_message = "BlenderGDS html-export %s" % gds.short_path,
    )

    return [DefaultInfo(files = depset([out]))]

_orfs_blender_html_gen = rule(
    implementation = _orfs_blender_html_gen_impl,
    attrs = {
        "src": attr.label(
            mandatory = True,
            providers = [OrfsInfo],
            doc = "An orfs_gds target whose OrfsInfo.gds is the final GDS.",
        ),
        "pdk_selection": attr.string(
            mandatory = True,
            doc = "BlenderGDS PDK key (e.g. SKY130, GF180MCU, IHP_SG13G2).",
        ),
        "title": attr.string(
            doc = "Page title rendered into the HTML output.",
        ),
        "addon": attr.label(
            default = "@blendergds//:all",
            allow_files = True,
            doc = "BlenderGDS addon files (the @blendergds// repo).",
        ),
        "_render_script": attr.label(
            default = "@bazel-orfs//tools/blendergds:render_gds.py",
            allow_single_file = True,
        ),
        "_html_template": attr.label(
            default = "@bazel-orfs//tools/blendergds:viewer_template.html",
            allow_single_file = True,
        ),
        "_model_viewer_js": attr.label(
            default = "@model_viewer_js//file",
            allow_single_file = True,
        ),
        "_blender": attr.label(
            default = "@bazel-orfs//tools/blender:blender",
            executable = True,
            cfg = "exec",
        ),
    },
)

def orfs_blender(name, src, pdk, variant = None, klayout = None, visibility = None):
    """Emit {name}_gds, {name}_gen, {name}, {name}_html_gen, {name}_html.

    Args:
      name: base name for the emitted targets.
      src: an orfs_final-stage target (whose OrfsInfo.odb feeds the klayout
        GDS-write step).
      pdk: the PDK label this design was built with. Used to pick the
        BlenderGDS stackup config. Must be one of the keys in
        _PDK_TO_BLENDERGDS above.
      variant: orfs_flow variant ("base" if unset).
      klayout: override klayout binary for the orfs_gds step. Defaults
        to @bazel-orfs//:klayout, which exec's `klayout` from the host's
        PATH — the mock klayout used elsewhere in the flow can't produce
        a usable GDS for 3D import. Pass an explicit label here to use a
        different, hermetic klayout.
      visibility: visibility for the emitted targets.
    """
    pdk_selection = _pdk_to_blendergds(pdk)

    gds_name = name + "_gds"
    gen_name = name + "_gen"
    html_gen_name = name + "_html_gen"
    html_name = name + "_html"

    orfs_gds(
        name = gds_name,
        src = src,
        klayout = klayout or "@bazel-orfs//:klayout",
        variant = variant or "base",
        tags = ["manual"],
        visibility = visibility,
    )

    _orfs_blender_gen(
        name = gen_name,
        src = ":" + gds_name,
        pdk_selection = pdk_selection,
        tags = ["manual"],
        visibility = visibility,
    )

    sh_binary(
        name = name,
        srcs = ["@bazel-orfs//:open_blend.sh"],
        args = [
            "$(rootpath :" + gen_name + ")",
            "$(rootpath @blender//:blender)",
        ],
        data = [
            ":" + gen_name,
            "@blender//:blender",
            "@blender//:blender_runtime",
        ],
        tags = ["manual"],
        visibility = visibility,
    )

    _orfs_blender_html_gen(
        name = html_gen_name,
        src = ":" + gds_name,
        pdk_selection = pdk_selection,
        title = name,
        tags = ["manual"],
        visibility = visibility,
    )

    sh_binary(
        name = html_name,
        srcs = ["@bazel-orfs//:open_html.sh"],
        args = ["$(rootpath :" + html_gen_name + ")"],
        data = [":" + html_gen_name],
        tags = ["manual"],
        visibility = visibility,
    )
