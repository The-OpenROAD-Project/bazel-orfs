# Gemmini 8×8 — Medium Configuration of Berkeley Systolic Array

An 8×8 variant (64 PEs) — between the 4×4 and 16×16 configurations.
Key data point for understanding how routing time and memory scale.

See also: [2×2 (4 PEs)](../gemmini_2x2/) | [4×4 (16 PEs)](../gemmini_4x4/) | [16×16 (256 PEs)](../gemmini/)

## What This Demo Builds

**MeshWithDelays** — an 8×8 INT8 systolic array core, targeting ASAP7 7nm:

- **Architecture**: 8×8 mesh of PEs, each with a MAC unit (8-bit × 8-bit → 32-bit accumulate)
- **Dataflow**: Supports both output-stationary and weight-stationary
- **Target frequency**: 1 GHz (1000ps clock period)

## Status: New

## Build

```bash
bazelisk build //gemmini_8x8:MeshWithDelays_route
```
