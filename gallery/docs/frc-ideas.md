# FRC — Flow Rules Check

Reframe "linting" as **FRC (Flow Rules Check)**, analogous to **DRC** (Design
Rules Check). Linting validates that the flow configuration and rules are
correct, just as DRC validates that the physical design meets manufacturing
rules. The FRC framing is immediately intuitive to hardware engineers familiar
with DRC/LVS terminology.

## Severity levels

Like DRC violations, FRC checks should have graduated severity:

- **Error** — must-fix, will cause a downstream stage to fail
- **Warning** — suspicious configuration, may or may not cause problems
- **Tip** — best-practice suggestion, not blocking

## Predictions

The key differentiator: FRC can **predict** failures in future stages based on
results from earlier stages, shifting failure detection left.

Examples:

| After stage | Check | Predicted failure |
|---|---|---|
| floorplan | DIE_AREA / CORE_AREA too small for macro + halo | PDN rings won't fit (PDN-0351) |
| floorplan | Insufficient core-to-die spacing | PDN grid generation fails (PDN-0232/0233) |
| floorplan | Macro overlaps or out-of-bounds | Placement failures |
| synth | High cell count vs. CORE_UTILIZATION | Placement congestion / timing closure |
| place | Congestion hotspots | Routing DRVs in GRT/detailed route |

The idea: after each stage completes, run a lightweight check that inspects
the output (ODB metrics, area, utilization) and flags likely problems in the
*next* stage — before spending the time to actually run it.

## Lint scope: canonicalize only, no synthesis

Currently lint runs the full flow with mock tools. Ideally, linting should
only need Yosys to produce RTLIL (canonicalization) — not full synthesis
with ABC. This would make lint near-instant and allow it to cover all designs
(including serv) in CI without real build cost.

Blocker: `orfs_synth()` doesn't currently separate canonicalization from
synthesis, so this requires upstream ORFS changes.

## Mining rules from OpenROAD/ORFS history

- Mine the GitHub OpenROAD/ORFS issue database and git log for error patterns
- Analyze all error messages (PDN-0232, PDN-0233, PDN-0351, etc.) and convert
  them into Python FRC checks with unit tests
- Each check: detect the precondition that leads to the error, before the
  failing stage runs

## Rule numbering and artifacts

Each FRC rule gets a stable numeric ID (FRC-1, FRC-2, ...) like DRC rules.
For each rule:

- **Python unit test** — embodies the intent of the check; the test IS the
  specification. Tests run against synthetic inputs (small ODB snippets,
  metric JSONs) to verify detection without needing a full ORFS build.
- **Markdown doc** (`frc/FRC-NNN.md`) — human-readable description: what the
  rule checks, why it matters, example failures, and suggested fixes.
- **Check implementation** — Python function that takes stage outputs and
  returns structured violations.

Example:

| ID | Name | After stage | Checks |
|---|---|---|---|
| FRC-1 | core-to-die-spacing | floorplan | Core-to-die spacing sufficient for PDN rings |
| FRC-2 | macro-in-bounds | floorplan | All macros fit within die area with halo |
| FRC-3 | pdn-grid-config | floorplan | PDN_TCL matches hierarchical design topology |
| FRC-4 | utilization-headroom | synth | Cell area vs. core area leaves routing margin |

## Implementation sketch

- Per-stage check scripts (Tcl or Python) that read ODB / metrics
- Integrated into the bazel-orfs flow as an optional post-stage step
- Output structured violations (JSON) with severity, message, predicted stage
- A/B comparison (current lint infrastructure) remains for determinism checks;
  FRC is orthogonal — it checks *correctness* of configuration

## To do / investigate

- [ ] Investigate: can `orfs_synth()` split canonicalization from full synthesis?
- [ ] Investigate: mine OpenROAD GitHub issues for common error patterns
      (PDN-*, GPL-*, GRT-*, DRT-*) and catalog preconditions
- [ ] Investigate: what ODB metrics / report data is available after each stage
      that could feed FRC checks?
- [ ] Fix: `genMetrics.py` crashes on empty JSON from lint variant — lint
      `generate_metadata` is broken (workaround: `--build_tests_only`)
- [ ] Implement: first FRC check — validate core-to-die spacing is sufficient
      for PDN ring config after floorplan
- [ ] Implement: FRC check for macro placement vs. die area bounds
- [ ] Design: structured FRC output format (JSON with severity, stage, message)
- [ ] Design: integration point in bazel-orfs — post-stage hook or separate rule?
