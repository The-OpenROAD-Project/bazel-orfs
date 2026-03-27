# Gemmini 2×2 — Minimal Configuration of Berkeley Systolic Array

A 2×2 variant of the [Gemmini](../gemmini/) demo with only 4 PEs — the
smallest possible mesh. Minutes-scale turnaround for rapid iteration.

See also: [4×4 (16 PEs)](../gemmini_4x4/) | [16×16 (256 PEs)](../gemmini/)

## What This Demo Builds

**MeshWithDelays** — a 2×2 INT8 systolic array core, targeting ASAP7 7nm:

- **Architecture**: 2×2 mesh of PEs, each with a MAC unit (8-bit × 8-bit → 32-bit accumulate)
- **Dataflow**: Supports both output-stationary and weight-stationary
- **Target frequency**: 1 GHz (1000ps clock period)

## Status: Route

## Build

```bash
bazelisk build //gemmini_2x2:MeshWithDelays_route
```

## References

- [4×4 configuration](../gemmini_4x4/) — medium scale
- [16×16 configuration](../gemmini/) — full scale with collected build data
- [Gemmini GitHub](https://github.com/ucb-bar/gemmini)
