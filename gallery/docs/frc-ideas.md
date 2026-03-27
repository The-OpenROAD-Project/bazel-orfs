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

## Implementation sketch

- Per-stage check scripts (Tcl or Python) that read ODB / metrics
- Integrated into the bazel-orfs flow as an optional post-stage step
- Output structured violations (JSON) with severity, message, predicted stage
- A/B comparison (current lint infrastructure) remains for determinism checks;
  FRC is orthogonal — it checks *correctness* of configuration
