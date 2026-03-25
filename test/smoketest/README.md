# Multi-PDK Smoke Tests

Verifies that the full ORFS flow (synthesis through abstract generation)
completes for every supported PDK. These targets run in CI and use
`FAST_SETTINGS` to minimize build time.

## Design

Uses `lb_32x128` — a mock 32-entry × 128-bit SRAM (~20 lines of
SystemVerilog). It is small enough to complete the full flow quickly
while still exercising realistic placement and routing.

## Supported PDKs

| PDK | Description |
|-----|-------------|
| asap7 | ASAP 7nm predictive PDK |
| nangate45 | NanGate FreePDK45 |
| sky130hd | SkyWater SKY130 high-density |
| ihp-sg13g2 | IHP SG13G2 130nm SiGe BiCMOS |

## CI timing

All four PDKs build in parallel. Wall time is ~107 s, dominated by
the asap7 critical path:

| Stage | asap7 (critical path) | % |
|-------|----------------------:|--:|
| Synthesis | 5 s | 5% |
| Floorplan | 12 s | 11% |
| Placement | 69 s | 64% |
| CTS | 4 s | 4% |
| Global route | 3 s | 2% |
| Detailed route | 5 s | 5% |
| Final | 7 s | 7% |
| Abstract | 2 s | 2% |

Placement dominates because even with `FAST_SETTINGS` (timing-driven
and routability-driven placement disabled), global placement itself
still runs.

## PDK extensibility

The PDKs listed above are the ones bundled with the ORFS image and
exposed here for convenience. PDK support does not have to live in
bazel-orfs — users can implement private or proprietary PDK support in
their own repository using the `orfs_pdk` rule.
