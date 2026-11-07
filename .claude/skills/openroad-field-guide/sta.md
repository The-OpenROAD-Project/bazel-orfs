# OpenSTA (dbSta): the timer under every stage

OpenSTA is OpenROAD's `src/sta` submodule (The-OpenROAD-Project/OpenSTA,
a fork of parallaxsw/OpenSTA, which is upstream of it). Every repair,
timing-driven gpl, timing-driven grt and CTS balancing is an STA
workload: when a stage is slow, the timer is the first suspect.

## How it scales

- **Threads** (`BfsIterator::visitParallel`): one level at a time with a
  barrier; a level with fewer vertices than threads runs serially.
  Deep, narrow graphs (carry chains, clock trees) and incremental
  updates touching a few vertices per level do not scale.
  `write_timing_model` stops scaling at 8 threads on lock contention
  (OpenROAD #11999 open).
- **Delay calculator**: `dmp_ceff_elmore` by default, cheap. ORFS switches
  to **prima** only with `LIB_MODEL=CCS` (asap7): a transient simulation
  per arc with a sparse LU over the net's RC nodes, much slower on big
  RC nets.
- **Memory**: a vertex per pin, an edge per arc, arrivals per tag group
  (clock x rise/fall x min/max x exception state): many clocks or
  exceptions multiply it. CRPR on large propagated clocks grows
  superlinearly (OpenSTA #452 open). A timing daemon on the XSTile
  parent's CTS .odb was OOM-killed at 56 GB plus 118 GB swap.

## Where the time goes

- `write_timing_model`: per input port and edge, set an input delay,
  propagate the fanout cone, delete. O(inputs x cone); explodes on blocks
  with hundreds of thousands of ports. The O(I x O) output scan is fixed
  upstream; dense overlapping cones are still O(I x cone). Eight carried
  patches (0145-0152) give 2.8x at 32 threads and 1.6x at 1 thread
  (bazel-orfs #1412), not upstreamed.
- Exception `-to` matched linearly: 17-22 % of `repair_timing` (OpenROAD
  #11933, carried 0145).
- ORFS's `report_metrics` at each stage end (up to 4x in grt with
  `DETAILED_METRICS`): full reports, skew, power. bazel-orfs skips it by
  default (0158) and builds `<stage>_report` on demand (#1543).

## Silent wrong answers

- **check_setup**: the count in `2_1_floorplan.log` is not enough; a
  register clocked only on the edge it does not launch on was invisible
  (OpenSTA #455, merged; in OpenROAD since the 2026-11-07 bump). An ICG with its
  enable tied high left flops untimed (fixed upstream). `check-setup`
  skill.
- **WNS is often set by the SDC, not the logic**: of 51 ORFS designs, an
  I/O budget or clock choice sets WNS in 22 (bazel-orfs #1386).
  `timing__fmax` includes virtual clocks (OpenROAD #11668 open).
- `write_spef` writes hierarchical cells under names that do not exist;
  over 1,000 XSTile nets read back unconnected (OpenROAD #12049 open,
  carried 0175).
- A deleted net leaves dangling exceptions `-through` it (carried 0210);
  `write_sdc` crashes after deleting an instance from a merged false path
  (OpenSTA #444 open).
- An abstract written at grt was timed with placement parasitics (fixed,
  ORFS #4688). A cts abstract is ~28 % pessimistic vs grt with the same
  worst paths.

## History

- Sharding the ConcreteParasitics lock (`find_delays` 60.4 -> 21.5 s,
  parallaxsw/OpenSTA #522) was closed for the maintainer's lock-free
  rewrite, which then needed OpenROAD-side entry creation.
- The maintainer prefers algorithmic fixes in his own design over
  constant-factor rewrites: a short body, a pasteable smoke test and a
  scaling table is the shape that lands.
