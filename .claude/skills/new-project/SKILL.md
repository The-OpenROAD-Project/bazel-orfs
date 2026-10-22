---
name: new-project
description: >-
  Bring a new design into a bazel-orfs workspace and through the flow: research the upstream
  project, pick the top module a hard macro would be, pin and fetch the RTL (a BCR rule set for
  generated Verilog), survey with hierarchical synthesis before deciding on macros, write a first
  orfs_flow with every optimisation off, then build stage by stage with a prediction and a check
  at each one, and write the design's README as present state. Also how to move a project to a
  newer upstream commit. Use when adding a design (XiangShan, a RISC-V core, an accelerator), when
  a first build of a new design is planned, or when upgrading a project's upstream pin.
---

> **Repo**: Applies to any workspace that uses bazel-orfs, bazel-orfs included. Paths are relative to the workspace root.

A new project is set up for early results and fast iterations: a placed design you can look at first, refinement afterwards. The steps below say what to decide and in what order; where another skill owns a step, it is named and not repeated.

ARGUMENTS: $ARGUMENTS

## 1. Research the project

- Find the upstream repository, its license, and the commit to pin (`gh api repos/<owner>/<repo>/commits/<branch> --jq .sha`). Pin a commit, never a branch.
- For anything more than a glance, clone it into `tmp/` and read it there; a local clone is faster and more complete than fetching files one by one.
- Find the synthesizable RTL (`rtl/`, `src/`, `hdl/`, `verilog/`), and whether it is generated (Chisel, Amaranth, SpinalHDL, ...).
- Note any results the authors report (frequency, area, process): the README compares against them later.

## 2. Pick the top module

Pick the module that would be a hard macro in a larger chip, not the SoC top: the core, tile or accelerator, without PLLs, pads, bus interconnect, debug ports or test harness. Examples: `BoomTile`, not `ChipTop`; `ibex_core`, not `ibex_top`; `cva6`, not `ariane_testharness`; for XiangShan, `XSTile`, whose interface is far narrower than `XSCore`'s.

If the design is too large to build in minutes, look for a small configuration of the same generator first and climb a ladder: minutes (5-10K cells), tens of minutes (50-100K), then the full design with the lessons applied (`no-paint-drying`).

## 3. Fetch the RTL

- Plain Verilog/SystemVerilog: an `http_archive` pinned to the commit, with a `build_file` that exposes the RTL as a `filegroup`. `http_archive`, not `git_repository`: no host git needed, and it caches and mirrors.
- Generated Verilog: search the Bazel Central Registry for a rule set for the generator before writing a `genrule` (Chisel: `rules_chisel`). Compile only the sources of the chosen module; skip the project's own build system, SoC glue and test harnesses.
- A design already in ORFS: in a bazel-orfs clone, `bazelisk run //:import` (the import rules in bazel-orfs's `docs/agent-rules.md`).
- When the upstream RTL needs a change to go through the flow, carry it as a patch on the `http_archive`, with a header saying what it fixes and how it retires. Patches and mocks are a plan: they become the upstream task list in the README. When the change is to the structure of the RTL rather than a bug, it is surgery (`surgery`).

## 4. Numbers first: survey before choosing macros

Do not guess the hierarchy; measure it. A first synthesis with `SYNTH_HIERARCHICAL=1` and memories mocked (`SYNTH_MOCK_LARGE_MEMORIES=1`) gives per-module cell counts in `synth_stat.txt` and the mocked memories in `synth_mocked_memories.txt`. Build with `--profile=tmp/<project>-profile.gz` to see which action is the tallest pole.

Which modules to harden, and the floorplan their interfaces dictate, is `macro-selection` (pins per micron in space, registered boundaries in time). Fitting several macros and the parent into the machine's memory is `scale-to-memory`.

## 5. The first flow

- `orfs_flow` with the top module, the RTL, and `pdk = "asap7"` (the fastest to iterate on).
- slang is the default frontend (`prefer-slang`). When slang rejects the RTL, the RTL is usually wrong: patch it rather than switch frontends.
- Every optimisation off for the first pass, a budget per stage, and through global route before refining anything: the `FAST_SETTINGS` dict in bazel-orfs's `examples/BUILD` and its table in `docs/performance.md`. Refine only while the route improves.
- Conservative floorplan to start: `CORE_UTILIZATION` 40, `PLACE_DENSITY` 0.65. Not too loose: a pathologically large die makes placement explode.
- `substeps = True` caches each substep's `.odb` as well, so a `dirty-lane` tree can start inside a stage while the design is under active development; leave it off on stable blocks to save cache.
- Constraints: source the platform's `constraints.sdc` first, then the clock. How boundary paths of a block are constrained is `macro-constraints`; there is no `set_input_delay` to write for a block.
- A hardened block is built as its own `orfs_flow` and given to the parent through `macros = [":<block>_generate_abstract"]`. `abstract_stage = "place"` while the parent's floorplan is being debugged; a later stage once timing matters.

Before changing a variable, look it up in the pinned ORFS's `flow/scripts/variables.yaml`: its stage says which cached stages it invalidates. A variable belongs in `user_arguments` only when your own scripts read it and ORFS does not.

## 6. Build stage by stage

Ask the human first: step by step (each substep shown and discussed), or unattended with monitoring (stop only on a problem). Either way, before every step longer than a few minutes, give an honest time estimate from data, or say there is none, and state a prediction of what the step will show; compare afterwards. Before any long run, ask whether a 30-second check answers the question first (`no-paint-drying`). Watch running stages instead of firing and forgetting, and say so when one is past its expected time.

What healthy looks like, per stage:

- **Synthesis**: cell count and hierarchy as surveyed; no unexpected latches or unmapped cells. More than about 100K cells flat means long placement and routing.
- **Floorplan**: utilization 30-50 %. A large WNS is normal before placement; what matters is whether repair makes progress.
- **Placement**: overflow falls towards 0 and HPWL settles. Overflow that oscillates or plateaus means density too high or die too small. With `GPL_ROUTABILITY_DRIVEN=0`, decide with the human whether to gamble on global route or redo placement routability-driven before an expensive route.
- **CTS**: skew and insertion delay; repair here is hold from skew.
- **Global route**: overflow must reach 0. Hotspots at macro edges want channels; uniform congestion wants a larger die or lower density.
- **Detailed route**: DRC count falls to 0 across iterations; a plateau usually means global route overflow was not really resolved.

When repair grinds at floorplan, CTS or global route, `repair-timing-grt` and `repair-headroom`; a `SETUP_SLACK_MARGIN` set from the observed WNS (about 10 % beyond it) stops a futile repair, never a round number. When a stage fails or needs a look inside, ask the database, not the log: `odb-debug` (macros, slivers, legality, worst paths, pictures). To iterate on a stage's settings or scripts in minutes, `dirty-lane`. For a crash, hang or wrong result in a tool, `openroad-debug`. After every stage, finished or failed, `warm-gui`.

Hierarchical builds are verified a level at a time before the next is built: block synthesis (cell count, module name), block placement (pin edges), block route (DRC clean), abstract (LEF has pins), parent floorplan (macro grid, channels), parent route (against the flat variant if there is one).

Known pitfalls:

- After synthesis, bus ports are bit-blasted (`io_in_0[3]`): IO constraints name bits, not buses.
- In Tcl on a hierarchical database, `ord::get_db_block`, not `[[[ord::get_db] getChip] getBlock]`.
- A geometry question needs only the database (`read_db`), not timing; loading the SDC and liberty for it wastes minutes and can fail on SDC problems.

## 7. The README

The design's README says what is, with numbers: what is built (top module, configuration, PDK), the hierarchy and why it was cut there, the stage results and the metrics that matter, how the authors' reported results compare, and the upstream task list the patches and mocks make. History goes into the PR bodies and `kpi.json`, not the README (`dogfooding`).

## 8. Moving to a newer upstream commit

1. Find the newest commit on the project's default branch; if it is the pinned one, stop.
2. Update the `http_archive`: URL, `strip_prefix` and `sha256` (or `integrity`).
3. Build synthesis first; when a carried patch no longer applies, rebase it onto the new source in a `tmp/` clone and regenerate it.
4. Rebuild through the flow (step 6) and update the README's numbers.
