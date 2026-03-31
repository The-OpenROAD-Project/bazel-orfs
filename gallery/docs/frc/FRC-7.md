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

The root cause is typically a mismatch between the macro's LEF/abstract
and the PDN TCL grid definitions: the macro power pins don't align with
the straps specified in the platform's `MACRO_BLOCKAGE_HALO` or
`pdn_grid` configuration.

## Example

`riscv32i-mock-sram/fakeram7_256x32:riscv_top_floorplan` fails at
`2_4_floorplan_pdn` with:

```
[INFO PDN-0001] Inserting grid: CORE_macro_grid_1 - dmem.dmem0
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem0" (Instance) does not contain any shapes or vias.
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem1" (Instance) does not contain any shapes or vias.
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem2" (Instance) does not contain any shapes or vias.
[WARNING PDN-0232] The grid "CORE_macro_grid_1 - dmem.dmem3" (Instance) does not contain any shapes or vias.
[ERROR PDN-0233] Failed to generate full power grid.
```

All four fakeram7_256x32 macro instances produce empty grids, causing the
flow to abort.

## Fix

Ensure the PDN TCL grid definitions for macro instances match the macro
LEF power pin geometry. Common remedies:

- Verify `PDN_TCL` or platform PDN config covers the macro's power pin
  layers and pitches.
- Check that `MACRO_BLOCKAGE_HALO` leaves enough room for PDN straps.
- For hierarchical designs, ensure the block's abstract includes power
  pins at the layers expected by the parent's PDN grid.

## Implementation

Not yet implemented in mock-openroad. The mock `pdngen` command
(`gallery/lint/openroad/src/bin/openroad_commands.py`, `cmd_pdngen`) is
currently a no-op stub. A future implementation could track macro
instances from `read_db` and flag when the PDN TCL defines macro grids
but no matching instances exist, or vice versa.
