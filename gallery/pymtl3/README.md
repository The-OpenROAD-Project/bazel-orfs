# pymtl3 — ChecksumRTL

Stream-based checksum unit generated from [pymtl3](https://github.com/pymtl/pymtl3),
Cornell BRG's Python-based hardware modeling framework.

## What This Builds

- **Module**: `ChecksumRTL_noparam` — 128-bit stream checksum with pipeline queue
- **PDK**: ASAP7 7nm
- **Generation**: Python → Verilog via pymtl3's `YosysTranslationPass`

## Results

| Metric | Value |
|--------|-------|
| Cells | 1,678 |
| Area | 192 μm² |
| Target Freq | 1.0 GHz |
| Achieved Freq | 0.42 GHz |
| WNS | -1,370 ps |
| Power | 23.1 mW |

## Build

```bash
# Full RTL-to-GDS flow
bazelisk build //pymtl3:ChecksumRTL_noparam_final

# CI smoketest
bazelisk test //pymtl3:checksum_build_test

# Gallery screenshot
bazelisk build //pymtl3:ChecksumRTL_noparam_gallery
```

## Purpose

This is the **fastest CI smoketest** in the gallery (~85s for full RTL-to-GDS).
It exercises the complete OpenROAD flow on a real design while keeping CI
turnaround short.

## References

- [pymtl3](https://github.com/pymtl/pymtl3) — Python-based hardware modeling framework
- [Cornell BRG](https://www.csl.cornell.edu/~cbatten/) — Computer Systems Laboratory
