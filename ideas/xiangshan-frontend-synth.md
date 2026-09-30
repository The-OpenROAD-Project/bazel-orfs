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

ABC never had a delay target in these runs. ORFS passes the clock
period as `abc -script <file> -D <period>`, and Yosys hands `-D` to ABC
only through the `{D}` placeholder of its built-in and inline scripts,
not a script file (ORFS #4585, #4586). Every ABC run here, the flow's
and the variants', mapped with no target.

## Results

| step | what | period | over 1,000 ps | over 950 ps | BUF cells |
|---|---|---:|---:|---:|---:|
| S0 | ABC speed script as the flow runs it | 1,265 | 16,382 | 26,375 | 146,247 |
| S1 | S0, then `repair_design -pre_placement` | 1,308 | 11,272 | 16,135 | |
| S2 | S0, `remove_buffers`: the logic with bare fanout | 164,974 | 97,287 | | 0 |
| S3 | S0, ABC's buffer trees rebuilt by `tools/fanout_tree`: at most 16 pins and 24 fF per driver | 1,282 | 7,716 | 10,767 | 95,765 |
| S4 | S3 with the four Ftq queues' liberty characterised from their own buffered, placed gates (`write_timing_model`) instead of the formula | 1,895 | 7,082 | 9,518 | 95,765 |
| S5 | S4, each rebuilt tree's root driver held to 2.5 fF per unit of drive, the rest behind buffers | 1,897 | 6,374 | 8,527 | 192,356 |
| S6 | S4, each rebuilt tree's root driver upsized in its family instead (18,672 roots, no `xp`/`x1p` cell) | 1,847 | 5,492 | 6,560 | 95,818 |
| S6b | S6, and every other driver upsized by the same rule (39,569 more) | 1,854 | 5,480 | 6,472 | 95,818 |
| S7 | S6 with the Ftq queues regenerated with `pins_at_columns` (Resolve in 4 folds) and re-characterised | 1,649 | 5,459 | 6,544 | 95,818 |
| S8 | S7, trees of up to 32 pins and 48 fF (the SDC's own `set_max_fanout 32`) | 1,602 | 3,451 | 6,215 | 41,264 |
| S9 | S8, every driver upsized in its family | 1,608 | 2,980 | 6,087 | 41,264 |
| S9c | S9, and a driver no family member can make strong enough gets its load behind a buffer beyond 8 fF per unit of drive | 1,606 | 2,761 | 5,740 | 44,969 |
| S10 | S9, weak drivers held to 5 fF per unit of drive (16,360 nets) | 1,604 | 2,443 | 5,608 | 56,739 |
| S11a | a new synthesis, ABC's speed script without `buffer -c` (`Frontend_abc_nobuf_synth`, ORFS patch 0089), as ABC leaves it | 44,829 | 94,415 | 97,491 | 2,196 |
| S11 | S11a, every tree built by `fanout_tree` with S10's settings | **1,392** | **566** | **925** | 56,442 |

Trees of 24 pins and 36 fF land at 3,473; 32 pins with 64 fF instead of
48 changes nothing, the pin limit binds. Holding weak drivers to 2.5 fF
per unit instead of 8 puts a buffer behind 59,938 ordinary x1 gates and
is worse (4,045).

`repair_timing -setup` on S6's netlist (asap7's dont-use set, no
placement) moved the worst slack from -1,374 to -1,238 ps in 1,224
moves and about 50 minutes, 80,864 endpoints still violating, and was
stopped at its one-hour cap: at this size and this far from closure it
is not the tool for synthesis.

## Where it is at S11

With ABC mapping for delay and building no buffers, and every tree
built by `fanout_tree` (32 pins, 48 fF, drivers upsized, weak drivers
behind a buffer past 5 fF per unit of drive):

| | |
|---|---:|
| `reg2reg` minimum period | 1,392 ps |
| endpoints over 1,000 ps | 566: 436 through `FtqMetaQueueResolve`, 130 through no macro |
| the worst period not through `FtqMetaQueueResolve` | 1,110 ps |

TAGE's useful-bit update, 4,617 endpoints over 1,000 ps at S7, is gone
from the list. The worst path outside Resolve's cone is now the IFU into
the instruction buffer's `vtypeGen`: 39 logic cells 874 ps, 7 buffers
170 ps, clock-to-output 51 ps. The same 16-partition synthesis took
about 20 minutes.

## Where it was at S10

| | |
|---|---:|
| `reg2reg` minimum period | 1,604 ps |
| the worst period not through `FtqMetaQueueResolve` | **1,043 ps** |
| the worst period through no macro at all | 1,023 ps |
| endpoints over 1,000 ps | 2,443: 2,007 of them under 1,100 ps |
| endpoints over 1,100 ps | 436, every one through `FtqMetaQueueResolve` |

Everything but one cone is within 4.3 percent of 1,000 ps at synthesis.
That cone is the Ftq's training read: 26 logic cells from the BPU's
`s2_hits` into the read address of a 64 by 954-bit register file with an
asynchronous read, and the file's own 813 ps.


At S9c, of the 2,761 endpoints over 1,000 ps, most end in TAGE: its useful-bit
update, `s2_hits` through the provider choice into the useful counters'
write buffers and SRAMs. On the worst of them with no macro on the path,
at S8: 31 logic cells 727 ps, 9 buffers 246 ps, clock-to-output 58 ps,
1,046 ps. The SRAM endpoints are the same cone plus the arrays' 50 ps
setup. The period itself is still the `FtqMetaQueueResolve` read: 26
logic cells, one tree level per broadcast net, and the array's 813 ps.

From S4 on, the worst path is the same `FtqMetaQueueResolve` read: at
S6 clock-to-output 58 ps, 11 buffers 269 ps, 26 logic cells 504 ps, the
array's read 1,010 ps. The array's shape is not the lever there:
Resolve with 1, 2, 4, 8 and 16 bit folds reads in 3,148, 1,751, 1,145,
1,012 and 1,132 ps.

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

Pins: the generator packed every pin from the corner of its edge, so
the 954 read-data pins sat in the first stretch of the bottom edge and
a bit in the middle of a fold ran 150 um sideways to its pin.
`pins_at_columns` puts each data pin on the free track nearest its own
column and the addresses and enables beside the first bank's decode:

| Resolve, pins at their columns | read |
|---|---:|
| 8 folds | 851 |
| 8 folds, decode centred between the bits | 959 |
| 2 / 4 / 6 / 16 folds | 1,041 / **813** / 826 / 1,049 |
| 4 / 16 folds, decode centred | 1,184 / 1,083 |
| 4 folds, a repeater every 60 / 120 um | 836 / 818 |

Centring the decode (`decode_center`, a decoder spine) halves the word
select and moves the address farther; it loses every time. At 4 folds
the 813 ps are 304 ps in 7 repeaters, 310 ps in 9 tree buffers and 190
ps of logic: three quarters wire, at the flow's own signal RC. With the
same pins Redirect reads in 537 ps, EntryQueue in 418, Commit in 270.

Fewer service sites (20 or 28 per 8 columns instead of 40) gain 11 ps
(802 ps): a standard-cell array of 61,056 bits read asynchronously ends
near 800 ps on this flow's wire model, whatever its shape.

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

## Why the rebuilt netlist is the same design

`fanout_tree` removes only buffers and adds only buffers, and its
`Check()` proves that every sink it moved reaches the driver it had
through buffers alone: identity by construction, checked on all
2,066,737 sinks of S10. Upsizing swaps a cell for another member of its
family (the name with its drive taken out), pins checked equal; on
asap7's RVT liberty, the 60 families left after the dont-use patterns
(`xp`, `x1p`) have the same `function` on every output in every member.
No formal equivalence check was run: at 1.1 M cells it is not needed for
these two rewrites, and kepler-formal did not build here (the
`xiangshan-mbtb-wns-path` branch).

## Not in the flow yet

Everything above is measured in sessions on the flow's synthesis ODB
(`test/coremark_joule/xs_frontend_synth`); no flow target runs it yet.

- `tools/fanout_tree` is a binary on an ODB. The flow runs OpenROAD
  hierarchical and the tool creates its buffers in the top module
  without module nets; every number here is a flat read. Putting it in
  the flow means either a step between synthesis and floorplan or the
  same algorithm as an OpenROAD command, with the hierarchy kept.
- `structured_gen` still writes the formula liberty in the memories
  step, where no OpenSTA runs. The characterised liberty needs the
  generated ODB timed there, or in the generator itself, which links
  OpenROAD.
- The Ftq specs in `designs/asap7/xiangshan` do not have the buffer and
  pin keys yet, nor Resolve's 4 folds.

## Open

- **Resolve's cone.** Everything else in Frontend is within 4.3 percent
  of 1,000 ps at synthesis; this cone is 1,604 ps, 813 of them the
  register file on its own gates. A chip builds a 64 by 954-bit
  asynchronous-read file with a register-file compiler, as it builds
  the SRAMs this flow models with FakeRAM. Modelling Resolve the same
  way would be a choice about the model, not a fix in the tools, and
  it is not made here.
- **TAGE's useful-bit update**, the 1,000 to 1,100 ps band at S10
  (25 to 31 levels as ABC mapped them), is gone at S11: ABC mapping
  without `buffer -c` and the trees built afterwards took it under
  1,000 ps.
- **`repair_design`'s early sizing round and a top-level port**: found,
  fixed and carried as OpenROAD patch 0005; see "The resizer's crash"
  below.

## The resizer's crash

`repair_design -pre_placement` stopped OpenROAD on Frontend's synthesis
ODB: after `remove_buffers`, and also on the netlist of ABC without
`buffer -c`, which has nothing to remove. A build with assertions and
debug information for `rsz` and `dbSta` names it:

```
sta::dbNetwork::staToDb(const Net*): !db_net || db_net->getObjectType() == odb::dbNetObj
rsz::Resizer::insertBufferBeforeLoads(net, ...)          Resizer.cc
rsz::RepairDesign::performGainBuffering(net, drvr_pin, max_fanout = 32)
rsz::RepairDesign::performEarlySizingRound: net_db = 0, mod_net_db = net, fanout 52
```

`performEarlySizingRound` takes a driver's net as
`network_->net(network_->term(drvr_pin))` when the driver is a
top-level port, and in a hierarchical netlist that is the top module's
`dbModNet`, not the flat `dbNet` the comment above the line asks for.
Gain buffering then inserts on it. The release build takes signal 11.

The trigger is a top-level input port with more than `max_fanout` loads
in a design that keeps a module. ABC's `buffer -c` hides it behind a
buffer, which is why the flow as it runs today never meets it;
`remove_buffers`, or a synthesis that builds no buffers, exposes it.
`test/rsz_remove_buffers` (`rb_top`, N = 512: a port that 512 flops in a
kept module each toggle on) reproduces it in seconds, and `repro_test`
fails without OpenROAD patch 0005 and passes with it. The patch takes
`flatNet(term)` instead. Five other call sites in `rsz` read a port's
net the same way (`Rebuffer.cc:2129`, `Resizer.cc:1271`, `1408`, `5260`,
`6396`); none is shown to fail, and they are candidates to check.

For an upstream issue, when the human decides (not filed):

> **rsz: repair_design early sizing buffers a top-level port's dbModNet
> (assert in dbNetwork::staToDb)**
>
> In a hierarchical netlist, `RepairDesign::performEarlySizingRound`
> takes a top-level port driver's net as
> `network_->net(network_->term(drvr_pin))`, which is the top module's
> `dbModNet`. `performGainBuffering` passes it to
> `Resizer::insertBufferBeforeLoads`, and `staToDb(const Net*)` asserts
> `db_net->getObjectType() == odb::dbNetObj` (signal 11 without
> assertions). Trigger: a top-level input port with more than
> `max_fanout` loads inside a kept module, then `repair_design
> -pre_placement` (after `remove_buffers`, or on a netlist ABC did not
> buffer). Fix: `db_network_->dbToSta(db_network_->flatNet(
> network_->term(drvr_pin)))`, which the comment above the line already
> asks for. A 512-flop reproducer and the one-line patch are in
> bazel-orfs (`test/rsz_remove_buffers`, `patches/0005-...`).

## At place

Frontend through the flow's place stage, which runs its own
`repair_design`; `reg2reg` with placement parasitics, ideal clock, the
flow's formula liberty for the Ftq queues (optimistic on Resolve's cone
by about 450 ps); the same harness with `XS_PARASITICS=placement`.

| arm | what | period | over 1,000 ps | over 950 ps | BUF cells |
|---|---|---:|---:|---:|---:|
| P0 | the flow as it runs today | 5,118 | 69,636 | 71,867 | 170,915 |
| P1 | ABC's speed script without `buffer -c` (`Frontend_abc_nobuf_place`) | 4,616 | 87,795 | 90,514 | 66,922 |
| P1f | P1's netlist through a deployed floorplan and place tree, flat (`OPENROAD_HIERARCHICAL=0`), OpenROAD with patch 0005 | 4,616 | 87,795 | 90,514 | 66,922 |
| **P2** | P1f with `fanout_tree`'s netlist (S11) swapped in before floorplan | **3,139** | **55,364** | **60,208** | 77,170 |

P0 reproduces the README's 5,118 ps. Its worst path is a CSR enable
(`csrCtrl_delay.io_out_mbtbEnable`) broadcast to TAGE's SRAMs through
42 buffers, 3,712 ps, against 1,267 ps of logic. P1's is BPU's
`io_toFtq_meta_valid` into an SC SRAM through 40 buffers, 2,680 ps,
against 1,809 ps of logic; its largest stage is a BUFx2 driving 23 pins
and 93 fF. Without ABC's chains the place stage's `repair_design` builds
chains of its own: the synthesis-stage gain does not survive placement
on the endpoint count (87,795 against 69,636), and the period improves
by 10 percent.

P1f reproduces P1 exactly, so the deployed flat tree stands in for the
flow and P2 differs from it only in the netlist. **Trees built before
floorplan survive placement**: P2 is 39 percent faster than P0 (3,139
against 5,118 ps) with 20 percent fewer endpoints over 1,000 ps. Its
worst path is TAGE's `s2_readResp` into an SC SRAM: 21 buffers 1,262
ps, 31 logic cells 1,763 ps; the largest stage is a NAND2x1, not a
buffer. The place stage's own `repair_design` builds worse trees than
the ones handed to it (P1 against P2).

With patch 0005, `repair_design -pre_placement` on P1's netlist
completes (3,344 s): 1,548 ps, 643 endpoints over 1,000 ps and 1,648 over
950 at synthesis, against `fanout_tree`'s 566 and 925 in 30 s. OpenROAD's
own gain buffering, run before placement, is close to `fanout_tree` in
quality and 110 times slower.
