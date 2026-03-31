# Flow Rules Check (FRC) Catalog

FRC rules validate design configuration in seconds using mock tools,
catching common errors before expensive real builds. See
[flow-linter-with-frc.md](../gallery/docs/flow-linter-with-frc.md) for the design
philosophy and roadmap.

| ID | Name | Severity | Stage | Synopsis |
|----|------|----------|-------|----------|
| [FRC-6](../gallery/docs/frc/FRC-6.md) | source-file-missing | Error | Any | `file exists` returns 0 for a `.tcl` file — silent source skip |
| [FRC-7](../gallery/docs/frc/FRC-7.md) | pdn-macro-grid-empty | Error | floorplan | Macro PDN grids contain no shapes/vias (PDN-0232/0233) |
| [FRC-8](../gallery/docs/frc/FRC-8.md) | cell-not-found | Error | synth | Cell referenced in netlist/SDC not in any liberty (STA-0453) |

## Collecting FRC violations

To find new FRC candidates, build all designs for a given stage across
all platforms with `--keep_going` and compare against the lint run:

```bash
cd orfs/

# 1. Build all floorplan targets in parallel (real tools)
bazelisk build --keep_going \
  $(bazelisk query @orfs//flow/designs/... 2>/dev/null \
    | grep '_floorplan$' | grep -v lint)

# 2. Build the lint variants of the same targets
bazelisk build --keep_going \
  $(bazelisk query @orfs//flow/designs/... 2>/dev/null \
    | grep '_lint_floorplan$')
```

Any target that fails the real build but passes lint is a candidate for a
new FRC rule. For each failure:

1. Read the error output and identify the OpenROAD error code (e.g.
   PDN-0232, STA-0453).
2. Check whether the lint variant also fails — if not, the mock tool is
   missing a check.
3. Create `gallery/docs/frc/FRC-NNN.md` documenting the pattern:
   what it checks, why it matters, an example, and a suggested fix.
4. Add the rule to the table above.
5. Update the build status table in [README.md](README.md).

Repeat for each stage (`_synth`, `_floorplan`, `_place`, `_cts`, `_route`,
`_final`) to extend coverage incrementally.

## Planned (not yet implemented)

| ID | Name | Stage | Synopsis |
|----|------|-------|----------|
| FRC-1 | core-to-die-spacing | floorplan | Core-to-die spacing sufficient for PDN rings |
| FRC-2 | macro-in-bounds | floorplan | All macros fit within die area with halo |
| FRC-3 | pdn-grid-config | floorplan | PDN_TCL matches hierarchical design topology |
| FRC-4 | utilization-headroom | synth | Cell area vs. core area leaves routing margin |
| FRC-5 | pin-count-vs-perimeter | floorplan | Pin count fits die edge at minimum pitch |
