# XiangShan Frontend at synthesis: toward a 1,000 ps netlist

The question: how close to a 1,000 ps minimum clock period is Frontend's
synthesis netlist, what stands between it and that, and how far do the
tools get when the netlist is built rather than left to ABC. Every number
is Frontend's `1_synth.odb` in an odb-debug session, the SDC at 473 ps
(unchanged), ideal clock, no wires. The period is 473 minus the worst
`reg2reg` slack; only that group can fail timing closure
(`.claude/skills/macro-constraints`). "Over 1,000 ps" counts `reg2reg`
endpoints whose worst path needs more than 1,000 ps.

Frontend's synthesis runs in 16 min at 11 GB on a 16-thread, 30 GB machine
(16 partitions); a session loads it in about 60 s.

## Results

| step | what | period | over 1,000 ps | over 950 ps | BUF cells |
|---|---|---:|---:|---:|---:|
| S0 | ABC speed script as the flow runs it | 1,265 | 16,382 | 26,375 | 146,247 |
| S1 | S0, then `repair_design -pre_placement` | 1,308 | 11,272 | 16,135 | |
| S2 | S0, `remove_buffers`: the logic with bare fanout | 164,974 | 97,287 | | 0 |
| S3 | S0, ABC's buffer trees rebuilt by `tools/fanout_tree`: at most 16 pins and 24 fF per driver | 1,282 | 7,716 | 10,767 | 95,765 |
| S4 | S3 with the four Ftq queues' liberty characterised from their own buffered, placed gates (`write_timing_model`) instead of the formula | 1,895 | 7,082 | 9,518 | 95,765 |

S3 and S4 are timed in a standalone OpenROAD session (`read_liberty`,
`read_db`, the flow's `1_synth.sdc`, the platform's `setRC.tcl`); with
the formula liberty it reproduces the odb-debug session's S3 to the
tenth of a picosecond.

## The generated register files, on their own gates

`structured_gen`'s arrays timed alone, `estimate_parasitics -placement`,
10 ps input transition, read address to read data:

| array | as generated | buffer trees (16 pins, 24 fF), by name | by position, root buffers at their driver | and a repeater every 80 um | the formula liberty says |
|---|---:|---:|---:|---:|---:|
| FtqMetaQueueResolve, 64 x 954, 8 folds | 3,625 | 1,508 | 1,312 | 1,012 | 358 |
| FtqMetaQueueRedirect, 64 x 211, 2R1W | | | | 631 | |
| FtqEntryQueue, 64 x 56, 4R1W | | | | 497 | |
| FtqMetaQueueCommit, 64 x 10 | | | | 282 | |

As generated, one address inverter drives 256 pins and 194 fF (1,382
ps, 3.3 ns of slew), a word select 120 AND2s, and the last bitline OR
the wire to a pin on the bottom edge. `structured_gen` now builds those
nets as trees (`buffering.cc`, reusing `fanout_tree`): sinks grouped by
recursive bisection of their positions, each group's load its pins plus
its half-perimeter at 0.2 fF/um, each buffer placed FIRM on the free
sites nearest what it drives as it is made, the buffers a root drives
put beside the root, and two-pin nets longer than `buffer_max_wire_um`
cut by repeaters. On Resolve that is 29,020 buffers and 6,880 repeaters
in the service columns, no buffer more than 41 um from its target. A
repeater every 40 um is slower (1,135 ps) than every 80.

What remains on Resolve is three crossings of the array at about
0.5 ps/um through the repeaters, pin to decode, the word select across
a fold, the bit down to its pin on the bottom edge, plus the OR tree.

The formula liberty is optimistic on the read arc by 2.8 times and
pessimistic on every input pin (19.8 and 38.4 fF against a single
buffer's input once the trees are built), which is why S4 has a worse
period and fewer endpoints over 1,000 ps than S3.

## The worst path at S0

`inner_bpu/io_toFtq_meta_valid` through ITTAGE and SC into the Ftq, the
read port of `metaQueueResolve` (an `FtqMetaQueueResolve`, 64 words by
954 bits, a `tools/structured_gen` macro), into
`inner_ftq/io_toBpu_train_bits_meta_mbtb_entries_1_3_rawHit`:
clock-to-output 38 ps, 12 buffers 468 ps, 18 logic cells 387 ps, the
macro's read arc 358 ps, the last two gates and setup 44 ps.

- The 358 ps is `structured_gen`'s model liberty, a formula
  (`views.cc`: read levels times 25 ps times 1.3), not a timing of the
  gates it built; the spec's `bit_folds 8` is not in it. Its pin
  capacitances are the same kind of estimate: 38.4 fF on each write
  enable, 19.8 fF on each read-address bit.
- One BUFx2 drives 123 fF, three of those write enables, at 370 ps of
  slew: ABC maps with the macro as a black box and does not see its pins.
- ABC's trees are chains: a BUFx2 drives ten loads, one of them the next
  BUFx2, so a sink at the end of a broadcast net is up to 18 buffers from
  its driver.

Over the 500 worst endpoints the path is on average 489 ps of buffers
(30 cells), 443 ps of logic (25 cells) and 312 ps in a macro. Of the
16,382 endpoints over 1,000 ps, 13,090 pass through no macro at all; by
endpoint they are in the BPU's predictors: TAGE 5,039, the ahead BTB
2,903, ITTAGE 592, SC 282.

The SRAM arrays (FakeRAM, `array_512x17` and the like) are not the
problem: 218 ps access and 50 ps setup on `array_512x17`, plausible for
asap7, and the paths out of them meet 473 ps.

## Reading

- The logic is not what sets the period. On the worst paths it is 390
  to 560 ps, 27 to 39 FO4; with clock-to-output and setup that is about
  500 to 620 ps.
- `repair_design` at S1 lowers the count but not the worst path: it
  buffers on top of ABC's chains instead of replacing them.
- The resizer cannot rebuild the trees on this netlist: `repair_design
  -pre_placement` after `remove_buffers` (S2) stopped OpenROAD with
  signal 11, hierarchical and flat reads alike, and a second signal 11
  followed `repair_design -pre_placement`, `find_timing_paths` and
  `report_checks -to` in one session. Not yet reduced to a reproducer.
- `tools/fanout_tree` (S3) rebuilds 43,616 nets in 30 s at 1.5 GB: 145,594
  of ABC's buffers out, 95,112 in, the deepest tree from 18 buffers to 3,
  and every one of the 1,550,537 sinks checked to reach its original
  driver through buffers only. It halves the endpoints over 1,000 ps.
  The worst path is still the register file's: 358 ps of formula, 556 ps
  of logic in 26 cells, 291 ps of buffers in 11, and a 64 ps
  clock-to-output where the start flop now drives its first-level group
  itself at x1.
