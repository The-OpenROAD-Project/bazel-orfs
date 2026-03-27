"""Gallery image macros for the OpenROAD Demo Gallery.

Generate screenshots and thumbnails from ORFS stage outputs.
"""

load("@bazel-orfs//:openroad.bzl", _orfs_run = "orfs_run")

orfs_run = _orfs_run

# Per-stage gallery scripts — each stage has different interesting features.
_STAGE_SCRIPTS = {
    "floorplan": "//scripts:floorplan_image.tcl",
    "place": "//scripts:place_image.tcl",
    "cts": "//scripts:cts_image.tcl",
    "grt": "//scripts:grt_image.tcl",
    "route": "//scripts:route_image.tcl",
    "final": "//scripts:route_image.tcl",
}

def demo_gallery_image(
        name,
        src,
        stage = None,
        thumbnail_size = 400):
    """Generate a gallery screenshot and thumbnail from an ORFS stage.

    Uses a per-stage Tcl script for optimal display settings (e.g. CTS
    hides power/ground, route shows signal nets). Falls back to the
    generic gallery_image.tcl for unknown stages.

    Creates two targets:
        :<name>      — full-resolution screenshot (.webp)
        :<name>_thumb — resized thumbnail (.webp)

    Args:
        name: Target name (e.g., "multiplier_gallery")
        src: The orfs stage target to screenshot (e.g., ":multiplier_route")
        stage: Stage name for script selection (e.g., "cts"). Auto-detected from src if None.
        thumbnail_size: Max dimension in pixels for thumbnail (default: 400)
    """
    script = _STAGE_SCRIPTS.get(stage, "//scripts:gallery_image.tcl")
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".webp"],
        arguments = {
            "GALLERY_IMAGE": "$(location :" + name + ".webp)",
            "OR_ARGS": "-gui",
        },
        extra_args = "OPENROAD_CMD='xvfb-run -a $(OPENROAD_EXE) -exit $(OPENROAD_ARGS)'",
        script = script,
    )

    native.genrule(
        name = name + "_thumb",
        srcs = [":" + name],
        outs = [name + "_thumb.webp"],
        cmd = "$(execpath //scripts:resize_image) $(SRCS) $@ --size " + str(thumbnail_size),
        tools = ["//scripts:resize_image"],
    )

def demo_stage_images(
        name,
        module,
        stages = None):
    """Generate gallery images at multiple ORFS stages.

    Creates `<name>_<stage>` and `<name>_<stage>_thumb` targets for each
    specified stage. Images show how the design evolves through the flow —
    from empty die at floorplan to final routed design.

    Args:
        name: Target name prefix (e.g. "MeshWithDelays_images")
        module: The orfs_flow target name (e.g. "MeshWithDelays")
        stages: List of stages to image (default: ["floorplan", "place", "cts", "route"])
    """
    if stages == None:
        stages = ["floorplan", "place", "cts", "grt", "route"]
    for stage in stages:
        demo_gallery_image(
            name = name + "_" + stage,
            src = ":" + module + "_" + stage,
            stage = stage,
        )
