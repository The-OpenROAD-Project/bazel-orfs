# XiangShan XSCore on asap7: a reference frame, not a CI design

XSCore is the core of XiangShan's Kunminghu generation: frontend, backend,
memory block, L1 caches and TLBs, about 4.3 million cells after synthesis.
It is here to be a fixed point that everyone can look at, run again and
argue about with numbers. It is not here to pass.

Nothing in this package runs in CI. Every flow target is
`tags = ["manual"]`, and it stays that way.

## What it is for

The flow does not converge. Global route is skipped past pin access
because of an open OpenROAD bug, and the five-iteration route has never
finished on this design. That is the point rather than a caveat: the
value of a design this size is the single-concern problems it produces,
and those are what leave here as reproducers, feature requests and
patches for OpenROAD, ORFS and XiangShan's own build.

The workflow is:

1. Run the baseline. It reproduces a known result, warts and all.
2. Find one thing wrong with it, measured.
3. Reproduce that one thing in a test that runs in seconds or minutes.
   The battery beside this package is where those live:
   `test/structured_netlist`, `test/planned_parent`, `test/macro_select`.
4. Fix it where it belongs, upstream or here, with the small test as the
   evidence and this design as the provenance.
5. Re-run the baseline and record the new numbers.

A position that falls in the small test falls here too, and a day of this
design costs what a minute of the small one does. Nobody should be
debugging against XSCore when a two-minute case reproduces the same
thing.

## Running it

```
bazelisk run //test/coremark_joule/designs/asap7/xiangshan:XSCore_grt gui_grt
```

That builds every stage and opens the result in the OpenROAD GUI, with the
congestion map the flow produced. Replace `gui_grt` with `open_grt` for a
Tcl shell on it, or drop the argument to build without opening anything.

**The machine matters.** Peak memory is about 61 GB in global route and
47 GB in clock tree synthesis, so this needs 64 GB and will not run on a
32 GB laptop. A cold build is about six hours: synthesis a little over
two, floorplan twenty minutes, placement and repair seventy minutes,
clock tree synthesis an hour, global route twenty minutes. With the
remote cache warm it is a download.

Earlier stages are targets of their own when that is all you need:
`XSCore_synth`, `_floorplan`, `_place`, `_cts`. Each has a
`gui_<stage>` and an `open_<stage>` form, and a `_deps` companion that
installs a standalone tree you can iterate in by hand.

## The baseline

`docs/xiangshan_baseline.json` carries the numbers, one entry per run, and
the figures in `docs/images/` are rendered from it. The current entry is
the reference: route-0 congestion, the worst edge, per-stage wall time and
peak memory, and the post-clock-tree worst slack. A change that claims an
improvement says so by moving those numbers.

## The warts, on purpose

Each one is a known, measured problem with a home in
`ideas/xiangshan-timing.md`, which has the full inventory.

- **Global route does not converge.** One maze iteration on a 3,978
  square gcell grid takes hours; every knob arm tried has timed out.
  Entry 18, and take 16's matrix.
- **Pin access is skipped.** Global route otherwise stops on exactly one
  pin per hardened block. A five-second reproducer exists in
  `test/planned_parent`. Entry 12.
- **The timing is not the design's timing.** The blocks are abstracted at
  their place stage, before their own clock tree, so each abstract's clock
  pin carries the block's whole unbuffered clock net, 145 pF for the
  memory block. The post-clock-tree worst slack is dominated by that
  model, not by the logic. Entry 17.
- **Seven carried ORFS patches** and one carried OpenROAD patch make the
  flow run at all; each says in its header what it fixes and how it
  retires. `patches/`, registered in `orfs_source.bzl`.
- **The register files are generated, not synthesised.** Yosys does not
  finish them at this size, so they are built by `tools/structured_gen`
  from the specs in this directory and dropped into the parent's rows.
  The same need exists for the content-addressable memories and has not
  been met.

## What this is not

It is not a regression test, a quality target, or a claim about
XiangShan. XiangShan's own published target is 3 GHz on a 7 nm process,
a 333 ps period; what this flow produces on asap7 is a different number
by a large factor, and the ladder of where that factor comes from is in
the inventory. The configuration here is integer-only with a small last
level cache, chosen so the study can run, and is a deliberate departure
from Kunminghu as delivered.

It is also not a design you check into a flow repository and expect to
run. The build system around it is the reason it runs at all, and that
build system is what would have to travel with it.
