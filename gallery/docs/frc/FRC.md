# Flow Rules Check (FRC) Catalog

FRC rules validate design configuration in seconds using mock tools,
catching common errors before expensive real builds. See
[flow-linter-with-frc.md](../flow-linter-with-frc.md) for the design
philosophy and roadmap.

| ID | Name | Severity | Stage | Synopsis |
|----|------|----------|-------|----------|
| [FRC-6](FRC-6.md) | source-file-missing | Error | Any | `file exists` returns 0 for a `.tcl` file — silent source skip |
| [FRC-7](FRC-7.md) | pdn-macro-grid-empty | Error | floorplan | Macro PDN grids contain no shapes/vias (PDN-0232/0233) |

## Planned (not yet implemented)

| ID | Name | Stage | Synopsis |
|----|------|-------|----------|
| FRC-1 | core-to-die-spacing | floorplan | Core-to-die spacing sufficient for PDN rings |
| FRC-2 | macro-in-bounds | floorplan | All macros fit within die area with halo |
| FRC-3 | pdn-grid-config | floorplan | PDN_TCL matches hierarchical design topology |
| FRC-4 | utilization-headroom | synth | Cell area vs. core area leaves routing margin |
| FRC-5 | pin-count-vs-perimeter | floorplan | Pin count fits die edge at minimum pitch |
