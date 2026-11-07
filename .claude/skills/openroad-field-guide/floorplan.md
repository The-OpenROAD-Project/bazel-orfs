# Floorplan, PDN and pin placement

Paths are in OpenROAD's `src/ifp/`, `src/pdn/`, `src/ppl/`, ORFS's
`flow/scripts/floorplan.tcl`, `io_placement*.tcl`, `pdn.tcl`.

## Where the time goes

- `floorplan.tcl` runs a zero-wire `repair_timing` (see [rsz.md](rsz.md))
  and `repair_tie_fanout`. On a large design that is the floorplan stage.
- pdngen: a quadratic `cleanupShapes` cost 25 min on XSTile with 1.3 M
  FIRM cells (fixed, OpenROAD #11527); via connection rescans were 92 %
  of a profile (fixed, #11364).
- ppl: Hungarian matching per section of 200 slots; rarely the cost. The
  extra skip-io gpl run that feeds it is ([gpl.md](gpl.md)).

## Silent wrong answers

- **`global_connect` skips dont_touch instances**: register files marked
  dont_touch before the PDN left 406k XSTile cells unpowered, invisible to
  timing. ORFS #4785 makes global connections before anything is
  dont_touch (carried workaround 0124 until the bump).
- A FakeRAM narrower than the strap pitch fails PDN-0233.

## Pins

- Hard stops: PPL-0024 more pins than positions (enlarge the die),
  PPL-0110/0076/0111 constraint regions with no slots.
- Pin order and partner-weighted block arrangement did not shorten
  XSTile crossings (bazel-orfs #1110, #1123). **Dead end.** Pin traps are
  solvable by pin assignment; placement traps need joint macro placement
  (bazel-orfs #1294).
