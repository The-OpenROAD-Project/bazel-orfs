# Module-cut search

Which modules should synthesis keep (`SYNTH_KEEP_MODULES`)? Try the keep
sets, measure each one, keep the best.

![The search on asap7 riscv32i](cut_search.png)

## Run it

    bazelisk run //tools/macro_select/cut:generate_cut -- //pkg:flow out.json

- A link with a token is printed first. It's reachable over the VPN you
  ssh'd in on (the address in `SSH_CONNECTION`). Open it to watch the search.
- Bazel builds the flow's synthesis and floorplan once, as dirty-lane trees
  (`.claude/skills/dirty-lane`). After that, each keep set is synthesised by
  yosys and floorplanned by ORFS's make outside Bazel, in seconds to minutes.
- `out.json` holds the best keep list and every keep set measured.
- The page stays up until no browser has been connected for `--idle`
  seconds (300) after the search; `--max-arms` (40) caps the search.

## How it decides

- **Score:** the worst register-to-register period, measured on the
  floorplan after `repair_design -pre_placement` and with no wire, then
  area, then synthesis time. Input and output constraints are often guesses, so they
  don't count (ORFS #4583).
- **Control:** the flow's own keep settings run as an arm of their own, so
  every number reads against what the flow does today.
- **What to try next:** a *census* (`../keep_census.tcl`) on each floorplan
  finds where a kept module's boundary cut through a path. Dropping a keep
  is worth trying when its boundary cuts the worst path.
- **Search:** every keep set when there are at most 16, otherwise one
  module type flipped at a time from the best so far. A type is kept or
  flattened with all its instances.

## Reading the page

| Panel | Shows |
|---|---|
| Arms | each arm's period against how many module types it keeps; the lowest dot is the best, ◆ is the control, running arms sit on the axis and the newest pulses |
| Census | kept instances: disc size is the cell area each holds itself, fill is logic delay. Flylines are boundaries that cut a path: the wider and darker, the closer that path is to the worst one. |
| Next | what it tries next and why |

## On riscv32i

The search on asap7 riscv32i (the picture above) and its confirmation
in a clean build, `test/cut_riscv32i`:

- The census pointed at one boundary: `dmem`, kept by riscv32i's
  `SYNTH_MINIMUM_KEEP_SIZE` for its four SRAMs' area, cut the worst path
  between the address adder and the SRAMs' enable decode. It was the only
  keep with a predicted gain.
- Through global route at 780 ps under ORFS's own settings, flat
  synthesis gives a 5.2 % shorter reg2reg period than the keep (791.8
  against 835.6 ps); of the endpoints within 10 % of the period, 995 are
  faster and 3 slower. `SWAP_ARITH_OPERATORS` is worth 11 % on top,
  independently.
- At floorplan the search ranked keeping the comparator cells first;
  global route did not confirm it. Confirm a winner through global
  route, at a clock repair cannot meet: at riscv32i's own 950 ps every
  keep set closed at the clock.

## SYNTH_MINIMUM_KEEP_SIZE and macros

riscv32i's lesson generalises as a flaw in the size rule (ORFS #4714):
`convert_liberty_areas` gives a macro the gate equivalent of its area, so
a wrapper around SRAMs looks like a large module of logic, though yosys
does no work on a macro. `test/cut_keep_size` measures what a macro cost
of 0 changes:

- **Which keeps** (`keep_probe.py`, yosys up to the keep decision, today
  and with macros at cost 0, each design with its own frontend): of the
  eleven ORFS designs that synthesise hierarchically with a keep
  threshold and macros, nine keep fewer modules (`keeps.json`). Every
  module dropped is a memory wrapper or a module holding one; coralnpu and
  tinyRocket are unchanged.
- **What it does**, through global route at a clock repair cannot meet,
  reg2reg endpoints within 10 % of the period:

  | design | clock | today | macros at cost 0 | | faster / slower |
  |---|---|---:|---:|---:|---:|
  | asap7/riscv32i | 780 ps | 835.6 ps | 791.8 ps | −5.2 % | 995 / 3 |
  | nangate45/bp_be_top | 1.90 ns | 1.993 ns | 1.975 ns | −0.9 % | 225 / 7 |
  | nangate45/bp_fe_top | 1.38 ns | 1.680 ns | 1.671 ns | −0.5 % | 21 / 33 |

  No hold buffers in any arm. At 2.21 ns, a clock bp_be_top's reg2reg
  meets, the same comparison read +1.9 %: the trap riscv32i showed at
  950 ps.
- **Not measured here:** ariane133/136, mempool_group, black_parrot,
  bp_multi_top and bp_quad, whose flows do not fit this machine's budget,
  and the gf12 designs (private PDK). Their keep changes are in
  `keeps.json`.

## Caveats

- Numbers are from floorplan, with no wire and outside Bazel's cache. Put
  the winner in the flow's BUILD and confirm it with a clean build to
  global route.
- A flow that Bazel synthesises in partitions (`SYNTH_NUM_PARTITIONS`) is
  synthesised serially here, the control too.
- Small structural changes move ABC's result, so a keep set can move the
  period with no cut path near the worst: read a difference of a few
  percent as noise until a clean build repeats it.

## Developing the page

`bazelisk test //test/cut_page:page_test` loads the page on a recorded
state in Chrome for Testing's headless shell, a dev-only download, and
fails on a console error. `bazelisk run //test/cut_page:record -- //pkg:flow
out.json frames/` records a search, a PNG every 10 s; the server reads
`page.html` on each load, so an edit shows in the next frame.
