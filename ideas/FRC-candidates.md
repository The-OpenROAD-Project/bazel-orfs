# FRC Candidates

Feature Request Candidates sourced from OpenROAD-flow-scripts and OpenROAD
git history, issues, PRs, and discussions (Jan-Mar 2026).

## Tier 1: High Impact

### FRC: Synthesis Determinism (Yosys abc_new)

**Source:** ORFS #4056 (issue), #4058 (PR, open)

Repeated Yosys synthesis runs produce different netlists because `abc_new`
module visitation order varies between runs. This breaks Bazel's
content-addressed caching: nondeterministic outputs invalidate all
downstream cache entries.

PR #4058 inserts a `sort` command before ABC execution, controlled by
`SYNTH_SORT_BEFORE_ABC`. Runtime cost is ~125ms.

**Action:** Once merged upstream, enable by default in bazel-orfs. Consider
applying the sort in the synthesis wrapper if upstream is slow to merge.

---

### FRC: RAM Generator Integration

**Source:** OpenROAD #9392 (feature tracker), src/ram/ module

OpenROAD has a new DFF-based RAM compiler (`generate_ram` Tcl command) that
builds placed-and-routed memory blocks from standard cells. Currently
tested on sky130hd.

**Capabilities:**
- Configurable word size, depth, and write mask granularity
- Auto-detects storage cells (DFFs), tristates, inverters from Liberty
- Produces: placed/routed DEF, abstract LEF, behavioral Verilog
- Integrates PDN, pin placement, filler insertion, global + detailed routing
- Parameters: `-mask_size`, `-word_size`, `-num_words`, `-read_ports` (currently 1 only),
  `-power_pin`, `-ground_pin`, `-routing_layer`, `-ver_layer`, `-hor_layer`,
  `-filler_cells`, `-tapcell`, `-write_behavioral_verilog`

**Architecture:** Cell -> Layout -> Grid hierarchy. Each bit = 1 DFF + tristate
output buffer. Binary address decoder using AND gate trees. Clock gating per
write-mask slice.

**Action:** Create a `ram_library` Bazel rule that wraps `generate_ram` and
produces LEF/Liberty/Verilog artifacts consumable by `orfs_flow` as macros.

---

### FRC: PRE/POST Tcl Hooks for Flow Steps

**Source:** ORFS commit bacd07403, variables.yaml

Systematic PRE_*_TCL and POST_*_TCL environment variables for 16 flow stages
(floorplan, io_placement, macro_place, global_place, detail_place,
repair_timing, resize, cts, pdn, tapcell, global_route, detail_route,
fillcell, density_fill, final_report).

Invoked via `source_step_tcl PRE DETAIL_PLACE` / `source_step_tcl POST DETAIL_PLACE`
in each stage script.

**Action:** Expose hook variables in `orfs_flow` rule attributes so users can
inject custom Tcl at any stage. Map to Bazel file dependencies for sandboxing.

---

### FRC: KLayout Optional / GDS Decoupling

**Source:** ORFS commit 3d0bc18d2, docs/KLayoutOptionalDependency.md

GDS generation decoupled from `finish`. New `make gds` target is separate.
`generate_klayout_tech.py` generates .lyt files using pure Python (no KLayout).
`def2stream.py` guards `import pya` behind try/except.

**Impact matrix:**
| Target | Requires KLayout |
|---|---|
| `make do-finish` | No |
| `make gds` | Yes |
| `make generate_abstract` | No |

**Action:** bazel-orfs already doesn't produce GDS by default. Verify
alignment with upstream changes and update if needed.

---

### FRC: LEC Per-Stage Targets

**Source:** ORFS #3918 (issue, open)

Request for `make lec-floorplan`, `lec-place`, `lec-cts`, `lec-grt`,
`lec-drt`, `lec-final` targets for Logic Equivalence Checking at each stage.
Users want LEC off by default, opt-in per stage.

**Action:** Natural fit for Bazel's target model. Create optional `lec_check`
targets per stage that users can selectively depend on.

---

### FRC: VHDL Frontend Support via ghdl

**Source:** ORFS #4078 (PR, draft)

Adds VHDL file support through ghdl Yosys frontend with counter examples
for sky130hd and ihp-sg13g2.

**Action:** Add `vhdl_files` attribute to `orfs_flow` alongside `verilog_files`.

---

## Tier 2: Medium Impact

### FRC: Segment-Based RC Correlation

**Source:** ORFS commit 9750e41db, #3969, #4040

New `write_segment_rc.tcl` extracts per-wire-segment parasitics (layer,
length, R, C) instead of per-net aggregates. `correlateRC.py --mode segment`
runs per-layer linear regression to derive `set_layer_rc` commands.

Compared to net mode: finer granularity, per-layer R² validation,
higher accuracy for RC estimation.

**Action:** Expose segment RC correlation as a flow utility in bazel-orfs.

---

### FRC: Yosys Memory Mapping

**Source:** ORFS #3768 (issue, open)

`SYNTH_MEMORIES=memories.txt` option for Yosys memory mapping. Users list
memories and provide them via `ADDITIONAL_LIBS/LEFS/GDS`.

**Action:** Expose memory mapping configuration in `orfs_flow`.

---

### FRC: DRT Determinism

**Source:** ORFS #4071 (PR, merged), OpenROAD #9984

Detailed route determinism improvements with metrics updates. Ongoing work
to make the flow reproducible -- important for Bazel caching.

**Action:** Track upstream progress. Add determinism verification tests
similar to OpenROAD's `check_same.bzl` idempotency macro (commit 8d87f8408f).

---

### FRC: Standalone OpenROAD Binary (Tcl 9 Packaging)

**Source:** OpenROAD #9980

Embedding Tcl system files into the binary via Tcl 9 virtual filesystem.
Eliminates symlink trees and makes the binary standalone.

**Action:** Simplifies `@openroad//:openroad` target and removes runfile
issues. Monitor progress and update packaging when available.

---

### FRC: OpenROAD Debug/Profiling Mode

**Source:** ORFS commit 467132e43 (#4044, merged)

`flow.sh` now uses `eval` on `OPENROAD_EXE`, enabling wrappers like
`OPENROAD_EXE="valgrind openroad"`.

**Action:** Support a debug/profiling mode in bazel-orfs that wraps the
OpenROAD binary with valgrind, perf, or other tools.

---

### FRC: Metric Sanity Validation

**Source:** ORFS #3850

mock-cpu reports `1e+42` hold WNS since Nov 2025. Bogus metric values
go undetected.

**Action:** Add metric range checks to bazel-orfs test rules. Flag
obviously invalid values (infinity, NaN, extreme magnitudes).

---

### FRC: Verific Frontend Option

**Source:** ORFS #4088 (PR, merged)

Docker builds now support Verific as an alternative synthesis frontend.

**Action:** Support Verific as an alternative to Yosys in `orfs_flow`
when available.

---

## Tier 3: Future / Tracking

### FRC: GateSim (Built-in Gate-Level Simulator)

**Source:** OpenROAD #9882 (proposal/PoC)

Proposed `simulate_saif` Tcl command for built-in gate-level simulation
producing SAIF/VCD for power estimation without external simulators.
**Not yet implemented** in current OpenROAD source.

Currently, power estimation requires external VCD files via
`read_power_activities -vcd`. OpenROAD has sophisticated VCD parsing
and activity annotation in `src/sta/power/` but no simulation engine.

**Action:** Monitor. If implemented, could replace Verilator dependency
for power estimation flows.

---

### FRC: Immutable ODB with Command Journal

**Source:** OpenROAD #9854 (closed as RFQ, may resurface)

Embed a Tcl command journal in `.odb` files for reproducibility and
incremental replay. Could enable replaying from checkpoints instead
of full-stage reruns.

**Action:** Monitor. Good fit for Bazel's caching model if adopted.

---

### FRC: ML-Aware Macro Placement

**Source:** OpenROAD #9996

Proposed `-mode ml_aware` flag for RTLMP targeting SRAM-heavy and
structured designs (systolic arrays, tiled accelerators).

**Action:** Monitor for flow-level integration needs.

---

### FRC: DRT Access Pattern Awareness

**Source:** OpenROAD #9948

Proposes a persistent flow-graph oracle so DRT avoids invalid access
points during routing, reducing DRVs.

**Action:** Monitor. No flow-level changes needed unless new variables
are exposed.

---

### FRC: GPL Routing-Aware Timing

**Source:** OpenROAD #9364

Call global routing during timing-driven placement for better parasitic
estimation. Would change placement-routing interaction.

**Action:** Monitor for new flow variables or stage ordering changes.

---

### FRC: PDN Error Diagnostics

**Source:** OpenROAD #9934

Better PDN-0178/0179 channel repair messages: include why channel exists,
what was tried, and what user should change. Motivated by hierarchical
tensor accelerator designs.

**Action:** No flow changes needed. Improves debugging experience for
hierarchical designs in bazel-orfs.

---

### FRC: 3D IC Tooling

**Source:** OpenROAD #9447, #9381, #9412, #9516, #9585

Growing support for 3D integration: cuboid shapes, 3dblox checker,
underside iterm access, 3D GUI viewer markers.

**Action:** Long-term. Monitor for when 3D flow is mature enough for
bazel-orfs integration.

---

### FRC: slang Name Mangling

**Source:** ORFS #3774 (open, stale)

slang mangles module names during synthesis, breaking Tcl scripts that
map original to post-synthesis names. Relevant to hierarchical flow
support in bazel-orfs.

**Action:** Monitor. Needed for correct hierarchical synthesis with slang.

---

### FRC: Headless Operation

**Source:** ORFS commit 49167a7ad

Skip `save_images` on headless machines without DISPLAY. Prevents fatal
Qt platform plugin crashes.

**Action:** bazel-orfs already runs headless. Verify alignment with
upstream headless support.

---

## Build System / Infrastructure Notes

These are not FRCs but are relevant for bazel-orfs maintenance:

- **Bazel 8.6.0:** ORFS bumped .bazelversion (#4064). Track compatibility.
- **KLayout 0.30.7:** Updated with multi-platform checksums (ORFS commit befa85bac).
- **Ubuntu 26.04 / Debian 13:** Supported in OpenROAD (#9997). Keep containers aligned.
- **C++20 compilation:** Downstream projects must compile with C++20 (#9958).
- **swig from BCR:** Last WORKSPACE dependency removed (#9555).
- **tclreadline from BCR:** Simplifies MODULE.bazel (#9962).
- **test/orfs module isolation:** Moved to separate Bazel module (OR commit 1d63f8ce97).
  Reference architecture for bazel-orfs workspace structure.
