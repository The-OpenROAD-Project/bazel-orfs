# CVA6 — cv32a60x Configuration

Application-class 6-stage in-order RISC-V CPU from the
[OpenHW Group](https://github.com/openhwgroup/cva6), cv32a60x configuration
with HPDcache.

## What This Builds

- **Module**: `cva6` — the CPU core (not the SoC wrapper)
- **Configuration**: cv32a60x (32-bit, HPDcache)
- **PDK**: ASAP7 7nm
- **Clock**: 500 MHz target (2000 ps)

## Results

| Metric | Value |
|--------|-------|
| Cells | 80,306 |
| Area | 15,189 μm² |
| Target Freq | 0.50 GHz |
| Achieved Freq | 0.29 GHz |
| WNS | -1,413 ps |
| Status | Placement |

## Submodule Handling

CVA6 uses git submodules for FPU and HPDcache. Since `http_archive` doesn't
include submodule contents, these are fetched separately:

- `@cvfpu` — FPU (shared with coralnpu)
- `@fpu_div_sqrt_mvp` — FPU div/sqrt
- `@cv_hpdcache` — High-performance data cache

## SRAM Strategy

`SYNTH_MOCK_LARGE_MEMORIES=1` handles all memories automatically.
HPDcache behavioral models from `@cv_hpdcache` provide the source.

Future: add `demo_sram()` targets for hpdcache SRAMs with custom
`_impl.sv` files for better area estimates (see PR #3053).

## Build

```bash
# Synthesis
bazelisk build //cva6:cva6_synth

# Placement
bazelisk build //cva6:cva6_place

# Full flow
bazelisk build //cva6:cva6_final
```

## Future Improvements

Detail routing OOM'd at 46 GB with 70K DRC violations — flat 80K cells is
too large for single-pass routing. The following changes are needed:

1. **Hierarchical synthesis** — per-module `orfs_synth()` with parallel builds
   (coralnpu pattern). Top modules by cell count: regfile (7K), CSR (6.5K),
   multiplier (6.3K), RVFI probes (4.1K), store buffer (3.7K).

2. **SRAM macros** — `demo_sram()` targets for hpdcache SRAMs with custom
   `_impl.sv` behavioral models and `mock_area=0.2`. PR #3053 identifies:
   - `hpdcache_sram_1rw` (64×28 bits, 2 instances)
   - `hpdcache_sram_wbyteenable_1rw` (128×64 bits, 2 instances)

3. **Timing closure** — WNS is -1,413 ps (0.29 GHz vs 0.50 GHz target).
   After hierarchical builds reduce cell count, tune `SETUP_SLACK_MARGIN`
   and enable `GPL_TIMING_DRIVEN` for better QoR.

4. **Remove RVFI probes** — `cva6_rvfi_probes` adds 4.1K cells (5% of design)
   for verification only. Exclude for synthesis to reduce area.

## References

- [openhwgroup/cva6](https://github.com/openhwgroup/cva6)
- [PR #3053](https://github.com/openhwgroup/cva6/pull/3053) — bazel-orfs integration
- [CVA6 User Manual](https://docs.openhwgroup.org/projects/cva6-user-manual/)
