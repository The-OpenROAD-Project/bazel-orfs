# Auto-select gallery image from latest successful stage

## Problem

The gallery screenshot target in each project's BUILD.bazel hardcodes
which ORFS stage to source the image from:

```starlark
orfs_run(
    name = "MeshWithDelays_gallery",
    src = ":MeshWithDelays_floorplan",  # hardcoded
    ...
)
```

When a project advances (floorplan → CTS → route → final), you have
to manually edit the BUILD to change the source stage. This is busywork
that breaks the "just build" experience — the gallery shows stale
images until someone remembers to update the BUILD.

## Idea

The `demo_gallery_image()` macro in `defs.bzl` should accept the stage
as a parameter (defaulting to the latest available), or auto-detect
the latest completed stage. Options:

1. **Parameter**: `demo_gallery_image(name, module, stage="cts")` —
   explicit, simple, one-line change when advancing
2. **Last-stage**: source from `_final` if it exists, fall back to
   `_route`, `_cts`, `_place`, `_floorplan` — but this requires
   all stages to be buildable, which defeats the purpose
3. **Separate targets per stage**: `demo_stage_images()` already
   exists — just use the latest one for the gallery row

Option 1 is the simplest. The `demo_gallery_image` call becomes:
```starlark
demo_gallery_image(name = "gallery", src = ":MeshWithDelays_cts")
```
Instead of a full `orfs_run` block.

## Impact

Every project maintainer updating gallery images. Eliminates a
manual BUILD edit each time a project advances a stage.

## Per-stage thumbnails in project README

Each project README should show a thumbnail for every completed stage
(floorplan, place, CTS, route). The `demo_stage_images()` macro in
`defs.bzl` already generates per-stage gallery targets — just need to
copy thumbnails and add them to the README. Shows progression visually.

Also: `save_image` doesn't support heatmap opacity — the placement
density heatmap renders fully opaque, unlike the GUI. Need either a
`set_heatmap_alpha` Tcl command or a post-processing step to blend.

## Effort

Trivial — the `demo_gallery_image` macro already exists and takes
a `src` parameter. The only change is updating existing projects
to use it instead of raw `orfs_run` blocks. Per-stage thumbnails
need a small script to copy all available stage images.
