# Composed ASAP7 PDK (`//pdk/asap7`)

`//pdk/asap7:asap7` composes the ASAP7 7.5-track standard-cell PDK directly in
Bazel using `orfs_pdk_overlay`, combining `@orfs//flow:asap7`'s platform
scripts (`config.mk`, `setRC.tcl`, `fastroute.tcl`, `tapcell.tcl`, PDN and
Yosys mapping files) with the upstream cell views from
[`The-OpenROAD-Project/asap7sc7p5t_28`](https://github.com/The-OpenROAD-Project/asap7sc7p5t_28)
(including the 256 standard cells — 64 functions across `RVT`, `LVT`, `SLVT`,
and `SRAM` — added in
[asap7sc7p5t_28#13](https://github.com/The-OpenROAD-Project/asap7sc7p5t_28/pull/13)).

Nothing is vendored into `@orfs`:

- `asap7sc7p5t_28` (`repos.bzl`) lazily fetches only the 25 required upstream
  files (`1x` LEFs, GDS, Verilog, and `ADDED` NLDM/CCS `.lib.7z` archives), each
  pinned by `sha256`.
- `un7z_gz` (`rules.bzl`, `un7z_gz.cc`) extracts `.lib.7z` to deterministic
  `.lib.gz` (`mtime = 0`) via `@libarchive`.
- `inject_vt_obs.py` injects the `RVTN`/`RVTP`, `LVTN`/`LVTP`, and
  `SLVTN`/`SLVTP` implant `OBS` rectangles omitted from upstream
  `asap7sc7p5t_28` LEFs, which OpenROAD's `Resizer::cellVTType()` and `dpl`
  filler placement require to distinguish VT classes.
- `orfs_pdk_overlay` (`openroad.bzl`) stages the merged platform directory,
  reuses `@orfs//flow:asap7`'s pre-compiled binary liberties for all unchanged
  libraries, and runs `WriteLibertyBinary` only on the overlaid `ADDED`
  Liberty files.

## Usage

Per flow:

```starlark
orfs_flow(
    name = "my_design",
    pdk = "@bazel-orfs//pdk/asap7",
    ...
)
```

Or workspace-wide in `MODULE.bazel`:

```starlark
orfs.default(
    pdk = "@bazel-orfs//pdk/asap7",
)
```
