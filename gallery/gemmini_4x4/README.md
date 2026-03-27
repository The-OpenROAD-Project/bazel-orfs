# Gemmini 4×4 — Small Configuration of Berkeley Systolic Array

A 4×4 variant of the [Gemmini](../gemmini/) demo, sized to complete the
full RTL-to-GDS flow on a 30 GB machine.

The full 16×16 configuration (256 PEs, 896K cells) requires ~29 GB RAM for
detail routing and 6+ hours — see [gemmini/](../gemmini/) for that data.
This 4×4 configuration (16 PEs) demonstrates the same architecture at a
tractable scale.

## What This Demo Builds

**MeshWithDelays** — a 4×4 INT8 systolic array core, targeting ASAP7 7nm:

- **Architecture**: 4×4 mesh of PEs, each with a MAC unit (8-bit × 8-bit → 32-bit accumulate)
- **Dataflow**: Supports both output-stationary and weight-stationary
- **Pipeline**: Configurable tile latency with SRAM-based shift registers
- **Target frequency**: 1 GHz (1000ps clock period)

Uses the same Chisel source, patches, and upstream dependency as the 16×16
configuration — only the generator parameters differ.

## Status: Route Complete

The flow completed through **route** (detail routing). The `_final` stage
fails due to a known bazel-orfs klayout GDS merge bug (empty `6_1_merge.log`).

### Per-Stage Results

| Stage | Time | Peak Memory | Notes |
|-------|-----:|------------:|-------|
| Synthesis | 72s (1 min) | 342 MB | Flat, 47,600 synthesis cells |
| Floorplan | 55s (1 min) | 391 MB | Timing repair 43s, WNS -185ps |
| Placement | 104s (2 min) | 519 MB | 5 substeps, all healthy |
| CTS | ~10s | ~450 MB | Repair skipped (`SKIP_CTS_REPAIR_TIMING=1`) |
| GRT | ~30s | ~500 MB | Zero overflow |
| Detail route | 22 min | 18.5 GB | Completed, 0 DRC violations |

Total time through route: **~26 minutes**. Compare to 16×16: 85 min through GRT, OOM'd at routing.

### Key Metrics (post-GRT)

| Metric | Value |
|--------|-------|
| Cells | 48,454 |
| Design area | 5,840 μm² |
| Core utilization | 41.7% |
| fmax (GRT) | 736 MHz (target: 1 GHz) |
| Setup TNS (GRT) | -130 ns |

### Comparison with 16×16

| Metric | 4×4 | 16×16 | Ratio |
|--------|----:|------:|------:|
| PEs | 16 | 256 | 16× |
| Cells (post-GRT) | 48,454 | 896,465 | 18.5× |
| Routing time | 22 min | >6 hrs (OOM) | >16× |
| Routing memory | 18.5 GB | 28.9 GB (OOM) | 1.6× |
| fmax | 736 MHz | 631 MHz | 1.17× |
| WNS (floorplan) | -185 ps | -1,007 ps | 5.4× better |

The 4×4 has better timing because the critical paths are shorter (fewer
pipeline stages in the mesh). The memory scaling is sub-linear — 18.5×
fewer cells but only 1.6× less routing memory, suggesting a large fixed
overhead in OpenROAD's data structures.

### Lessons for the 16×16

1. **Timing closure is feasible at 736 MHz for 4×4** — the 16×16 at 631 MHz
   is limited by longer paths through the larger mesh, not fundamental
   architecture issues
2. **No `SETUP_SLACK_MARGIN` needed for 4×4** — the -185ps WNS is manageable.
   The 16×16 needs -1100ps margin to skip futile repair
3. **Routing memory scales sub-linearly** — hierarchical decomposition of the
   16×16 into macros would help more with time than memory

## Build

```bash
# Synthesize
bazelisk build //gemmini_4x4:MeshWithDelays_synth

# Full flow through routing
bazelisk build //gemmini_4x4:MeshWithDelays_route
```

## References

- [Gemmini GitHub](https://github.com/ucb-bar/gemmini)
- [Gemmini: Enabling Systematic Deep-Learning Architecture Evaluation via Full-Stack Integration](https://arxiv.org/abs/1911.09925) (DAC 2021)
- [16×16 configuration](../gemmini/) — full-size variant with collected build data
