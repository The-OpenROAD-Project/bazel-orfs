> **Repo**: Run from the openroad-demo root. `bazelisk` needs the MODULE.bazel workspace.

Build a demo project incrementally through each ORFS stage, fixing errors at each step.

**Before starting**, clarify with the user what they want to achieve and how
much time they're willing to spend. Builds can take minutes to hours depending
on design size. Ask early to avoid wasting time on a strategy the user doesn't
want. If a user complains about something taking too long, suggest a narrowly
scoped skill or action to address it quickly.

**Start loose, tighten gradually.** Begin with relaxed PPA settings (large
die, low density, generous halos) and tighten through floorplan and
placement debugging. Don't go TOO loose — pathologically large dies can
cause placement to explode. After placement is working, be reluctant to
change floorplan parameters — each change invalidates the placement cache.

**Present a plan with visuals before each long step.** Before committing
to a stage that could take >5 minutes, show the user a plan with images
and data from the current state — congestion heatmaps, floorplan
screenshots, scaling plots, pin placement diagrams. Reference these in
your narrative: "Looking at the congestion heatmap [above], the M5
overflow is concentrated at the macro edges. I propose adding 5 µm X
halo to create routing channels." A visual plan lets the user course-
correct before spending time. In EDA, a small directional change early
saves hours later.

**Make predictions before every data point.** Before running a congestion
check, build step, or verification, state what you expect to see and why.
"I predict the M5 overflow will drop below 10K because the X halo created
routing channels — but M7 might stay high because the transposer is still
in the top-right corner." Then compare with results. This builds intuition
about the design and makes wait times productive.

**It isn't what you don't know — it's what you know for sure that just
ain't so.** Wrong assumptions are more dangerous than ignorance. Before
each fix attempt, identify your assumptions and write a test that
challenges the one you're least sure about. Example: "I assume only pad
cells have CLASS BLOCK" — write a test with a non-pad BLOCK macro and
see what happens. "I assume expanding the core rect won't shift strap
positions" — write a test with macros inside the core and verify output
is identical. A test that PASSES on master and constrains your fix
catches wrong assumptions before they cascade into 12 broken tests. The
most valuable test reduces your uncertainty the most, not confirms what
you already believe.

**Chat with the user while builds run.** Share interesting observations
about the design — surprising cell counts, congestion patterns, timing
paths. Ask what they think. Use build wait time for learning, not just
waiting.

**Annotate images with ad-hoc Python scripts.** When presenting heatmaps
or screenshots in `status.md`, generate small Python scripts (using
Pillow/matplotlib) to draw arrows, labels, bounding boxes, or overlays
on the images — e.g. "arrow pointing to congestion hotspot with label
'M5: 80K overflow'", or "box around the routing channel with dimension
annotation". These annotated images are more informative than raw
screenshots and help the user understand what they're looking at.

**Make annotations readable.** Scale font sizes and line widths relative
to the image dimensions — a 2000px image needs ~30-40px font, not 12px.
Use `ImageFont.truetype` with a size proportional to `min(W, H) / 40`.
Use contrasting colors (white text on dark backgrounds, black on light).
Draw a semi-transparent background box behind text labels for legibility.
Test by viewing the image at its display size, not zoomed in.

**Update `status.md` whenever something takes >2 minutes** and you think
the user is watching. Show intermediate results, images, and what's
happening so the user isn't staring at a blank screen.

**Maintain a `status.md` in the project directory.** After each ad-hoc
investigation (congestion check, pin verification, density heatmap),
update `status.md` with the image and findings. This lets the user see
progress visually and decide what to do next. Include: the image, what
the current configuration is, what you learned, and what you recommend
as the next step. Commit after each update so the user can view it.

**Document your reasoning in the project README.** Don't just record what
parameters you set — explain WHY. What is special about this design that
led to these choices? What did you try that didn't work? What did you
learn from congestion checks, scaling experiments, or timing analysis
that informed the configuration? Future readers (including Claude in the
next conversation) need the reasoning, not just the numbers.

**Be curious about the design at every step.** Invent small Tcl scripts
(via `orfs_run`) to probe the design state — pin positions, macro gaps,
congestion estimates, cell counts per region, timing paths, power grid
coverage. Each script takes seconds to write and run, and often reveals
something unexpected. Don't just run the flow and hope — actively
investigate what the tools produced before moving to the next stage.

**Manage expectations on running times.** Disappointment is mismanaged
expectations. Before every build step, give the user your best honest
estimate based on available data — `build_times.yaml`, similar designs,
cell count scaling. If you don't know, say "I don't have data for this"
rather than guessing optimistically. If a step is taking longer than
estimated, say so immediately. Only state facts — never invent numbers.

**Profile stuck processes.** If a step runs much longer than expected, use
`ps -p <pid> -o pcpu,etime,rss` to check CPU/time/memory, and
`eu-stack -p <pid>` or `gdb -batch -ex "thread apply all bt" -p <pid>`
to get a stack trace. This tells you what OpenROAD is actually doing —
e.g. stuck in annealing for pin placement, or in timing repair iterations.
The stack trace is proof of the problem and guides the fix (e.g. remove
`-annealing` from `PLACE_PINS_ARGS` for large designs).

**Watch logs while builds run.** Don't fire-and-forget. When a substep is
running, tail the log and look for signs of trouble: timing repair not
improving, placement overflow not converging, routing violations
plateauing, memory growing toward the machine limit. If it looks futile,
ask the user if they want to stop and try a different approach rather
than waiting hours for a predictable failure.

**Be nervous about long-running tasks.** Before any build >5 minutes, ask
yourself: "Is there a faster way to check if this will work?" Run congestion
checks, pin verification, module size analysis BEFORE committing to full
flows. Use substep targets and Tcl scripts for seconds-scale feedback
instead of full `bazelisk build`. When tempted to "just run it and see",
stop and think about what could go wrong — prefer the 30-second
investigation that saves a 3-hour build over optimism.

Trust the bazel cache — if a stage is already cached, it completes instantly.
Build each stage sequentially, fixing errors before proceeding to the next.

**NEVER run `bazelisk clean` or `bazel clean`** — this destroys hours of
cached build data across all projects. To force a rebuild of a specific
target, use cache poisoning: make a semantic change to an input file that
affects the target's hash. Adding a comment alone may not work — bazel
may canonicalize outputs and produce the same hash. Instead, change a
real parameter slightly (e.g. add a trivial `puts` to a Tcl script, or
change a numeric parameter by an insignificant amount like `0.650` to
`0.6500001`), rebuild, then change it back.

**Batch builds**: If you pass multiple targets to a single `bazelisk build`,
Bazel will run them in parallel where possible:

```bash
bazelisk build //serv:serv_rf_top_final //vlsiffra:multiplier_final
```

This is much faster than building one at a time. Use this when rebuilding
multiple projects from scratch or when generating images for all stages.

**IMPORTANT**:
- Do NOT build place, grt, or route stages for multiple projects in parallel —
  these are very resource intensive. Build one project at a time.
- Do NOT update or modify other projects unless the user explicitly asks.
  Focus only on the project specified in the arguments.
- **Always use substep targets** (`bazel run //<project>:<module>_<stage>_<substep>`)
  to run individual substeps, monitor output, and adjust parameters before
  committing to a full `bazelisk build`. Never run a full `bazelisk build`
  for a stage without first surveying it. Drop to `_deps` only when a substep
  fails and you need to debug inside the failure (see "When a substep fails").

The user will specify a project name and optionally a top module.

## Execution mode

After determining the top module and reviewing build times, **ask the user**:

> How would you like to run the flow?
>
> 1. **Step-by-step** — I run each substep one at a time, show you the output,
>    and we examine the logs together before moving on. Best for debugging or
>    first-time runs where things may get stuck.
>
> 2. **Autonomous with monitoring** — I run through the full flow myself,
>    using timeouts to detect stuck timing repair or placement overflow, and
>    only stop to ask you when I detect a problem. Best when the flow is
>    expected to work and you just want to be notified of issues.

In **step-by-step mode**, pause after each substep and show key output
(elapsed time, WNS, overflow, errors) before proceeding.

In **autonomous mode**, run substeps back-to-back, using timeouts on
timing-repair-heavy substeps (floorplan, CTS, GRT). Only stop and ask the
user when a problem is detected (stuck repair, placement overflow not
converging, errors).

**In both modes**, after each substep completes, provide a brief summary:
- Elapsed time vs. expected time
- Key metrics for that stage (overflow/HPWL for placement, WNS/TNS for
  timing stages, DRC violations for routing, etc.)
- Whether the result looks healthy or concerning, using EDA domain knowledge
- Any actionable warnings

## 0. Determine the top module, assess complexity, and review build times

Read `<project>/BUILD.bazel` to find the `demo_flow` target name — that is the top module.

Read `build_times.yaml` to get expected per-substep times for this project.
**Before running each substep, tell the user how long you expect it to take**
based on the recorded times. If the project is new and not in `build_times.yaml`,
use a similar-sized project as a rough guide.

Example: "Running `do-2_1_floorplan` — expected ~354s (~6 min) based on last build."

## Project configurations

Some designs support multiple configurations (e.g. different mesh sizes for a
systolic array). Configurations are separate project directories following the
naming convention `<project>_<variant>/` (e.g. `gemmini_4x4/`).

**How configurations work:**
- Each configuration is its own Bazel package with its own `BUILD.bazel`
- Configurations share the upstream source dependency (`@gemmini//:gemmini_lib`)
  and patches — only the generator parameters differ
- For Chisel projects, each configuration needs its own generator `.scala` file
  because `fir_library` does not support passing args to the generator
- The Verilog top module name may be the same across configurations (e.g. both
  `gemmini/` and `gemmini_4x4/` produce `MeshWithDelays`) — this is fine
  because they are in separate Bazel packages
- Each configuration is its own row in the projects table

**When to suggest a configuration variant:**
- A design takes too long to route (>2 hours) or OOMs on available hardware
- The design has a parameterized generator (Chisel, Amaranth) with a natural
  small configuration
- The small variant demonstrates the same architecture at a tractable scale
- Literature describes standard small/large configurations for the design

**Scaling strategy for large designs:**
If the full design takes many hours, create configurations at minutes / tens
of minutes / hours scales and progress through them. See
[PHILOSOPHY.md](../../PHILOSOPHY.md#scalable-rtl-is-a-prerequisite) for the
rationale. The operational steps:

1. Create the smallest configuration first (minutes scale, ~5-10K cells)
2. Build it through the full flow, apply lessons (slack margins, density)
3. Create a medium configuration (tens of minutes, ~50-100K cells)
4. Only then attempt the full design with all lessons applied

**Creating a configuration:**
1. Create `<project>_<variant>/` directory
2. Copy and modify the generator source with different parameters
3. Create `BUILD.bazel` reusing the same upstream deps
4. Copy `constraints.sdc` (same clock target initially)
5. Create minimal `README.md` linking back to the base project

## Fast feedback loops for hierarchical and abutted builds

When setting up hierarchical builds (macros, abutment), use a tight
verify-at-each-step loop. Don't build through route until each
intermediate step is verified.

**Verification approach:**
- Write Tcl verification scripts that check ODB state programmatically
- Run them via `orfs_run()` targets or `_deps` make interface
- Each script reports PASS/FAIL — no visual inspection needed

**Key lessons learned:**

1. **Pin constraints**: `set_io_pin_constraint -region` conflicts with
   `-mirrored_pins` (ODB-0026). Set the region on ONE direction only;
   the mirrored pair places the opposite side automatically.

2. **Verilog sharing**: Cross-package references work but need
   `visibility = ["//visibility:public"]` on the source target. Use the
   `.sv` genrule output (not `verilog_directory` or `verilog_single_file_library`
   which produce directories or library targets, not files).

3. **IO constraints**: `IO_CONSTRAINTS` is sourced during floorplan
   (`source_env_var_if_exists IO_CONSTRAINTS`). The constraints persist
   in the ODB and are used by `place_pins` during `3_2_place_iop`.

4. **Tcl compatibility**: OpenROAD's embedded Tcl may not support all
   Tcl 8.6 features (e.g. `lmap`). Use `for` loops and `lappend` instead.
   Test constraint files by checking the floorplan log for ODB warnings.

5. **Bus pin names**: After synthesis, bus ports are decomposed into
   individual bit pins (e.g. `io_in_a_0[0]` through `io_in_a_0[7]`).
   Use explicit bit-expanded names in IO constraints, not logical bus names.

6. **Clock and SDC for hierarchical**: When building macros with `demo_sram()`,
   the mocked synthesis (`SYNTH_GUT=1`) removes all registers. The platform
   `constraints.sdc` uses `[all_registers]` in `group_path` which fails on
   gutted designs (STA-0391). Verify the clock port name matches the actual
   Verilog port by using Grep to search for `input.*clock` in the Verilog file. If the
   mocked synth fails, the SDC may need guards around register-dependent
   constraints.

7. **Abstract stage selection**: Use `abstract_stage = "place"` on macros
   while debugging the floorplan — this is fastest and sufficient for
   verifying pin placement and macro grid alignment. Once the floorplan
   is working, switch to `abstract_stage = "grt"` for meaningful timing.
   There's no significant accuracy gain beyond GRT for timing, so
   `abstract_stage = "route"` is only needed for final DRC-clean results.

8. **Tcl script loading**: ORFS has two patterns for loading a design:
   - `load.tcl` — loads ODB + timing (SDC, liberty). Slow, needed for
     timing analysis, repair, CTS.
   - `open.tcl` — loads ODB only, no timing. Fast, sufficient for
     geometry queries (pin positions, macro placement, area, DRC).
   Use `read_db` (like `open.tcl`) in verification and image scripts
   that only need geometry. Don't load timing if you're just checking
   pin coordinates or macro positions — it wastes time and can fail
   on designs with SDC issues.

9. **Chesterton's fence**: Before removing or changing any ORFS parameter,
   BUILD.bazel setting, or Tcl script, understand why it was set that way.
   Check `variables.yaml` in bazel-orfs for per-stage variable routing —
   `sources` variables like `IO_CONSTRAINTS` are automatically distributed
   to the correct stage. Don't use `stage_sources` unless you have a
   specific reason to override the automatic routing.

   **Substep targets vs `_deps`**: Substep targets (`bazel run ..._<substep>`)
   are the primary iteration tool — one command, automatic dependency chain,
   change detection when BUILD.bazel is edited. `_deps` is a fallback for
   when you need the full Make environment (see "When a substep fails" and
   "Running ad-hoc Tcl scripts" sections below).

   **`_deps` is a local work folder with no dependency management** — unlike
   bazel, it doesn't track which files changed. If you modify BUILD.bazel
   parameters (sources, arguments), you must re-run `bazelisk run ..._deps`
   to rebuild the stage from bazel cache with the new settings. Editing
   Tcl files in the project directory IS picked up immediately by `_deps`
   because the Tcl is sourced at runtime.

10. **Hacking Tcl files with `_deps`**: When iterating on Tcl scripts
   (IO constraints, macro placement, verification), use `_deps` for fast
   turnaround. Edit the Tcl file in the project directory, then re-run
   only the affected substep via `tmp/<project>/<module>_<stage>_deps/make
   do-<substep>`. No need to rebuild from scratch — `_deps` picks up file
   changes immediately. This gives seconds-to-minutes iteration instead of
   minutes-to-hours through full `bazelisk build`.

9. **Early congestion check after placement**: Run `congestion_check.tcl`
   (via `orfs_run`) after global placement to estimate routing congestion
   BEFORE committing to CTS/GRT/route. The script runs
   `global_route -congestion_iterations 0`, generates a congestion heatmap
   image, and reports overflow per layer.

   **What to look for in the heatmap:**
   - Red/dark areas = severe congestion — routing will fail
   - Green/cyan = healthy
   - Congestion at macro boundaries = need more halo space
   - Congestion uniform across die = die too small

   **Adjustments (cheapest first, re-run check after each):**
   - Increase `MACRO_PLACE_HALO` X (0→2→5 µm)
   - Lower `PLACE_DENSITY`
   - Increase die area
   - Enable `GPL_ROUTABILITY_DRIVEN=1`

10. **Debugging failed stages**: When a substep fails, drop to `_deps`
    (see "When a substep fails" section) and look for `*fail*.odb` in the
    results directory. Load it with `read_db` in a Tcl script and investigate:
   - Enumerate DRC errors (`check_drc`, marker databases)
   - Check placement density (`report_design_area`)
   - Look at congestion hotspots
   - Screenshot the failed state for the README
   - Read the log for the specific error message and context
   Focus on understanding **what specifically** needs fixing, not just
   that it failed. A screenshot of the failure state is often more
   informative than the error message alone.

10. **Build order for hierarchical**: Verify at each step before proceeding:
   - Macro synth → check cell count, module name correct
   - Macro place → verify pin edges via Tcl script
   - Macro route → verify DRC clean
   - Macro abstract → verify LEF has pins
   - Top floorplan → verify macro grid and abutment gaps
   - Top route → compare timing/area with flat variant

## Using EDA domain knowledge

Apply general EDA/physical design knowledge to judge what to expect at each
stage and whether output looks healthy:

- **Synthesis**: Check cell count and hierarchy. Designs with >100k cells are
  large; expect long placement and routing. Watch for unmapped cells or
  unexpected latches — these indicate RTL issues.
- **Floorplan**: Utilization 30-50% is typical. >60% will cause placement
  and routing congestion. WNS at floorplan is often large (paths aren't
  optimized yet) — this is expected, not alarming. What matters is whether
  timing repair is making progress or spinning.
- **Placement**: Overflow should decrease monotonically toward 0. HPWL should
  stabilize. If overflow oscillates or plateaus, the placement density is too
  high or die area too small. The number of placement iterations correlates
  with cell count — a 100k-cell design may need 300+ iterations.
- **CTS**: Clock skew and insertion delay are the key metrics. Timing repair
  here targets hold violations from clock skew. Large designs with many
  clock sinks will have longer CTS runs.
- **GRT**: Overflow must reach 0 for routing to succeed. Congestion hotspots
  indicate too-aggressive utilization or missing routing layers.
- **Detailed routing**: DRC violations should decrease to 0 across iterations.
  Persistent violations often mean GRT overflow wasn't fully resolved or
  routing resources are exhausted.
- **Final**: Mostly reporting. Check final WNS/TNS, DRC count, and area.

Use this knowledge to contextualize what you see in logs — don't just report
numbers, explain whether they look healthy or concerning for the design size
and complexity.

## Prerequisites

**Check `upstream/` before spelunking.** Upstream project repos may be
cloned into `upstream/` (e.g. `upstream/OpenROAD-flow-scripts`,
`upstream/coralnpu`). Always check there first when you need to:
- Read upstream source code or documentation
- Search for module definitions, port names, or architecture details
- Check git history for why something was done a certain way
- Generate patches against the upstream repo
- **Debug errors** — read OpenROAD source code in
  `upstream/OpenROAD-flow-scripts/tools/OpenROAD/src/` to understand
  what an error message means, what conditions trigger it, and what
  the fix might be
- **Understand ORFS flow** — read the Tcl scripts in
  `upstream/OpenROAD-flow-scripts/flow/scripts/` to understand what
  each stage does and how variables are used
- **Find tools** — `whittle.py` for minimizing test cases, other
  utilities in `tools/OpenROAD/etc/`

Reading a local clone is instant; fetching from GitHub is slow and lossy.
If an important upstream repo is NOT in `upstream/`, suggest to the user:
"Want me to clone `<repo>` into `upstream/` for faster access?"

**Use serv for fast smoke-testing.** When testing new procedures, verifying
workflow changes, or validating that a bazel-orfs bump didn't break anything,
use `//serv:serv_rf_top` — it's small (~2K cells), completes synth-to-route
in minutes, and exercises the full flow. Don't use large designs like
coralnpu or gemmini for validation that doesn't require their complexity.

The `_deps` local flow installs into `tmp/` under the workspace root.
Ensure `tmp/` is in `.gitignore` and `tmp` is in `.bazelignore`.

## General workflow for every stage

Every stage follows the same pattern using **substep targets**:

1. **Run substeps one at a time**: `bazel run //<project>:<top_module>_<stage>_<substep>`
   - This builds all prerequisites automatically (previous stages from cache),
     then runs the specified substep. No manual dependency management needed.
   - Substeps must be run **in order** as defined by ORFS (e.g. `3_1_...`
     before `3_2_...`). Each substep depends on the output of the previous one.
   - **Requires `substeps = True`** in the project's `demo_flow()` call.
2. **Monitor output** — look for excessive timing repair, stuck iterations, errors
3. **Adjust BUILD.bazel** if needed (slack margins, density, etc.)
4. **Re-run the same substep command** — it auto-detects BUILD changes
5. **Once all substeps pass**, run `bazelisk build //<project>:<top_module>_<stage>`
   - This runs the full stage from scratch in bazel's sandbox. It produces
     the cached artifact for the next stage.

### When a substep fails — drop to `_deps`

Substep targets run in Bazel's sandbox. When they fail, the sandbox is
cleaned up and you can't inspect the failed state. To debug a failure:

1. **Deploy `_deps`**: `bazelisk run //<project>:<top_module>_<stage>_deps`
   - Installs a local working copy in `tmp/`. Expected time: roughly the
     build time of the previous stage (re-runs it from cache).
2. **Reproduce the failure**: `tmp/<project>/<top_module>_<stage>_deps/make do-<failing_substep>`
3. **Inspect the failed state**:
   - Look for `*fail*.odb` in the results directory
   - Run ad-hoc Tcl scripts: `tmp/<project>/<top_module>_<stage>_deps/make run RUN_SCRIPT=/path/to/script.tcl`
   - Generate a bug reproducer: `tmp/<project>/<top_module>_<stage>_deps/make <script>_issue`
     (e.g. `make global_place_issue`, `make cts_issue`) — creates a tar archive
     with all files needed to reproduce the bug for upstream reporting
4. **Fix and re-run** until the substep passes
5. **Go back to substep targets** for the remaining substeps

### Running ad-hoc Tcl scripts

Use `_deps` + `make run` to run arbitrary Tcl (or Python) scripts against
a stage's ODB with the full ORFS environment loaded:

```bash
tmp/<project>/<top_module>_<stage>_deps/make run RUN_SCRIPT=/absolute/path/to/script.tcl
```

This loads the stage's ODB and sources your script. The script has access
to all ORFS env vars (`$::env(RESULTS_DIR)`, `$::env(SCRIPTS_DIR)`, etc.).
Output goes to `tmp/<project>/<top_module>_<stage>_deps/logs/<stage>/run.log`.

Useful for:
- Probing design state (cell counts, pin positions, congestion estimates)
- Generating custom reports or screenshots
- Testing Tcl snippets before wiring them into `orfs_run()` targets

For **reusable** Tcl scripts that produce outputs needed by the flow, use
`orfs_run()` in BUILD.bazel instead — this integrates with Bazel's
dependency tracking. `make run` is for **ad-hoc exploration**.

Python scripts are also supported (detected by `.py` extension):
`make run RUN_SCRIPT=/path/to/script.py`

## Monitoring timing repair (applies to floorplan, CTS, GRT)

**Do NOT use `timeout` to sample substeps** — this kills the process and
leaves incomplete state. Instead:

1. **Before running**, check BUILD.bazel for `SKIP_CTS_REPAIR_TIMING`,
   `SKIP_INCREMENTAL_REPAIR`, and `SETUP_SLACK_MARGIN`. If repair is already
   skipped or the margin covers the expected WNS, just run directly.

2. **When timing repair IS enabled and could be problematic**, run the substep
   target in the background, then find and monitor the active log:

   ```bash
   # Run substep in background
   bazel run //<project>:<top_module>_<stage>_<substep>
   # Find the active log file
   ps -Af | grep '[t]ee.*\.log'
   # Then tail the log to monitor progress
   ```

   If using `_deps` instead (for debugging), logs are in the local `tmp/` directory:
   ```bash
   tail -30 tmp/<project>/<top_module>_<stage>_deps/_main/<project>/logs/asap7/<top_module>/base/<substep>.log
   ```

3. **Look at the `repair_timing` iteration table** in the log. Key columns:
   - **Iter** — iteration count
   - **WNS** — worst negative slack (ps). More negative = worse.
   - **TNS** — total negative slack

4. **Signs of excessive/futile timing repair:**
   - WNS is flat across many iterations (not improving)
   - WNS is very large (e.g. -500ps or worse)
   - Iteration count is climbing past 200+ with no WNS improvement

5. **When you detect excessive timing repair**, report progress to the user
   and ask whether to continue or stop:

   > Timing repair has been running for X minutes. WNS is **Y ps** and not
   > improving after Z iterations. Should I let it continue, or stop and
   > adjust? Options:
   >
   > 1. **Adjust `SETUP_SLACK_MARGIN`** — set it to slightly beyond the WNS
   >    (e.g. WNS is -1007ps → set `SETUP_SLACK_MARGIN` to `"-1100"`). This
   >    tells the tool to accept the current slack and skip futile repair.
   >
   > 2. **Relax the clock period** — increase the clock period in the SDC
   >    file to give the design more timing budget.
   >
   > Suggested `SETUP_SLACK_MARGIN`: round WNS down by ~10% (e.g. WNS -1007
   > → margin `"-1100"`, WNS -500 → margin `"-550"`).

6. **Never stop a substep without asking the user first.** Always explain
   what you're seeing and let them decide.

Use `make print-FOO` via `_deps` to inspect any ORFS variable (not available
via substep targets — use `_deps` for variable inspection):
```bash
tmp/<project>/<top_module>_<stage>_deps/make print-SETUP_SLACK_MARGIN
tmp/<project>/<top_module>_<stage>_deps/make print-HOLD_SLACK_MARGIN
tmp/<project>/<top_module>_<stage>_deps/make print-CORE_UTILIZATION
```

## 1. Synthesis (_synth)

Synth does not have substep targets (it uses Yosys, not OpenROAD). Run it
directly or use `_deps` for debugging:

```bash
# Direct build (recommended):
bazelisk build //<project>:<top_module>_synth

# Or via _deps for debugging:
bazelisk run //<project>:<top_module>_synth_deps
tmp/<project>/<top_module>_synth_deps/make do-yosys-canonicalize
tmp/<project>/<top_module>_synth_deps/make do-yosys
tmp/<project>/<top_module>_synth_deps/make do-1_synth
```

- If slang fails on an unsupported construct, try `"SYNTH_HDL_FRONTEND": ""` (native yosys).
- If the upstream Verilog itself has an error or incompatibility, **create a patch**:
  1. Download the file: `curl -sL <github-raw-url> > /tmp/original.v`
  2. Edit the copy to fix the issue
  3. Generate a patch: `diff -u /tmp/original.v /tmp/fixed.v > <project>/patches/fix_description.patch`
  4. Add patches to `http_archive` in `MODULE.bazel`
- Check output for warnings (unmapped cells, latches inferred unexpectedly).

## 2. Floorplan (_floorplan)

**`2_1_floorplan` includes timing repair.** Check if `SETUP_SLACK_MARGIN`
already covers the expected WNS. If not, run the substep and monitor the log
for excessive repair (see "Monitoring timing repair" section).

```bash
bazel run //<project>:<top_module>_floorplan_2_1_floorplan
bazel run //<project>:<top_module>_floorplan_2_2_floorplan_macro
bazel run //<project>:<top_module>_floorplan_2_3_floorplan_tapcell
bazel run //<project>:<top_module>_floorplan_2_4_floorplan_pdn
```

- If die area is too small, adjust `CORE_UTILIZATION` (try 30-50) and `PLACE_DENSITY` (try 0.4-0.7).
- Then run: `bazelisk build //<project>:<top_module>_floorplan`

## 3. Placement (_place)

```bash
bazel run //<project>:<top_module>_place_3_1_place_gp_skip_io
```

Watch overflow decreasing toward 0 and HPWL stabilizing. If overflow is stuck
high after hundreds of iterations, kill and adjust `PLACE_DENSITY` or
`CORE_UTILIZATION`.

```bash
bazel run //<project>:<top_module>_place_3_2_place_iop
bazel run //<project>:<top_module>_place_3_3_place_gp
```

Same monitoring — watch overflow converge to 0.

```bash
bazel run //<project>:<top_module>_place_3_4_place_resized
bazel run //<project>:<top_module>_place_3_5_place_dp
```

- Lower `PLACE_DENSITY` gives more room; lower `CORE_UTILIZATION` gives a bigger die.
- Then run: `bazelisk build //<project>:<top_module>_place`

**After placement: ask about routability.** If `GPL_ROUTABILITY_DRIVEN=0`
(the speed default), placement finished fast but may have created routing
congestion. Before committing to CTS/GRT (which is expensive), ask the user:

> Placement finished in X min with `GPL_ROUTABILITY_DRIVEN=0`. We have a
> choice:
>
> 1. **Go for it** — proceed to CTS/GRT and see if routing converges.
>    If GRT has low overflow, we saved time. If it fails, we redo placement
>    (~X min) with routability driven on plus GRT (~Y min) — total cost
>    of the wrong bet is X+Y min.
>
> 2. **Play it safe** — redo placement with `GPL_ROUTABILITY_DRIVEN=1` now.
>    Placement will be slower but GRT is more likely to succeed first try.
>
> For small designs (<50K cells), option 1 is usually fine. For larger
> designs, the GRT gamble can cost hours.

## 4. Clock Tree Synthesis (_cts)

**`4_1_cts` includes timing repair** — but only if `SKIP_CTS_REPAIR_TIMING`
is not set. Check BUILD.bazel first:
- If `SKIP_CTS_REPAIR_TIMING=1` is set, run directly.
- If NOT set, run and monitor the log for excessive repair (see "Monitoring
  timing repair" section).

CTS has only one substep, so just build the stage directly:

```bash
bazelisk build //<project>:<top_module>_cts
```

## 5. Global Routing (_grt)

**`5_1_grt` includes timing repair** — but only if `SKIP_INCREMENTAL_REPAIR`
is not set. Check BUILD.bazel first:
- If `SKIP_INCREMENTAL_REPAIR=1` is set, run directly.
- If NOT set, run and monitor the log for excessive repair (see "Monitoring
  timing repair" section).

GRT has only one substep, so just build the stage directly:

```bash
bazelisk build //<project>:<top_module>_grt
```

Watch overflow decreasing to 0. If congestion: reduce `PLACE_DENSITY`,
enable `GPL_ROUTABILITY_DRIVEN=1`, or increase die area.

## 6. Detailed Routing (_route)

```bash
bazel run //<project>:<top_module>_route_5_2_route
```

Watch DRC violations decreasing: `1523 → 892 → 412 → 0`. If violations
plateau, check `MIN_ROUTING_LAYER` and `MAX_ROUTING_LAYER`.

```bash
bazel run //<project>:<top_module>_route_5_3_fillcell
```

- Then run: `bazelisk build //<project>:<top_module>_route`

## 7. Final (_final)

```bash
bazel run //<project>:<top_module>_final_6_1_merge
bazel run //<project>:<top_module>_final_6_report
```

- Then run: `bazelisk build //<project>:<top_module>_final`
- If it succeeds, the full flow is complete.

## Monitoring logs in real-time

When running substep targets or `bazelisk build`, find active logs with:
```bash
ps -Af | grep '[t]ee.*\.log'
```

When running via `_deps`, logs are in the local `tmp/` directory and persist:
```bash
tail -f tmp/<project>/<top_module>_<stage>_deps/logs/<log_file>.log
```

## Extracting metrics after completion

```bash
bazelisk run //scripts:extract_metrics -- \
  $(pwd)/bazel-bin/<project>/logs/asap7/<top_module>/base \
  $(pwd)/bazel-bin/<project>/reports/asap7/<top_module>/base
```

## ORFS variables reference

Print any ORFS variable using `make print-FOO` via `_deps` (not available
via substep targets):

```bash
tmp/<project>/<top_module>_<stage>_deps/make print-SETUP_SLACK_MARGIN
tmp/<project>/<top_module>_<stage>_deps/make print-CORE_UTILIZATION
```

Key variables to try when fixing issues:
- `SETUP_SLACK_MARGIN` / `HOLD_SLACK_MARGIN` — terminate timing repair early (floorplan, cts, grt)
- `PLACE_DENSITY` / `CORE_UTILIZATION` — floorplan/placement tuning
- `GPL_ROUTABILITY_DRIVEN` / `GPL_TIMING_DRIVEN` — placement quality vs speed
- `SYNTH_HIERARCHICAL` / `SYNTH_MINIMUM_KEEP_SIZE` — hierarchical synthesis control
- `SKIP_CTS_REPAIR_TIMING` / `SKIP_INCREMENTAL_REPAIR` — timing optimization toggles
- `REMOVE_ABC_BUFFERS` — skip buffer optimization in floorplan (deprecated but effective)
- `MIN_ROUTING_LAYER` / `MAX_ROUTING_LAYER` — routing layer control

## Common pitfalls (lessons learned)

**Variables not exported to Tcl in `_deps`**: The `.short.mk` only exports
variables explicitly set in BUILD.bazel `arguments`. ORFS defaults like
`CORE_ASPECT_RATIO` are set by the Makefile but NOT exported as env vars
for Tcl scripts. If floorplan.tcl fails with `can't read ::env(FOO)`, add
the variable to `arguments` explicitly. Known examples:
- `CORE_ASPECT_RATIO` — defaults to 1, not exported
- `CORE_MARGIN` — defaults to 1.0, but BLOCKS_grid_strategy PDN needs ≥2
  (PDN-0351: "PDN rings do not fit inside the die area")
- `KEEP_VARS` — set to `"1"` when using `SYNTH_NETLIST_FILES` to skip
  `erase_non_stage_variables` which fails without PyYAML in `_deps`

**SETUP_SLACK_MARGIN must exceed actual WNS**: Don't pick a round number
like `-1100` — first run `do-2_1_floorplan`, observe the actual WNS from
the repair_timing table, then set the margin 10% beyond. Example: WNS is
-7800ps → set margin to `-8600`. If the margin is tighter than the WNS,
timing repair spins indefinitely.

**Hierarchical ODB Tcl API**: Use `ord::get_db_block` for hierarchical
designs. The pattern `[[[ord::get_db] getChip] getBlock]` returns NULL
for hier ODBs because `getChip` fails.

## Upgrading bazel-orfs

If a build issue might be a bazel-orfs or ORFS bug, upgrade to the latest:

```bash
bazelisk run @bazel-orfs//:bump
```

## Collect outputs after each successful stage

After each stage's `bazelisk build` succeeds, collect logs, metrics, and
reports into the project folder:

```bash
bazelisk run //scripts:collect_stage_outputs -- <project>
```

This copies all available outputs (logs, JSON metrics, reports) into
`<project>/logs/`, `<project>/metrics/`, and `<project>/reports/`. The files
are small (typically <1 MB total) and designed to be committed to git as a
lightweight lab log that Claude can read directly in future conversations.

The script makes all collected files read-write (bazel outputs are read-only
by default). This allows re-collection and manual editing.

**Do not filter empty files** — empty logs and reports are valuable information.
An empty `5_route_drc.rpt` means zero DRC violations (clean routing). An empty
`6_1_merge.log` means klayout never ran (a bug). An empty
`synth_mocked_memories.txt` means no memories were mocked. The absence of
content is itself data.

**Do not gitignore these files** — they are the primary data artifact of the
build, capturing the result of one-off trials with the specific versions of
bazel-orfs, OpenROAD, and ORFS at the time. The git log makes them
reproducible.

## Generate stage images

After each stage's `bazelisk build` succeeds, generate a gallery image:

```bash
bazelisk build //<project>:<top_module>_<stage>_gallery
```

Stage-specific images show how the design evolves through the flow — empty
die at floorplan, placed cells, clock tree, routing congestion, final routed
design. Store images in `<project>/images/` and reference them in the README.

If a `_gallery` target doesn't exist for a stage, the default
`demo_gallery_image` targeting `_route` is sufficient for most projects.

## When a stage takes too long

If a stage exceeds practical time limits (e.g. detail routing taking 6+ hours)
or OOMs repeatedly, **do not keep retrying**. Instead:

1. **Record what happened** — update the README with how far the build got,
   what the bottleneck was (time, memory, or both), and what was tried
2. **Collect outputs** — run `collect_stage_outputs` for whatever completed
3. **Update build_times.yaml** — record the incomplete stage with a note
4. **Update the status** — mark the project as incomplete with a clear
   description of what blocks completion (e.g. "detail routing requires
   64 GB RAM, only 30 GB available")
5. **Suggest alternatives** — document what could be changed to make it
   feasible (reduce threads, lower utilization, use a bigger machine, etc.)

The project's value is in the data collected through the stages that did
complete, not in forcing every design to finish. An incomplete build with
good documentation is more useful than a complete build with no notes.

## Analyze design for hierarchical decomposition

When a stage takes too long or uses too much memory, the root cause is often
that a large flat design should be built hierarchically. After synthesis
completes, analyze the design structure to identify macro candidates:

### What to look for

1. **Repeating tile structures** — systolic arrays, mesh networks, multi-core
   CPUs. If the design has N identical instances of a module (e.g. 256 PEs in
   a 16x16 mesh, 4 CPU cores in an SoC), each instance is a natural macro.
   Tiled designs can use **routing by abutment** — macros placed adjacent with
   matching pin patterns, eliminating top-level routing between tiles.

2. **Large memories** — SRAMs, register files, FIFOs, content-addressable
   memories (CAMs/TCAMs). These are well-studied in literature and benefit
   enormously from being built as hard macros with optimized bitcell layouts.
   Look for `mem_*`, `rf_*`, `fifo_*`, `cam_*` in the module hierarchy. ORFS
   `SYNTH_MOCK_LARGE_MEMORIES` already identifies these — check
   `synth_mocked_memories.txt` in reports.

3. **Functional units** — ALUs, multipliers, FPUs, crypto blocks. These are
   compute-dense and often have well-defined interfaces. If a functional unit
   appears multiple times or is large enough to dominate a stage, consider
   building it as a macro.

4. **Known architectural patterns** — use domain knowledge to identify
   structures from literature:
   - **Processor cores**: RISC-V cores (Rocket, BOOM) are designed for tiling
   - **Accelerator PEs**: ML accelerators (Gemmini, NVDLA) have regular PE arrays
   - **Network-on-chip routers**: regular grid topology, ideal for abutment
   - **Cache banks**: identical SRAM arrays with tag/data split

### How to analyze

Run `//scripts:module_sizes` after synthesis to get the hierarchy with cell
counts. Look for:
- Modules with >10K cells that appear multiple times → macro candidate
- A single module consuming >50% of total cells → break it down further
- Modules with names suggesting regularity (array, tile, bank, lane, pe, core)

```bash
bazelisk run //scripts:module_sizes -- \
  $(pwd)/bazel-bin/<project>/reports/asap7/<top_module>/base/synth_stat.txt
```

### Impact on build time and memory

Building macros separately has compounding benefits:
- **Placement/routing scales super-linearly** with cell count. A 900K-cell
  flat design may take 6 hours to route; four 225K-cell macros may take
  45 minutes each (3 hours total, parallelizable to 45 minutes).
- **Memory scales similarly**. A flat 900K-cell design needs ~29 GB for
  routing; macros may need 8 GB each.
- **Iteration is faster** — changing one macro doesn't rebuild others.

### How to implement

Use `demo_sram()` or `demo_hierarchical()` from `defs.bzl`:

```python
# Build PE as a macro
demo_sram(
    name = "PE",
    verilog_files = [":design_sv"],
    mock_area = 1.0,
    abstract_stage = "cts",
)

# Top level uses PE as a macro
demo_hierarchical(
    name = "TopModule",
    verilog_files = [":design_sv"],
    macros = [":PE_generate_abstract"],
)
```

Document the decomposition rationale in the project README.

## Return results

After all stages succeed (or after giving up), report:
- Which stages were cached vs. rebuilt
- Any warnings or issues observed in the logs
- Key metrics (cells, area, WNS) if available from reports
- If incomplete: what stage failed/timed out and why

## Write up findings in project README.md

After the full flow completes (or after a significant debugging session),
**update `<project>/README.md`** with a comprehensive qualitative and
quantitative summary. This README serves two purposes:

1. **Institutional memory** — so future runs don't repeat the same debugging
2. **Cross-project comparison** — so Claude can compare designs quantitatively
   and qualitatively across projects (e.g. "how does gemmini compare to serv?")

### Required sections in the README

**Status section** — current state of the flow (which stages complete, what's
blocked, what's next). Update this every time the status changes.

**Per-stage results table** — elapsed time, peak memory, and notes for every
stage that has been run. Example:

```markdown
| Stage | Time | Peak Memory | Notes |
|-------|-----:|------------:|-------|
| Synthesis | 177s (3 min) | 533 MB | Hierarchical, mocked SRAMs |
| Floorplan | 354s (6 min) | 3.7 GB | Timing repair futile at -1007ps WNS |
```

**Key metrics table** — cells, area, utilization, fmax, WNS/TNS, clock skew.
Use the latest stage's metrics JSON (extract with `python3 -c "import json; ..."`).

**Timing analysis** — describe the critical path, what limits fmax, and whether
timing closure is achievable at the target frequency. Include the WNS at each
stage to show how it evolves through the flow.

**Resource challenges** — memory requirements, runtime estimates, and any OOM
or resource issues encountered. Include specific numbers (peak memory, thread
count, wall clock time) so future runs can plan accordingly.

**Current BUILD.bazel configuration** — copy the `arguments` dict with comments
explaining why each parameter was chosen. Note which settings prioritize speed
vs. QoR.

**Future improvements** — actionable items, ordered by impact. Include both
parameter tuning (e.g. "reduce PLACE_DENSITY to 0.5") and design changes
(e.g. "replace mocked memories with real SRAMs").

### Writing style

- Lead with numbers — every claim should have a metric attached
- Explain the "why" behind parameter choices, not just the values
- Note what was tried and didn't work, not just what succeeded
- Keep it factual — this data will be used for automated comparison
- Use consistent formatting across all project READMEs — match the
  conventions in existing projects (e.g. `×` not `x` for dimensions,
  `→` not `->` for arrows, `μm²` not `um^2` for units). Check the
  top-level README and other project READMEs for the established style
  before writing.

ARGUMENTS: $ARGUMENTS
