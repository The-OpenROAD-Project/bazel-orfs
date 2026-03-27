# Flow Linting and FRC for OpenROAD

## The feedback loop problem

ASIC physical design has a brutal feedback loop. Change a parameter, wait
hours for synthesis and place-and-route, discover the die is too small or
routing is congested. Try again.

Setting up hierarchical synthesis for MegaBoom — 93 modules, 35 memories —
took 2.5 hours of developer time across 8+ failed iterations. The
successful build itself took 7 minutes. Every single failure was detectable
statically from the SystemVerilog source and BUILD.bazel configuration. No
real synthesis or place-and-route was needed to find them.

| Category | Time spent |
|----------|-----------|
| Failed build wall time | ~65 min |
| Reading bazel-orfs source to understand errors | ~60 min |
| Debugging SDC issues | ~15 min |
| Debugging filegroup/test issues | ~20 min |
| **Total wasted time** | **~2.5 hours** |
| Successful final build | 7 min |

Each iteration requires: approve Claude's proposal (~30s), wait for the
build (5s–37min), scan 200+ lines of output for the actual error (~2min),
translate domain knowledge into a correction (~3min). By iteration 4, the
developer is skimming approvals, context-switching during waits, reading
error output less carefully, and providing less precise corrections. This
is the fatigue spiral: less attention → worse corrections → longer wait for
worse results → more fatigue.

Scalable RTL helps — the small Gemmini (4×4, 47K cells) completed in
minutes where the full 16×16 (896K cells) OOM'd after 6 hours of routing,
and the small version revealed the same -185ps WNS pattern. But scalable
RTL doesn't eliminate configuration errors. The Make flow can't help — it
runs commands and produces files but doesn't know what those files mean.

## Make isn't going away — and shouldn't

Make is the right level of cognitive load for learning the ORFS flow and
small experiments. It's immediate, transparent, well-understood.

"I'm not going to go spelunking into your flow to help you" is a perfectly
valid position from OpenROAD developers. They maintain the tools, not the
build system wrappers. Make is their lingua franca for reproduction.

The `make <stage>_issue` workflow is the gold standard for bug reports.
The developer who triages your issue has dozens of bugs in their queue.
They don't want to clone your repo, install Bazel, or read your analysis.
They want:

    tar xf floorplan_mpl0005.tar.gz
    cd floorplan_mpl0005
    echo exit | ./run-me-*.sh

Untar, run, see the crash, fire up a debugger. Every second you save them
is a second closer to a fix.

The whittling flow (`whittle.py`) reduces .odb size for fast reproduction,
but the goal is not the smallest case that outputs the error string — it's
the smallest case that reproduces the idiomatic problem. Don't whittle away
more context than needed to get reproduction time down to minutes. You're
removing context that helps the developer understand what went wrong. Don't
tell them how wonderful your project is. All they want is to jump into the
debugger.

The `_deps` target in bazel-orfs produces a make wrapper that lets
OpenROAD developers use their familiar Make workflow, pointed at your
design's artifacts. Bazel builds; Make reproduces.

## What Bazel adds on top

Bazel-orfs encodes the ORFS flow as a typed dependency graph. This isn't
a replacement for Make — it's a layer on top that enables tools Make can't
support.

**Providers** (`OrfsInfo`, `LoggingInfo`, `PdkInfo`) carry structured
metadata between stages. **Output groups** separate logs, reports, metrics
JSON, and DRC violations into distinct channels. **The build graph itself**
encodes stage ordering, variant relationships, and configuration.

This information already exists — it's how Bazel builds the design. The
cost of exposing it is zero. And once exposed, it enables a family of
tools that would each require bespoke scripting in Make.

Make doesn't have providers, output groups, or a queryable build graph. To
build these tools on Make, you'd need to parse Makefile variables, track
file dependencies manually, write custom scripts for each piece of
metadata, and maintain those scripts as ORFS evolves. With Bazel, the
plumbing is the build system.

Bazel and Make coexist. Bazel manages the graph and metadata. Make remains
the execution engine and the interface for OpenROAD developers. The `_deps`
targets bridge the two.

## The flow linter — seconds instead of hours

`@lint-openroad` and `@lint-yosys` replace real OpenROAD and Yosys with
seconds-fast mock binaries. They execute the same ORFS TCL scripts via a
minimal TCL interpreter with mock command implementations, creating all
expected output files without running actual synthesis or place-and-route.

Because Bazel knows the full flow structure, swapping tools is a one-line
variant override — `orfs_sweep` with per-variant `openroad`/`yosys`
attributes. No changes to ORFS scripts, no special configuration.

What the linter validates today:

- ORFS variable ranges: CORE_UTILIZATION, PLACE_DENSITY,
  ROUTING_LAYER_ADJUSTMENT, PDK-aware die size limits (500um ASAP7,
  10000um sky130)
- Cross-variable consistency: CORE_UTILIZATION + DIE_AREA conflicts,
  MOCK_AREA scale factor sanity
- SDC constraints: port names validated against Verilog, clock
  definitions, multi-arg `get_ports` (STA-0566)
- A/B comparison: per-stage `py_test` targets that diff lint vs. real
  flow outputs
- 199 unit tests: TCL interpreter (96), OpenROAD commands (81), Yosys
  commands (22)

The linter also works with Make — pass the lint binaries via environment
variables:

```bash
make OPENROAD_EXE=/path/to/lint-openroad \
     YOSYS_EXE=/path/to/lint-yosys \
     DESIGN_CONFIG=designs/asap7/counter/config.mk
```

## The training loop

The cost of gathering flow knowledge and encoding it as checks is the
bottleneck. Each check is a small, cross-stage, crosscutting concern
test — and that's exactly why a linting *flow* is needed, not just static
analysis. Downstream linting stages need information from previous stages
to assemble coherent, actionable diagnostics.

**Why a flow, not just static checks.** A static checker can validate that
CORE_UTILIZATION is in (0, 100]. But only a flow can tell you: "you asked
for an 8000×8000um die area because you used the wrong units on
CORE_UTILIZATION — your 95% utilization with 200K cells at ASAP7 density
implies a 50um die, not 8000um." That diagnosis requires mock synthesis
(to get cell count), mock floorplan (to compute implied die area), and
cross-referencing against PDK parameters. Each stage contributes a piece
of the picture.

**Separation of concerns.** Real OpenROAD's policy is "you asked for it,
you deserve the result" — PDN will happily generate an 8000×8000um grid.
It is not OpenROAD's job to check for intent. That's the job of the FRC
and the linter. The linter runs the same flow scripts through mock tools,
gathering cross-stage information to present a coherent story about what
you actually asked for vs. what you probably meant.

The mock-train workflow encodes each discovered gotcha as a pytest
assertion:

1. **Hit a problem** — mock build fails, hangs, produces wrong output, or
   a real flow issue that mock should have caught.
2. **Identify the crazy value** — MOCK_AREA as absolute area instead of
   scale factor, DIE_AREA > 500um on ASAP7, CORE_UTILIZATION outside
   (0, 100].
3. **Write the check** — Python code in `openroad_commands.py` or
   `yosys_commands.py` at the command that first encounters the value.
4. **Write the unit test** — always a pair: positive (insane triggers
   error) and negative (sane is quiet). The test IS the specification.
5. **Run tests** — `pytest` across all three test files.
6. **Fix root cause** — if the crazy value came from `defs.bzl` or
   `BUILD.bazel`, fix that too. Add Starlark `fail()` for values
   validatable at analysis time.
7. **Commit together** — sanity check, unit tests, and root cause fix.

The cost of this loop is low. Claude and a skilled operator produce unit
tests as a byproduct of normal debugging work. Each session encodes the
gotcha permanently. The test suite grows monotonically — every gotcha
encountered once is caught forever after. This is how the linter learns:
not through ML training, but through human-in-the-loop debugging sessions
captured as pytest assertions.

Examples from MegaBoom:

- `test_blackbox_nonexistent_module` — flags SYNTH_BLACKBOXES typos
- `test_sdc_missing_reset_port` — validates port references
- `test_sdc_multi_arg_get_ports` — catches STA-0566 pattern
- `test_orfs_flow_with_save_odb` — flags kwargs leak
- `test_pdn_block_vs_blocks` — validates PDN strategy for macro designs

## FRC — Flow Rules Check

Reframe linting as **FRC (Flow Rules Check)**, analogous to DRC (Design
Rules Check). The framing is immediately intuitive to hardware engineers
familiar with DRC/LVS terminology.

### Severity levels

Like DRC violations, FRC checks have graduated severity:

- **Error** — must-fix, will cause a downstream stage to fail
- **Warning** — suspicious configuration, may or may not cause problems
- **Tip** — best-practice suggestion, not blocking

### Forward prediction

The key differentiator: FRC can predict failures in future stages based on
results from earlier stages, shifting failure detection left. Predictions
reach forward from the beginning of a stage, not just to the next stage.

After `initialize_floorplan`, the linter knows die perimeter, pin count
from synthesis, and macro halo requirements. It can predict right then:
"your 200 pins don't fit on the die edge with this aspect ratio" — before
IO placement, before PDN, before any of the expensive substeps run.

| After stage | Check | Predicted failure |
|---|---|---|
| floorplan | DIE_AREA / CORE_AREA too small for macro + halo | PDN rings won't fit (PDN-0351) |
| floorplan | Insufficient core-to-die spacing | PDN grid generation fails (PDN-0232/0233) |
| floorplan | Pin count vs. die perimeter | IO placement fails |
| floorplan | Macro overlaps or out-of-bounds | Placement failures |
| synth | High cell count vs. CORE_UTILIZATION | Placement congestion / timing closure |
| place | Congestion hotspots | Routing DRVs in GRT/detailed route |

### Rule numbering

Each FRC rule gets a stable numeric ID (FRC-1, FRC-2, ...) like DRC rules.
For each rule:

- **Python unit test** — embodies the intent of the check; the test IS
  the specification.
- **Markdown doc** (`frc/FRC-NNN.md`) — human-readable description: what
  the rule checks, why it matters, example failures, and suggested fixes.
- **Check implementation** — Python function that takes stage outputs and
  returns structured violations.

| ID | Name | After stage | Checks |
|---|---|---|---|
| FRC-1 | core-to-die-spacing | floorplan | Core-to-die spacing sufficient for PDN rings |
| FRC-2 | macro-in-bounds | floorplan | All macros fit within die area with halo |
| FRC-3 | pdn-grid-config | floorplan | PDN_TCL matches hierarchical design topology |
| FRC-4 | utilization-headroom | synth | Cell area vs. core area leaves routing margin |
| FRC-5 | pin-count-vs-perimeter | floorplan | Pin count fits die edge at minimum pitch |

### Mining rules from history

OpenROAD's GitHub issues, PRs, and discussions contain years of failure
patterns — PDN-0232, PDN-0233, PDN-0351, GPL congestion, GRT DRVs. Each
pattern is a candidate FRC rule: detect the precondition that leads to the
error, before the failing stage runs. The source code history is the
training data.

## frc.yaml — curating rules back into ORFS

The lint checks currently hardcoded in bazel-orfs are a prototype. As they
stabilize, they belong upstream in ORFS.

ORFS already has the precedent. `variables.yaml` describes variable
metadata (types, ranges, stage assignments). `defaults.py` reads it and
prints Make-compatible output. `variables.mk` evals it. bazel-orfs
consumes it via `load_json_file` in `MODULE.bazel`.

A new `frc.yaml` is the natural extension: structured rule definitions
(ID, stage, severity, preconditions, predicted failure) that any build
system can consume — Make, Bazel, or whatever comes next.

The formalization path: checks hardcoded in mock lint → stable →
refactored into upstream `variables.yaml` / `frc.yaml` → formalized with
`min`, `max`, `type`, cross-variable constraints. bazel-orfs is the
incubator; ORFS is the home. Demo projects provide the ground truth for
what values are sane.

## Scaling the gallery

The gallery has 13 projects from arcane build systems and languages:
Chisel (Gemmini, CoralNPU), Amaranth (GenBen), pymtl3, standard Verilog
(serv, picorv32, cva6). Claude Code creates the patches to give Yosys the
Verilog it needs — cross-language pattern recognition, cross-project
dependency tracing, Scala error interpretation. This is quintessentially
an LLM task: no specialized tools exist for Chisel 7 migration across
300+ files.

The linting flow makes this practical. Build one stage in seconds, predict
what happens in onward stages, tune parameters with a seconds-not-days
feedback loop. Without lint, each parameter experiment costs minutes to
hours. With lint, the gallery can grow enormously.

The division of labor:

```
LLM (creative)          → .sv + BUILD.bazel + .sdc
MOCK FLOW (deterministic) → validation report + estimates
GUI (interactive)        → visual interface
REAL TOOLS (ground truth) → the actual chip design
```

The LLM gets to Verilog. The mock validates configuration instantly. The
GUI wraps both in an accessible interface. Real tools run once, correctly.

## Constraining the autotuner search space

bazel-orfs supports design space exploration via `orfs_sweep` and
`string_flag` build settings. External optimizers — Optuna, Vizier,
hyperopt — can drive DSE by scripting `bazel build` invocations with
different flag values and parsing PPA metrics from the outputs.

The autotuner explores a combinatorial space of ORFS parameters. Most of
that space is nonsensical: CORE_UTILIZATION=95 with a macro-heavy design,
or DIE_AREA too small for the PDN rings. FRC checks can prune the search
space before running any real builds — reject parameter combinations that
violate known flow rules. This turns the autotuner from blind search into
informed search.

The FRC rules mined from OpenROAD history become the autotuner's
constraints: failure patterns distilled into fast, checkable predicates.

## The GUI — another thing you get for free

Same structured metadata enables static HTML reports. Run a build
overnight; next morning, open a static HTML file and instantly inspect
everything — histograms, timing paths, layout, clock tree — with zero
wait because all data is pre-computed. No WebSocket, no loading spinners,
no "Update" buttons. Open the file, everything is there.

Gallery screenshots (`demo_gallery_image()`) already demonstrate this
pattern: build-time image generation from structured stage outputs.

The mock flow is the intelligence layer for the GUI: DAG view annotated
with estimated cell counts and flagged errors, config editor that
validates changes instantly before building, build launcher that
pre-validates so builds succeed on first attempt.

See [static-html-gui.md](../ideas/static-html-gui.md) for the full
architecture and [OpenROAD PR #9770](https://github.com/The-OpenROAD-Project/OpenROAD/pull/9770)
for the proof of concept.

## MegaBoom — where this became necessary

MegaBoom — a 4-wide BOOM CPU compiled from Chisel source through a
6-library dependency chain — is where the lifting got heavy enough to
inspire the linting and FRC work. The rocket-chip Chisel 7 patch alone
was 7,305 lines across 300+ files. 93 modules, 35 memories, hierarchical
synthesis with extracted SRAMs.

"When a full build takes 6 hours and 29 GB of RAM, every experiment is a
day-long commitment. You cannot develop a backend strategy by learning
from builds that take hours — the feedback loop is too slow to explore the
design space."

MegaBoom is the next project we'll validate the FRC flow against.

## The cost of coding approaches zero

Each of these capabilities — linting, FRC, static GUI, autotuner pruning,
gallery scaling — reuses the same structured information that Bazel already
maintains. The marginal cost of each new tool is writing the check logic,
not the plumbing to extract metadata, identify stages, or track
dependencies.

The training loop (debug → unit test → check) means Claude and a skilled
operator produce FRC rules as a byproduct of normal debugging work. The
encoding cost is a pytest assertion, not a new infrastructure project.

In Make, each tool would need its own parsing, its own filename
conventions, its own state tracking. In Bazel, the plumbing is the build
system.
