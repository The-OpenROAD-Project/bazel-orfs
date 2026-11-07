# cts: clock tree synthesis (TritonCTS) and the cts stage

Paths are in OpenROAD's `src/cts/`, ORFS's `flow/scripts/cts.tcl`.

## Reading the log

TechChar (CTS-0046/0047, CTS-0097 buffer types), clock nets (CTS-0008),
sink clustering and an H-tree per net (CTS-0027-0035), write to the
database (CTS-0012-0018), `repairClockNets`, then the
**LatencyBalancer** (CTS-0033/0036; useful skew CTS-0544/0545). CTS-0500
runtime. CTS-0204/0205 "Better solution may be possible": you set
`CTS_CLUSTER_SIZE`/`DIAMETER` and turned off the automatic search.

## Where the time goes

- **The cts stage is mostly `repair_timing`**, not CTS: `cts.tcl` repairs
  setup and hold with placement parasitics unless
  `SKIP_CTS_REPAIR_TIMING`. See [rsz.md](rsz.md).
- **The latency balancer timed the whole design.** OpenSTA's
  `ArrivalVisitor` copy dropped `clks_only`, so with threads the
  clock-arrival search covered every path (7.47 M -> 0.18 M paths on
  swerv when fixed). OpenSTA #462 (merged) plus OpenROAD #12147 (open;
  balancer asks only for clock arrivals) took XSTile Top CTS from
  101.8 -> 47.8 GB and 1,045 -> 609 s, byte-identical (bazel-orfs #1535,
  carried 0206/0207). The earlier CRPR-off workaround (OpenROAD #12119)
  was dropped.
- **Gated clocks each get their own tree**; their skew is reconciled only
  by the balancer's delay buffers.
- Balancing to a hard block whose abstract carries its whole unbuffered
  clock net (145 pF pin) gave 49,736 delay buffers and 2.6 h of
  legalisation. Fix: abstract blocks at cts, so the clock pin is a buffer
  (bazel-orfs #1080); then the parent's CTS balances the block trees
  (3,860 -> 2,976 ps, #1150).

## Futile, or nothing there

- **CTS is not a period lever at 1-2 ns**: OpenROAD's skew is a small
  fraction of the period; at ~600 ps clock distribution is a different
  problem from what TritonCTS does. Useful skew built nothing on the
  array toys (bazel-orfs #1444).
- CRPR on large propagated clocks grows memory superlinearly (OpenSTA
  #452 open); skipping CRPR with ideal clocks (#445) and pre-CTS (ORFS
  #4284) were closed.

## Known problems

- Hierarchical netlists: CTS connected clock pins to the flat net only,
  leaving unclocked register pins on read-back. Fixed, OpenROAD
  #11718/#11719.
- Macro insertion-delay hold races (OpenROAD #10901) traced to a
  liberty generator inventing `clock_tree_path` on SRAMs (bazel-orfs
  #1175): check the macro's .lib before blaming CTS.
- Timing models written before CTS carry the whole clock net as pin
  capacitance (8.5-32 pF): the owner's clock arrives nanoseconds late.
- Swerv CTS RSZ-1008 "-inf" under prima (CCS liberty): OpenSTA
  e419f88d, OpenROAD #12037, fixed upstream.
