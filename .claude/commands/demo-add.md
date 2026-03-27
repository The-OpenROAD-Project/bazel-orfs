> **Repo**: Run from the openroad-demo root.

Add a new demo project to the OpenROAD Demo Gallery.

Read `docs/adding-projects.md` for the full strategy and rationale.
The key principle: **early results, fast iterations** — get a working
placement screenshot first, refine later.

The user will provide either:
- A **GitHub URL** (e.g., `https://github.com/lowRISC/ibex`), or
- A **project name from the Upcoming table** in `README.md` (e.g., `SERV`, `Ibex`, `CVA6`)

## 0. Resolve the Project

If the argument is not a URL, look it up in the **Upcoming** table in `README.md`.
Match case-insensitively against the Project or Description columns. Extract the
GitHub URL from the Link column. If no match is found, ask the user for a URL.

After adding the project successfully, **remove its row from the Upcoming table**
and add it to the Projects table instead.

## 1. Research the Project

Use `bin/curl-read` for simple fetches and `bin/curl-read-python-head` when you
need to filter/extract JSON fields:

```bash
# Fetch README (first 100 lines)
bin/curl-read-python-head https://raw.githubusercontent.com/<owner>/<repo>/<branch>/README.md "data" 100

# Repo tree — extract paths matching a pattern
bin/curl-read-python-head \
  "https://api.github.com/repos/<owner>/<repo>/git/trees/<branch>?recursive=1" \
  "[e['path'] for e in json.loads(data).get('tree',[]) if e['path'].endswith('.v')]" 50

# Latest commit hash
bin/curl-read-python-head \
  "https://api.github.com/repos/<owner>/<repo>/commits?per_page=1" \
  "json.loads(data)[0]['sha']"
```

- Fetch the project's README and repo structure
- Find synthesizable Verilog/SystemVerilog RTL files
- Look in directories like: `rtl/`, `src/`, `hdl/`, `verilog/`, `gold/`
- Check if the project uses a generator (Chisel, Amaranth, SpinalHDL, etc.) that produces Verilog
- Note the project's license

## 2. Pick the Right Top-Level Module

**This is critical.** Do NOT use the SoC-level top module. Find the **idiomatic
macro** — the core computational unit that you would care to demonstrate in
OpenROAD and that makes sense as a hard macro within a larger SoC.

Exclude all SoC integration concerns:
- No PLLs, pad rings, IO controllers
- No bus interconnects, memory controllers, debug ports
- No test harness or simulation wrappers

Examples:
- **Berkeley BOOM**: use `BoomTile`, not `ChipTop` or `DigitalTop`
- **CoralNPU**: use the NPU core, not the SoC wrapper with peripherals
- **CVA6**: use `cva6` (the core), not `ariane_testharness`
- **Ibex**: use `ibex_core`, not `ibex_top`

## 3. Get Numbers First — Survey with Hierarchical Synthesis

**Don't guess — measure.** The strategy is:
1. **Mock all memories** (`SYNTH_MOCK_LARGE_MEMORIES=1`) so synthesis doesn't hang
2. **Keep all modules** (`SYNTH_HIERARCHICAL=1`, `SYNTH_MINIMUM_KEEP_SIZE=0`)
3. **Run synthesis** to get cell counts per module
4. **Then decide** what to build as separate macros

### Pre-synthesis RTL scan — ballpark the hierarchy

**Before running synthesis**, use `scripts/analyze_hierarchy.py` to scan the
Verilog and ballpark the design complexity. This is instant and tells you
whether you need macros before waiting for a potentially long synthesis run.

```bash
# Fetch the RTL and run the hierarchy scanner
bin/curl-read "<raw_verilog_url>" > /tmp/design.v
python3 scripts/analyze_hierarchy.py /tmp/design.v --top <module>
```

The script reports:
- Module hierarchy tree with line counts and instance counts
- Large modules (>200 lines) — candidates for separate macros
- Repeated modules (>2 instances) — likely SRAM/datapath elements
- Memory-like modules (by name pattern) — potential `demo_sram()` targets

**Decision rules from the scan:**
- **No modules >200 lines, no repeats >2x**: flat design, no macros needed
- **Repeated modules with >50 lines**: speculative `demo_sram()` candidates
- **Systolic arrays / PE arrays** — N×N grids of MAC units → definitely macros
- **SRAM banks** — any module with `sram`, `mem`, `ram`, `rf` in the name
- **Replicated compute units** — processing clusters, lanes, tiles
- **Large arithmetic** — multipliers, dividers, FPUs >200 lines

If the top module instantiates 4+ copies of something, or if a module
contains an N×N array of sub-instances, it's almost certainly worth
building as a separate macro speculatively. You can always flatten it
later if it turns out to be small.

Always start the BUILD.bazel arguments with:
```starlark
    arguments = {
        "SYNTH_HIERARCHICAL": "1",
        "SYNTH_MINIMUM_KEEP_SIZE": "0",
        "SYNTH_MOCK_LARGE_MEMORIES": "1",
        ...
    },
```

### Always use `--profile` and substeps

**Every** `bazelisk build` invocation should include `--profile=/tmp/profile.gz`.
This is free (negligible overhead) and gives you wall-time per action so you
can identify the tallest pole in the tent — the single action that determines
total build time.

```bash
bazelisk build //project:target_synth --profile=/tmp/profile.gz
# Then open in Chrome: chrome://tracing/ or https://ui.perfetto.dev/
```

If one module's ABC optimization dominates synthesis, break it out as a
`demo_sram()` macro so it synthesizes independently and caches.

**Always enable `substeps = True`** in `demo_flow()` / `demo_sram()` /
`demo_hierarchical()` calls. Substeps split each ORFS stage into individual
bazel actions, so the profile shows timing per substep (e.g., `1_1_yosys`,
`1_2_abc`, `2_1_floorplan`, `3_1_place`). Without substeps, each stage is
one opaque action and you can't tell what's slow inside it.

After synthesis completes, analyze module sizes:
```bash
bazelisk run //scripts:module_sizes -- \
  $(pwd)/bazel-bin/<project>/reports/asap7/<top_module>/base/synth_stat.txt
```

Use this data to decide:
- **Which modules to build as separate macros** (SRAMs, large repeated modules >5K cells)
- **Whether to increase SYNTH_MINIMUM_KEEP_SIZE** (e.g., keep only modules >1K cells)
- **Which modules to keep flat** (small modules, <1K cells)

Then set up hierarchical builds following the megaboom pattern
(https://github.com/The-OpenROAD-Project/megaboom):
- Large repeated modules → `demo_sram()` targets with `abstract_stage`
- Top module → `demo_hierarchical()` or `demo_flow()` with macros

Keep memories mocked until you know what you're dealing with. Refine later.

**IMPORTANT**: Do NOT update or modify other projects while working on a new one.
Focus only on the project being added.

## 4. Add http_archive to MODULE.bazel

- Pin to a specific commit hash (NEVER a branch name)
- Use `http_archive` (not `git_repository` — avoids system git dependency)
- Compute sha256 of the archive: `bin/curl-read <url> | sha256sum`
- Add `build_file = "//<project>:external.BUILD.bazel"` pointing to a local BUILD file
- If the project generates Verilog from Python/Chisel/etc., also add rules_python or rules_scala deps as needed

```starlark
http_archive(
    name = "<project>",
    build_file = "//<project>:external.BUILD.bazel",
    sha256 = "<sha256>",
    strip_prefix = "<project>-<commit>",
    urls = ["https://github.com/<owner>/<repo>/archive/<commit>.tar.gz"],
)
```

## 5. Create <project>/external.BUILD.bazel

Expose the Verilog files and any generator tools:

```starlark
filegroup(
    name = "rtl",
    srcs = glob(["rtl/*.v", "rtl/*.sv"]),
    visibility = ["//visibility:public"],
)
```

If the project uses a Python/Amaranth generator, create py_binary targets (see vlsiffra).

**If the project uses Chisel**, bypass the project's own build system (sbt, mill,
Chipyard, etc.) entirely. Use bazel-orfs's built-in Chisel rules to compile the
`.scala` source files directly, focusing only on the core accelerator/CPU module:

1. **Find the core Scala files** — look in `src/main/scala/` for the module you
   want to build. You don't need the full SoC or Chipyard integration.
2. **Use `chisel_library` and `chisel_verilog`** rules from bazel-orfs to compile
   only the relevant Scala sources to Verilog. See the megaboom example in bazel-orfs.
3. **Skip test harnesses, SoC wrappers, and Chipyard glue** — the goal is to get
   numbers, make policy decisions about the design, and display a demo, not build a chip.
4. **Pin the Scala sources** via `http_archive` just like any other project.

This approach avoids the complexity of Chipyard/sbt and lets Bazel manage the
Scala → Verilog → GDS pipeline end to end.

## 6. Create <project>/BUILD.bazel

Start with GLOBAL_SETTINGS and FAST_SETTINGS, then add project-specific settings.
See `vlsiffra/BUILD.bazel` as a minimal example and megaboom's BUILD.bazel for
hierarchical designs.

```starlark
load("@bazel-orfs//:openroad.bzl", "orfs_flow")

GLOBAL_SETTINGS = {
    "SYNTH_REPEATABLE_BUILD": "1",
    "SYNTH_HDL_FRONTEND": "slang",
    "SYNTH_SLANG_ARGS": "--disable-instance-caching=false",
    "OPENROAD_HIERARCHICAL": "1",
}

FAST_SETTINGS = {
    "FILL_CELLS": "",
    "SKIP_LAST_GASP": "1",
    "SKIP_REPORT_METRICS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_INCREMENTAL_REPAIR": "1",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_TIMING_DRIVEN": "0",
    "TAPCELL_TCL": "",
}

PROJECT_SETTINGS = {
    "CORE_UTILIZATION": "40",
    "PLACE_DENSITY": "0.65",
    "SYNTH_MOCK_LARGE_MEMORIES": "1",
}

orfs_flow(
    name = "<top_module>",
    verilog_files = ["@<project>//:<rtl_target>"],
    pdk = "asap7",
    arguments = GLOBAL_SETTINGS | FAST_SETTINGS | PROJECT_SETTINGS,
    sources = {
        "SDC_FILE": [":constraints.sdc"],
    },
)
```

### For hierarchical designs (following megaboom pattern):

```starlark
# 1. Build sub-macros (SRAMs, register files) as separate orfs_flow targets
orfs_flow(
    name = "<sram_module>",
    abstract_stage = "cts",  # generate abstract at CTS stage
    mock_area = 0.5,         # scale factor for mock area
    verilog_files = ["@<project>//:<sram_rtl>"],
    pdk = "asap7",
    arguments = GLOBAL_SETTINGS | FAST_SETTINGS | {
        "CORE_UTILIZATION": "40",
        "PLACE_DENSITY": "0.65",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    },
    sources = {"SDC_FILE": [":constraints-sram.sdc"]},
)

# 2. Build the top module with macros
orfs_flow(
    name = "<top_module>",
    verilog_files = ["@<project>//:<rtl_target>"],
    macros = [":<sram_module>_generate_abstract"],
    pdk = "asap7",
    arguments = GLOBAL_SETTINGS | FAST_SETTINGS | PROJECT_SETTINGS | {
        "SYNTH_HIERARCHICAL": "1",
        "MACRO_PLACE_HALO": "5 5",
        "PLACE_PINS_ARGS": "-annealing",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
    },
    sources = {"SDC_FILE": [":constraints.sdc"]},
)
```

### Key defaults to always start with:
- **PDK**: Always start with `asap7` — fastest, best supported
- **SYNTH_MOCK_LARGE_MEMORIES**: `"1"` — avoids memory synthesis issues
- **GPL_ROUTABILITY_DRIVEN**: `"0"` — faster placement
- **GPL_TIMING_DRIVEN**: `"0"` — faster placement
- **CORE_UTILIZATION**: `"40"` — conservative, room to breathe
- **PLACE_DENSITY**: `"0.65"` — conservative starting point

## 7. Create <project>/constraints.sdc

Always source the platform's standard constraints first, then add project-specific clocks:

```tcl
source $::env(PLATFORM_DIR)/constraints.sdc

current_design <top_module>

set clk_name  clk
set clk_port  [get_ports $clk_name]

create_clock -name $clk_name -period <period_ps> $clk_port

set non_clock_inputs [lsearch -inline -all -not -exact [all_inputs] $clk_port]

set_input_delay  50 -clock $clk_name $non_clock_inputs
set_output_delay 50 -clock $clk_name [all_outputs]

set_max_fanout 8 [current_design]
```

Choose clock period based on project's target frequency or a reasonable default (1000ps = 1 GHz for ASAP7).

## 8. Build Incrementally with /demo-debug

**Enable substep targets** by setting `substeps = True` in the project's `demo_flow()` call.
This generates per-substep targets for fast iteration (e.g.
`bazel run //<project>:<module>_place_3_4_place_resized`).

Use `/demo-debug <project>` to build incrementally through each stage (_synth → _route → _final),
fixing errors at each step. Trust the bazel cache — cached stages complete instantly.

After synthesis, check the log for:
- **Cell count**: If >50K cells, you MUST use hierarchical synthesis
- **Memory inference**: Are memories being inferred? If so, SYNTH_MOCK_LARGE_MEMORIES is working
- **Warnings/errors**: Fix any Verilog compatibility issues now
- **Module hierarchy**: Confirm which sub-modules are large

Record the synthesis statistics (cell count, area estimate) — these go into the README.

## 9. Generate Initial Gallery Screenshot

After synthesis passes, run through placement and generate a gallery screenshot.
**Start with placement, not routing** — it's much faster and gives a useful first image.

```starlark
# Add to <project>/BUILD.bazel:
load("//:gallery.bzl", "demo_gallery_image")

demo_gallery_image(
    name = "<top_module>_gallery",
    src = ":<top_module>_place",
)
```

```bash
bazel build //<project>:<top_module>_gallery
```

**Copy the image to `docs/`** so the README and gallery can reference it:

```bash
mkdir -p docs/<project>
cp bazel-bin/<project>/<top_module>_gallery.webp docs/<project>/place.webp
```

Once the design matures, switch the BUILD target to routing and update the copy:

```starlark
demo_gallery_image(
    name = "<top_module>_gallery",
    src = ":<top_module>_route",
)
```

```bash
bazel build //<project>:<top_module>_gallery
cp bazel-bin/<project>/<top_module>_gallery.webp docs/<project>/route.webp
```

## 10. Create <project>/README.md — REQUIRED

**Do not skip this step.** `/demo-update` depends on this file existing.
Use `serv/README.md` as a format reference. Include:

- Project description and link to upstream
- What this demo builds (top module, configuration, PDK)
- Hierarchy table (if hierarchical: level, module, PDN pins, metal budget)
- Reported vs. Actual results table (actual from synthesis stats, rest = TBD)
- **Future Improvements** section: analyze the patches you created and list
  specific improvements needed to clean them up. Mocks and patches look ugly
  but are gold for planning — they can be transformed into a concrete task list
  for the upstream project or your team.
- Build commands
- References (upstream repo, issues, PRs, papers)

## 11. Update Top-Level README.md

Add a row to the **Projects data table**:

```markdown
| [<project>](<project>/) | <description> | ASAP7 | <freq> | TBD | TBD | Building |
```

Also add the project to the **gallery image rows** below the data table.
Append to the last row (or start a new row if it has 5 entries):

```markdown
| [<project>](<project>/) |
|:--------:|
| [<img src="docs/<project>/route.webp" width="150">](<project>/) |
```

## Lessons Learned / Pitfalls

- **No source code copying**: Everything is fetched by Bazel. This repo stays tiny.
- **Pick the right top module**: The idiomatic hard macro, not the SoC wrapper. Exclude PLLs, pads, debug harnesses.
- **Pin commits**: Always use a specific commit hash in http_archive, never a branch.
- **http_archive > git_repository**: No system git dependency, supports mirrors and caching.
- **Find the right Verilog**: Look in `rtl/`, `src/`, `gold/` directories. Generated output dirs may not have synthesizable RTL — you may need to run a generator.
- **Start with FAST_SETTINGS**: Get through the flow first, optimize later.
- **Hierarchical synthesis from the start**: For any non-trivial design, use `SYNTH_HIERARCHICAL=1` and build SRAMs as separate macros. This dramatically reduces iteration time.
- **Module name must match**: The Verilog top module name must match the `name` parameter in orfs_flow (or use `top` to override).
- **Always use slang**: `SYNTH_HDL_FRONTEND=slang` is the default (set in `_GLOBAL_SETTINGS`). Never fall back to yosys — if slang reports errors, patch the upstream RTL to fix them. slang is stricter and catches real bugs (e.g., invalid hex literals like `32'hDDR4_0000`). Fixing the RTL is better than hiding problems behind a lenient parser.
- **Patches**: If upstream Verilog needs modifications for ORFS, create patch files in `<project>/patches/` and add `patches` to http_archive. Never modify source code.
- **Constraints pattern**: Always source `$::env(PLATFORM_DIR)/constraints.sdc` first for platform defaults.
- **Run synth first**: Always validate synthesis before investing time in floorplan/place/route.
- **Screenshot from placement first**: Use `demo_gallery_image` with `_place` stage initially for fast turnaround, switch to `_route` once the design is stable.
- **Chisel projects**: Write a generator in this repo to bypass arcane build systems (Chipyard, sbt). Pick reasonable default parameters. Include all `.scala` files, exclude ones with Rocket-Chip/TileLink deps. Patch for Chisel 7 compat.
- **Patches are a plan**: Mocks and patches created to get a design through the flow form a concrete task list. Analyze them to document specific upstream improvements needed in the project README's Future Improvements section.
- **No barstools/SRAM compilers**: Chipyard uses barstools for memory compilation; here we mock memories (`SYNTH_MOCK_LARGE_MEMORIES`) or build our own memory macros with `demo_sram()`. Never depend on Chipyard's memory infrastructure.
- **Full Chisel dep chains**: For projects deeply integrated with rocket-chip (like BOOM), compile the full dependency chain from source (cde → diplomacy → hardfloat → rocket-chip → project) rather than trying to exclude rocket-chip deps. Each library gets its own `http_archive` + `chisel_library` + Chisel 7 patch.
- **Never `bazelisk clean`**: Never run `bazelisk clean` or `clean --expunge` — it destroys the entire cache and leads to extremely long rebuild times. Instead, use cache poisoning (modify sha256/urls to force a specific re-fetch) or targeted `rm` of the specific repo dir under `.cache/bazel/`. Trust the cache.
- **Debug failed stages via fail ODB inspection**: When a stage fails, use the fail ODB to inspect the design state.
- **Know which variables invalidate which stage**: Before changing a variable, check `variables.yaml` in ORFS to see which stage it belongs to. Variables only invalidate their stage and downstream — e.g., `SETUP_SLACK_MARGIN` is a placement variable and won't invalidate synthesis cache, but `SDC_FILE` content changes invalidate everything from synth onward. The single source of truth is `upstream/OpenROAD-flow-scripts/flow/scripts/variables.yaml` (or the copy inside the Docker image at `external/bazel-orfs++orfs_repositories+docker_orfs/OpenROAD-flow-scripts/flow/scripts/variables.yaml`). Read it instead of guessing.
- **Add SSOT references to skills**: When referencing ORFS internals (variables, scripts, Tcl commands), always include the canonical file path so future readers can look it up directly rather than spelunking through the cache.
- **`sources` overrides `arguments` for the same key**: When `demo_sram` or `demo_hierarchical` sets a make variable like `PDN_TCL` in the base `arguments` dict (e.g., to a platform default), you can override it by providing the same key in the `sources` dict with a local file label (e.g., `"PDN_TCL": [":my-pdn.tcl"]`). The `sources` dict wins — no need to set `"PDN_TCL": ""` in arguments (which would cause a "couldn't read file" error).
- **Say when you're spelunking**: If you find yourself searching through bazel cache dirs, sandbox paths, or doing `find` across `.cache/bazel/` to locate a file, STOP and tell the user: "I'm spelunking through the cache to find X." The user likely knows the canonical location and can point you there directly. This saves time and produces a better SSOT reference for the skill.
- **Docker image by default**: All projects use OpenROAD from the Docker image — no from-source builds. Use `bazelisk run @bazel-orfs//:bump` to update. If a specific project hits an OpenROAD bug, it can build a patched OpenROAD from source and pass `openroad = "@openroad//:openroad"` in `orfs.default()`, but this is a project-specific workaround, not the default.
- **Gallery images hide power/ground**: All per-stage gallery scripts (`scripts/*_image.tcl`) hide power and ground nets for cleaner screenshots. The only exception is `floorplan_image.tcl`, which shows PDN intentionally. The generic fallback `gallery_image.tcl` also hides power/ground. Stage-to-script mapping is in `defs.bzl:_STAGE_SCRIPTS`.

## 12. Update This Skill

If you learn something new while adding this project, update this file
(`.claude/commands/demo-add.md`) with the lesson learned. This skill should
grow smarter over time.
