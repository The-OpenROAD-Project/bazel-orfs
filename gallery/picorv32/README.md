# PicoRV32

A size-optimized RISC-V CPU core implementing the RV32IMC instruction set,
designed for use as an auxiliary processor in FPGA designs and ASICs.

**Upstream**: [YosysHQ/picorv32](https://github.com/YosysHQ/picorv32)
**License**: ISC

## What This Demo Builds

- **Top module**: `picorv32` — the core CPU with native memory interface
- **Configuration**: Default parameters (RV32IMC with counters, dual-port regfile)
- **PDK**: ASAP7 (7nm predictive)
- **Target frequency**: 1 GHz (1000ps clock period)

The `picorv32` module is the idiomatic hard macro — the CPU core itself,
not the SoC wrapper (`picosoc`) or AXI/Wishbone bus adapters.

## Results

| Metric | Value |
|--------|-------|
| **Cells** | 12,159 |
| **Sequential** | 1,597 FFs (32%) |
| **Synth area** | 1,446 μm² |
| **Placed area** | 1,510 μm² |
| **Utilization** | 42% |
| **Reproduced freq** | 0.84 GHz |
| **WNS** | −193 ps |

## Build

```bash
# Synthesis only
bazelisk build //picorv32:picorv32_synth

# Full RTL-to-GDS flow
bazelisk build //picorv32:picorv32_route

# Open in GUI
bazelisk run //picorv32:picorv32_route -- $(pwd)/route gui_route
```

## References

- [YosysHQ/picorv32](https://github.com/YosysHQ/picorv32) — upstream repository
- [RISC-V ISA specification](https://riscv.org/specifications/)
