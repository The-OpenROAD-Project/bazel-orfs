# Adding a Project to the OpenROAD Demo Gallery

This guide explains the strategy for adding a new project. The goal is to get
**early results with fast iterations** — a working placement screenshot in
minutes, not a perfect GDS in hours.

## Philosophy: Early Results, Fast Iterations

Adding a design to OpenROAD is an iterative process. Don't try to get everything
right on the first pass. Instead:

1. **Get synthesis working** — this catches 90% of integration issues
2. **Get a placement screenshot** — visual proof that the design is real
3. **Refine later** — tune settings, fix timing, improve density

Every setting defaults to **fast over correct**: mock memories, skip expensive
repair steps, disable timing-driven placement. This gets you through the flow
in minutes instead of hours. Once the design works end-to-end, selectively
remove the speed shortcuts.

## Step-by-Step Strategy

### 1. Pick the Right Module

The single most important decision. You want the **idiomatic hard macro** — the
core computational unit that makes sense as a block in a larger SoC.

**Do use:**
- The CPU core itself (e.g., `BoomTile`, `ibex_core`, `cva6`)
- The accelerator datapath (e.g., Gemmini's spatial array)
- The functional unit (e.g., vlsiffra's `multiplier`)

**Don't use:**
- SoC top-level with PLLs, pad rings, IO controllers
- Test harnesses or simulation wrappers
- Bus interconnects or memory controller wrappers

When in doubt, look at what the project's own documentation calls "the core."

### 2. Survey the Verilog Hierarchy

Before writing any Bazel config, understand what you're building:

```bash
python3 scripts/analyze_hierarchy.py path/to/rtl/
```

This shows:
- Module hierarchy tree with instance counts
- Large modules (>200 lines) — candidates for separate macro builds
- Repeated modules — likely SRAMs or datapath elements
- Memory-like modules detected by name patterns

For designs with **>50K cells**, plan hierarchical synthesis from day one.
Build SRAMs and repeated blocks as separate `demo_sram()` targets.

### 3. Start with the Speed Defaults

Every new project starts with two layers of settings that prioritize speed:

**GLOBAL_SETTINGS** — always on, correct behavior:
- `SYNTH_HDL_FRONTEND=slang` (much faster than Yosys for reading RTL)
- `OPENROAD_HIERARCHICAL=1` (enables hierarchical optimization)
- `SYNTH_REPEATABLE_BUILD=1` (deterministic builds)

**FAST_SETTINGS** — skip expensive steps for quick iteration:
- `GPL_TIMING_DRIVEN=0` / `GPL_ROUTABILITY_DRIVEN=0` (faster placement)
- `SKIP_CTS_REPAIR_TIMING=1` (skip hours of CTS repair)
- `SKIP_LAST_GASP=1` (skip final optimization pass)
- `FILL_CELLS=""` / `TAPCELL_TCL=""` (skip fill cells)
- `SYNTH_MOCK_LARGE_MEMORIES=1` (avoid memory synthesis bottleneck)

These are defined in [`defs.bzl`](../defs.bzl) and applied automatically by
the `demo_flow()` macro.

### 4. Get Synthesis Working First

```bash
bazel build //myproject:top_module_synth
```

This is your first milestone. If synthesis succeeds, you know:
- All Verilog files are found and parseable
- The top module is correctly identified
- Memory mocking is working (no synthesis hang)

If it fails:
- **slang parse error** → try `SYNTH_HDL_FRONTEND=yosys` as fallback
- **Missing module** → check that all RTL files are in `verilog_files`
- **Missing include** → add include paths or create a patch
- **Synthesis hangs** → ensure `SYNTH_MOCK_LARGE_MEMORIES=1` is set

Check the cell count in the synthesis log. If >50K cells, set up hierarchical
synthesis before going further.

### 5. Get a Placement Screenshot

Don't wait for routing. Placement is much faster and gives you the first
visual result for the gallery:

```bash
bazel build //myproject:top_module_gallery
```

This uses `demo_gallery_image()` targeting the `_place` stage. The screenshot
shows cell placement, macro positions, and gives a feel for the design's
density and structure.

Add it to the project's README immediately. Having an image — even from
placement — makes the PR reviewable.

### 6. Iterate Toward Routing

Once placement works, incrementally push further:

1. **Floorplan → Place**: Already done
2. **CTS**: Usually works if placement works. Check for clock issues.
3. **Global Route (GRT)**: First sign of congestion problems. If GRT fails,
   reduce `PLACE_DENSITY` or increase die area.
4. **Detailed Route**: May take longer but usually succeeds if GRT passes.
5. **Final/GDS**: The finish line.

At each stage, if something fails, use `/fix-errors` to diagnose and fix.
Don't try to get a perfect result — get a passing result first, then tune.

### 7. Remove Speed Shortcuts Gradually

Once the flow passes end-to-end, selectively re-enable quality steps:

```python
# In BUILD.bazel, override specific FAST_SETTINGS:
demo_flow(
    name = "top_module",
    fast = True,  # keep most fast settings
    arguments = {
        # Re-enable just the ones that matter:
        "GPL_TIMING_DRIVEN": "1",          # better timing
        "SKIP_CTS_REPAIR_TIMING": "0",     # fix clock skew
    },
    ...
)
```

Or switch to `fast = False` once the design is stable and you want production
quality results.

## Memory Strategy: From Mocked to Real

Most real designs contain SRAMs or register files. These dominate area, drive
floorplanning, and create the critical timing paths. Getting memories right is
a progression — start mocked, end real.

### Level 0: Mocked Inline (start here)

**Setting:** `SYNTH_MOCK_LARGE_MEMORIES=1`

Yosys replaces large memory arrays with simple logic approximations inline.
The memories don't have correct area or timing, but synthesis completes in
seconds instead of hanging. This is the default for all new projects.

```starlark
demo_flow(
    name = "top_module",
    arguments = {
        "SYNTH_MOCK_LARGE_MEMORIES": "1",  # default in demo_flow
    },
    ...
)
```

**What you get:** A design that synthesizes and places. The memory regions
appear as blobs of standard cells. Useful for proving the RTL is parseable
and getting a first screenshot.

**What you don't get:** Realistic area, timing, or floorplan. Memory cells
are scattered across the die instead of being in compact blocks.

### Level 1: Mocked Memory Macro Areas

**Setting:** `mock_area` parameter in `demo_sram()`

Extract memories into separate `demo_sram()` targets with `mock_area` scale
factors. The memories are still synthesized from behavioral RTL (no real SRAM
compiler), but they get their own placement regions with realistic area
estimates. This produces a much better floorplan.

```starlark
demo_sram(
    name = "tag_array_64x184",
    verilog_files = ["@project//:tag_array_64x184.sv"],
    mock_area = 0.62,  # scale factor for area estimation
    abstract_stage = "cts",
)

demo_hierarchical(
    name = "top_module",
    verilog_files = ["@project//:rtl"],
    macros = [":tag_array_64x184_generate_abstract"],
    ...
)
```

**What you get:** Realistic floorplan with memory macros placed as blocks.
The top module sees LEF/LIB abstracts for each memory, giving the placer
and router correct blockage information.

**What you don't get:** Correct timing through the memories. The behavioral
synthesis produces logic that doesn't match real SRAM read/write timing.

### Level 2: Correct Timing Path Endpoints

**Setting:** Proper SDC constraints on memory interfaces

Add timing constraints that model the real SRAM interface timing. Even though
the memory internals are still mocked, the paths *to and from* the memories
have correct setup/hold requirements. This makes timing reports meaningful
for the logic surrounding the memories.

```tcl
# In constraints-sram.sdc:
# Model the SRAM read latency as a single-cycle path
set_input_delay  [expr $clk_period * 0.3] -clock $clk_name [get_ports rd_data*]
set_output_delay [expr $clk_period * 0.2] -clock $clk_name [get_ports wr_data*]
```

The `demo_sram()` macro's `abstract_stage = "cts"` ensures that the generated
LEF/LIB has timing arcs that CTS and placement can use.

**What you get:** Meaningful timing reports for the logic between memories.
The critical paths through the datapath are now visible and optimizable.

**What you don't get:** Correct power numbers or silicon-accurate memory area.

### Level 3: Fake Memories with SRAM Compiler Models

**Setting:** Replace behavioral RTL with SRAM compiler-generated models

Use PDK-specific SRAM compiler outputs (Liberty timing models + LEF
abstracts) instead of synthesized behavioral RTL. The memories are
"fake" in that they don't have GDS, but their timing and area are
silicon-accurate.

This is where [megaboom](https://github.com/The-OpenROAD-Project/megaboom)
operates — behavioral mock SRAMs with carefully tuned `mock_area` factors
calibrated against real SRAM compiler output.

```starlark
demo_sram(
    name = "data_array_256x128",
    verilog_files = ["@project//:data_array_256x128.sv"],
    mock_area = 1.225,  # calibrated against SRAM compiler
    abstract_stage = "cts",
    arguments = {
        "CORE_UTILIZATION": "40",
        "CORE_ASPECT_RATIO": "0.47",
    },
)
```

**What you get:** Near-accurate area and timing. The design can be
meaningfully compared against the project's reported PPA numbers.

### Level 4: Real Memories

**Setting:** Actual SRAM compiler GDS/LEF/LIB

Replace mock SRAMs with real SRAM macro outputs from a memory compiler
(e.g., OpenRAM, SRAM22, or a foundry compiler). The memories have real
GDS, real timing, and real power models.

At this level, the memories may need to be combined into banks to match
the design's required configurations (e.g., combining 4x 256x32 SRAMs
into a 1024x32 bank, or using multiple narrow SRAMs to build a wide one).

```starlark
# Memory banking: combine physical SRAMs into logical memories
# The RTL instantiates a 1024x64 memory, but the SRAM compiler
# only provides 256x32 macros. Build a banking wrapper:
orfs_flow(
    name = "sram_bank_1024x64",
    verilog_files = [":sram_bank_wrapper.sv"],
    macros = [
        ":sram_256x32_generate_abstract",  # the real SRAM
    ],
    abstract_stage = "cts",
    ...
)
```

**What you get:** Silicon-accurate results. GDS-ready memory blocks.
Power numbers you can trust. This is the production target.

### Summary: Memory Maturity Ladder

| Level | Approach | Area | Timing | Effort |
|-------|----------|------|--------|--------|
| 0 | `SYNTH_MOCK_LARGE_MEMORIES=1` | Wrong | Wrong | Minutes |
| 1 | `demo_sram()` with `mock_area` | Approximate | Wrong | Hours |
| 2 | + correct SDC endpoints | Approximate | Paths correct | Hours |
| 3 | Calibrated mock areas | Near-accurate | Near-accurate | Days |
| 4 | Real SRAM compiler + banking | Correct | Correct | Days–weeks |

**Always start at Level 0.** Move up only when the current level is the
bottleneck for what you're trying to learn about the design.

## What Goes in This Repo

**Yes (just text):**
- `MODULE.bazel` entry — `http_archive` pointing to upstream
- `<project>/external.BUILD.bazel` — exposes RTL files from the archive
- `<project>/BUILD.bazel` — `demo_flow()` / `demo_sram()` / `demo_hierarchical()`
- `<project>/constraints.sdc` — sources platform defaults, adds project clocks
- `<project>/README.md` — blurb, build commands, results table
- `<project>/patches/*.patch` — fixes for upstream Verilog if needed

**No (never copied):**
- Source code from the upstream project
- Third-party dependencies
- Generated Verilog (use `genrule` to generate at build time)
- PDK files (come from the ORFS Docker image)

## Shared Macros

[`defs.bzl`](../defs.bzl) provides three macros that embed the gallery's
best practices:

| Macro | Use Case | Example |
|-------|----------|---------|
| `demo_flow()` | Simple flat design | vlsiffra multiplier |
| `demo_sram()` | Sub-macro (SRAM, regfile) | megaboom's `tag_array_64x184` |
| `demo_hierarchical()` | Top-level with macros | megaboom's `BoomTile` |

All three apply GLOBAL_SETTINGS + FAST_SETTINGS by default.

## Gallery Screenshots

Use `demo_gallery_image()` to generate `.webp` screenshots:

```starlark
load("//:gallery.bzl", "demo_gallery_image")

# Start with placement (fast)
demo_gallery_image(
    name = "top_module_gallery",
    src = ":top_module_place",
)

# Later, switch to routing (higher quality)
demo_gallery_image(
    name = "top_module_gallery",
    src = ":top_module_route",
)
```

The Tcl script ([`scripts/gallery_image.tcl`](../scripts/gallery_image.tcl))
renders a clean view: routing visible, power/ground hidden, fill cells hidden,
scale bar shown.

## Claude Skills

| Skill | What It Does |
|-------|-------------|
| `/demo-add <url>` | Full workflow: research → setup → synth → screenshot → README |
| `/demo-update <project>` | Refresh statistics and screenshots after a build |
| `/fix-errors` | Diagnose and fix build failures |
| `/bump-orfs` | Update the ORFS Docker image to latest |

These skills have been tuned while adding projects to the gallery, embedding
real experience with Bazel and OpenROAD into each one.
