# FRC-7: pdn-macro-grid-empty

| Field | Value |
|-------|-------|
| **ID** | FRC-7 |
| **Name** | pdn-macro-grid-empty |
| **Severity** | Error |
| **Stage** | floorplan (2_4_floorplan_pdn) |

## What it checks

After macro placement, the PDN step generates power grids for each macro
instance. When a macro grid contains no shapes or vias, OpenROAD emits
PDN-0232 per instance and then PDN-0233 to abort the flow.

## Why it matters

The PDN step is the last substep of floorplan. A design that passes
synthesis, initial floorplan, macro placement, and tapcell insertion can
still fail here — wasting minutes of build time on a configuration that
was never going to work.

## Root cause

On asap7, the platform `config.mk` selects `PDN_TCL` based on whether
`BLOCKS` is set:

```makefile
ifeq ($(BLOCKS),)
   export PDN_TCL ?= .../grid_strategy-M1-M2-M5-M6.tcl
else
   export PDN_TCL ?= .../BLOCKS_grid_strategy.tcl
endif
```

`BLOCKS_grid_strategy.tcl` defines an `ElementGrid` macro grid with only
an M5↔M6 connection rule but **no stripes**. When the block abstract has
`MAX_ROUTING_LAYER=M4`, the M5↔M6 connection has nothing to connect —
the grids are empty.

The working pattern (used by `aes-block`) overrides `PDN_TCL` to use
`BLOCK_grid_strategy.tcl`, which defines M4↔M5 connections matching the
block's routing constraints.

## Example

`riscv32i-mock-sram/fakeram7_256x32:riscv_top_floorplan` failed at
`2_4_floorplan_pdn` with:

```
[INFO PDN-0001] Inserting grid: CORE_macro_grid_1 - dmem.dmem0
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem0" (Instance) does not contain any shapes or vias.
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem1" (Instance) does not contain any shapes or vias.
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem2" (Instance) does not contain any shapes or vias.
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem3" (Instance) does not contain any shapes or vias.
[ERROR PDN-0233] Failed to generate full power grid.
```

## Fix

Override `PDN_TCL` in the design's `config.mk` to use
`BLOCK_grid_strategy.tcl`:

```makefile
export PDN_TCL = $(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl
```

This was applied in patch 0035 and verified: the floorplan now passes
with only the `top` grid inserted (no empty macro grids).

## Implementation

Not yet implemented in mock-openroad. The mock `pdngen` command
(`gallery/lint/openroad/src/bin/openroad_commands.py`, `cmd_pdngen`) is
currently a no-op stub. A future implementation could cross-check
`PDN_TCL` grid definitions against block `MAX_ROUTING_LAYER` constraints
to detect layer mismatches before the real build.
