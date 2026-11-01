# arrays: XiangShan's arrays found, extracted and proven

generate_array's front end on real RTL. A block such as the Rob holds
an array the RTL never wrote as one: 352 entries, each the same
registers and logic, each written where a broadcast index equals its
own number. Synthesis and placement see 352 copies of everything,
including 352 copies of every index comparison. The front end finds the
entries, writes the block as one entry cell instanced per entry, and
decodes each index comparison once in the block.

| Step | File | What it does |
| --- | --- | --- |
| proc | `proc_json.py` | the block after yosys's `proc`, as JSON; named modules stay blackboxes |
| find | `entries.py` | entries are word *i* of arrays of equal length (`x`, `x_1`, ... too: firtool's vectors), an array of k·N words k arrays of the group of N where that follows one rule; each entry's cone is a structural signature, and constants, shared bits and `x == K` / `x != K` comparisons are decided across entries (the same, the entry's number, or its bank's); where that leaves entries off the rule, thresholds `x >= K` / `x < K` too |
| extract | `extract.py` | the template entry as `<Block>Entry`, instanced per entry; each index comparison decoded once per distinct operand, a threshold `x >= i + o` as bit `i + o - 1` of `(1 << x) - 1`, an ordered comparison with the index (`i > x`, `i <= x`, ...) as such a threshold, inverted in the cell where it is the complement, an `en && x == i` as bit `i` of `(1 << x) & {en}` |
| prove | `check.py` | registers and blackboxes as cut points, a yosys miter, ABC's `iprove`; a negative control (one register's D-mux swapped) must come out different |
| swap | `substitute.py` | the core with each extraction in place of its block, for the XSTile flows (`../README.md`, "The arrays") |

What the front end handles (and, where it wins, `--fanout-tree`: every input all entry cells share driven through two levels of a kept one-inverter module in the block, root and per eight entries, the clock left alone, for LoadQueueRAR, PhysicalStoreQueue, Uncache and VirtualLoadQueue, `TREE` in `BUILD.bazel`): duplicate cells merged, private port buffers
seen through, an entry's read side (its compare against a query, its
contribution to a reduction across entries) kept in the cell, arrays
that differ between entries left inline, a bank's pointer decoded once
per bank, a decoder's enable decoded with it (`en && x == i`: a write
enable, VirtualStoreQueue's serial retire carry; one wire into each
cell and the enable into the decoder alone, where it had reached all
128 cells and each link of the carry waited for its buffer tree; a
boundary bit no cell reads gets no port), blackboxes kept as instances, thresholds against the entry's
number however firtool folded them for each one (VirtualLoadQueue's
`x >= i + 1` as `x > 2`, `|x[6:2]` or `x[6]` alone), and where the
read cones differ between entries the part of them every entry has
(LoadQueueRAW's select bits, without the per-bank priority inverters,
a different number in every entry, which stay in the block).

## Targets

```
bazelisk test //test/coremark_joule/designs/asap7/xiangshan/arrays:features_test
bazelisk build //test/coremark_joule/designs/asap7/xiangshan/arrays:<Block>_extracted
bazelisk build //test/coremark_joule/designs/asap7/xiangshan/arrays:<Block>_grt_qor
bazelisk build //test/coremark_joule/designs/asap7/xiangshan/arrays:<Block>_rtl_grt_qor
bazelisk test //test/coremark_joule/designs/asap7/xiangshan/arrays:<Block>_check_test
```

`features_test` runs every step on an 8-entry CAM, on an 8-entry
queue freed below a bound (thresholds) and on a CAM with a per-bank
priority select and per-port match registers (read cones that differ,
firtool's vector names), in seconds.
`<Block>_rtl_grt_qor` is the same flow on the module as it is (no entry
cell): the A arm of the block's A/B.
`<Block>_grt_qor` is the extracted block through global route with
setup repair at CTS and global route off (XSTile's ~2,000 ps), its
period in the JSON.
`<Block>_check_test` and `<Block>_control_test` prove an extraction and
its negative control; they are manual, the Rob's takes over an hour.
The Rob's flow is `../rob_array:RobEntries`.

When a change to the front end breaks a block, two tools find where:

```
bazelisk run //test/coremark_joule/designs/asap7/xiangshan/arrays:regress -- \
    <yosys> <proc.json> <module> <workdir> [--direct]
bazelisk run //test/coremark_joule/designs/asap7/xiangshan/arrays:localise -- \
    <yosys> <proc.json> <extracted.json> <module>
```

`regress` proves the extraction with the index kept, runs its control,
writes the decoded extraction as Verilog and reads it back through
`check -assert` (two drivers on a wire fail there in seconds, not in
the flow), and with `--direct` proves the decoded form. `localise` runs
the proof per group of outputs and names the ones that differ. Paths
absolute; `<proc.json>` copied from `<Block>_proc_json` somewhere
writable. The open work is in `ideas/structured-macros.md`, "Tasks, for
agents".

The flows read the extraction through slang and fold the entry cell's
copies (`../fold_entries.tcl`), as XSTile's flows do, except where the
period at global route came out worse that way: those stay on yosys's
frontend (`YOSYS_FRONTEND` in `BUILD.bazel` has the numbers).

## What the extraction buys

Against the module as it is, the same flow, single runs side by side;
the period at global route on the routes' parasitics (the probe's
`period_grt_ps`; `ideas/structured-macros.md`, "QoR inventory", has the
stages, cells, area and the placement-parasitics period):

| Block | A total min | B total min | A period ps | B period ps | verdict |
|---|---:|---:|---:|---:|---|
| PhysicalStoreQueue | 30.53 | 9.67 | 1,453.0 | 1,579.6 | dominates |
| LoadQueueReplay | 37.40 | 22.36 | 1,198.4 | 1,201.8 | dominates |
| VirtualStoreQueue | 6.04 | 3.53 | 944.7 | 910.4 | dominates |
| LoadQueueRAR | 6.59 | 4.05 | 781.3 | 818.1 | dominates |
| TLBFA | 2.69 | 2.19 | 397.0 | 320.6 | dominates |
| TLBFA_1 | 5.95 | 3.06 | 456.2 | 282.3 | dominates |
| VirtualLoadQueue | 4.48 | 3.91 | 857.6 | 847.0 | dominates |
| Rob (`rob_array:RobEntries`) | 58.07 | 52.60 | 1,379.9 | 1,212.3 | dominates |
