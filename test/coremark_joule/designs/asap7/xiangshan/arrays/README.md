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
| find | `entries.py` | entries are word *i* of arrays of equal length; each entry's cone is a structural signature, and constants, shared bits and `x == K` / `x != K` comparisons are decided across entries (the same, the entry's number, or its bank's) |
| extract | `extract.py` | the template entry as `<Block>Entry`, instanced per entry; each index comparison decoded once per distinct operand |
| prove | `check.py` | registers and blackboxes as cut points, a yosys miter, ABC's `iprove`; a negative control (one register's D-mux swapped) must come out different |
| swap | `substitute.py` | the core with each extraction in place of its block, for the XSTile flows (`../README.md`, "The arrays") |

What the front end handles: duplicate cells merged, private port buffers
seen through, an entry's read side (its compare against a query, its
contribution to a reduction across entries) kept in the cell, arrays
that differ between entries left inline, a bank's pointer decoded once
per bank, blackboxes kept as instances. What it does not yet: threshold
comparisons (`x >= K`, VirtualLoadQueue) and read cones that differ
between entries (LoadQueueRAW).

## Targets

```
bazelisk test //test/coremark_joule/designs/asap7/xiangshan/arrays:features_test
bazelisk build //test/coremark_joule/designs/asap7/xiangshan/arrays:<Block>_extracted
bazelisk build //test/coremark_joule/designs/asap7/xiangshan/arrays:<Block>_grt_qor
bazelisk test //test/coremark_joule/designs/asap7/xiangshan/arrays:<Block>_check_test
```

`features_test` runs every step on an 8-entry CAM in seconds.
`<Block>_grt_qor` is the extracted block through global route with
setup repair at CTS and global route off (XSTile's ~2,000 ps), its
period in the JSON.
`<Block>_check_test` and `<Block>_control_test` prove an extraction and
its negative control; they are manual, the Rob's takes over an hour.
The Rob's flow is `../rob_array:RobEntries`.

The flows read the extraction through slang and fold the entry cell's
copies (`../fold_entries.tcl`), as XSTile's flows do, except where the
period at global route came out worse that way: those stay on yosys's
frontend (`YOSYS_FRONTEND` in `BUILD.bazel` has the numbers).
