# Pin traps

A pin trap is a parent and its hardened blocks in which a choice that is
right for one part, made by that part alone, is pathologically wrong for
the whole. Each trap is one concern, built in arms that differ only in
that concern:

- **own**: today's flow. Each block built alone, its free pins where its
  own placement puts them; the parent's blocks where the trap's local
  rule puts them.
- **hand**: the answer, written by hand.
- **r1, r2**: rounds of the pin loop, each block's pins written by
  `pins_from_parent.tcl` from the previous round's placed parent (r0 is
  own).

Every arm is measured by `probe.tcl` on the placed block and the placed
parent: a global route with congestion allowed and no repair iterations,
the side every pin landed on, block pins off the parent's tracks, and
optionally pin access. `<trap>_test` checks the own and hand arms against
bounds worked out from the trap's geometry (the docstrings in
`trap_test.py`), so a trap is something to develop against only once its
own arm is caught and its hand arm is out. `<trap>_loop_test` checks the
loop: never worse than own (within 2 %), and on a trap whose answer is a block's pins,
round 1 within a tenth of hand.

```sh
bazelisk test //test/pin_traps:all
```

Every flow is asap7, a few hundred cells per block; each stage takes
seconds.

## The traps

Block + parent global-route wirelength in um, and the parent's overflow
where it is the signal.

| # | Trap | Own | Hand | r1 | r2 | Source |
|---|---|---|---|---|---|---|
| 1 | `face_away`: a block's free pins follow its logic to the side away from the parent's | 9 187 | 2 201 | 2 228 | 2 252 | |
| 2 | `both_own`: two blocks, each its own, neither facing the other across a 4.32 um gap | 13 424 | 7 249 | 7 333 | 7 286 | XiangShan inventory entry 13 |
| 4 | `selfish`: trap 1 with a block better off alone: its own pins are a third of the hand answer's wire inside it (1 383 against 4 054) | 9 979 | 4 753 | 4 739 | 4 793 | entry 35, CoupledL2's pins |
| 7 | `flip`: the parent mirrors a block rather than ask for pins; 14 of 64 pins land off its tracks | 4 628 | 4 340 | 3 328 | 3 207 | `macro_anneal.flip_legal` |
| 8 | `wide_pins`: pins two wire widths wide; pin access stops on DRT-0073 | DRT-0073 | ok | | | entry 12 |
| 9 | `narrow_channel`: a channel sized for the wires has no rows for the parent's registers | 13 771 | 4 459 | 9 215 | 9 171 | entry 5 |
| 10 | `split_logic`: partners side by side cut the parent's logic in two (overflow) | 23 738 (697) | 18 447 (0) | 17 366 (323) | 17 295 (488) | entry 31 |
| 11 | `tidy_row`: register files in a row, away from their owners (overflow) | 11 332 (66) | 3 996 (0) | 10 674 (0) | 8 892 (0) | entry 53 |
| 12 | `random_io`: today's flow, every pin free, macros placed against random pins | 6 285 | 3 996 | 6 848 (385) | 6 310 (0) | ORFS patch 0077 |
| 13 | `aspect`: a square core twenty blocks cannot tile; the macro placer refuses it (MPL-0065), and places all twenty on 100 x 78 um of the same area | refused | 20 of 20 | | | ORFS #4681 |
| | `in2out`: the parent's worst path runs through a block's adder from input pin to output pin; the hand arm is the RTL after surgery, the adder in the parent (minimum period, ps) | 450.7 | 316.6 | | | entry 26 |
| | `mini_top`: traps 1, 9 and 10 in bands of one die | 46 730 (166) | 28 787 (0) | 29 237 (68) | 27 166 (137) | |

Trap 7 shows the mirror's geometry, not a failure: the parent's pin
access still finds the 14 off-track pins. In trap 8 the pin it stops on is
the block's clock pin, which the pin placer put beside the first wide pin,
as XiangShan's one pin per block.

`in2out` is a surgery problem, not a placement one: the blocks are
placed alike in both arms, and the hand arm's RTL is own's with the adder
moved from block b into the parent, proven equivalent by yosys
(`in2out_equiv_test`, with a negative control that breaks the adder and
must fail). The `surgery` skill says how to recognise such problems.

A round's pins follow the placement before it, and that placement has
differed between two machines: round 2 of `tidy_row` built here and, on
CI, wrote a 0.72 um stretch at a side's end that stopped the pin placer
on a bare `vector` error. The loop's stretches are now at least 2 um,
two pin pitches per pin where the side has room, and clear of the
corners. Why the placements differ is not known.

Traps 1, 2, 4 and 7 are answered by a block's pins, and the loop reaches the
hand answer in one round. Traps 9 to 12 are answered by where the parent
puts its blocks, which the pin loop does not move: the pins help there and
do not reach the hand answer.

## The joint loop: the macro placer in every round

On the traps answered by where the parent puts its blocks, the arm `mpl`
lets OpenROAD's macro placer place them, from own's blocks; rounds
`mpl_r1`, `mpl_r2` rebuild every block with the pins the last placement
gave it, feed the parent's free ports back where they ended, and run the
macro placer again. On `random_io` own is that arm already, so its r1
and r2 are joint rounds. Block + parent wire in um, parent overflow in
brackets:

| Trap | Own | Macro placer | Round 1 | Round 2 | Hand |
|---|---|---|---|---|---|
| `narrow_channel` | 13 771 (147) | 12 989 (321) | 23 835 (943) | 11 177 (228) | 4 459 (87) |
| `tidy_row` | 11 332 (66) | 11 522 (32) | 11 723 (0) | 11 633 (380) | 3 996 (0) |
| `random_io` | 6 285 (0) | (own) | 6 848 (385) | 6 310 (0) | 3 996 (0) |
| `split_logic` | 23 738 (697) | 23 767 (971) | 12 768 (0) | 12 780 (0) | 18 447 (0) |

On the small rung the macro placer alone lands where own's local rule
does; it sees each parent as one cluster (below). Fed the pins back, it
swings on `narrow_channel`, and on `split_logic` it goes below the hand
answer with no overflow. That arm is not the hand arm's geometry: the
macro placer refuses blocks the core's height (MPL-0006, its halo is at
least the minimum spacing, even with no channel), so `split_logic`'s
and `narrow_channel`'s mpl arms have a die one row band taller and no
channel, and the parent's logic has rows above the blocks that the hand
arm does not. `split_logic`'s mpl arm placed only with carried patch
0136 (below). None of these rounds is claimed by a test.

Results move with things that do not change function. Renaming the
small `tidy_row` netlist's registers (one per stage, for the large rung)
moved its numbers by up to 3 % and `random_io`'s own-arm overflow from 1
to 0. A difference of a few percent between arms is not a result here;
the traps' claims are multiples.

## The large rung

The traps are small: a few hundred cells and 20 to 150 um of wire. That
is enough for the wire ratios above, which do not depend on scale, and
not for three things that do. Wire delay: asap7's buffered wire is about
0.6 ps/um, so the in2out trap's 134 ps is a nanosecond at XiangShan's
millimetres. Congestion: trap 3 never overflowed. And the macro
placer, whose clusters have a floor of 1 000 standard cells
(`clusterEngine.cpp`, `min_num_std_cells_allowed`): a parent of a few
hundred cells is one cluster to it, so the small rung's macro placer
results above say nothing about how it places a real design.

`tidy_row_large` and `random_io_large` are traps 11 and 12 with 64-bit
files and owners of eight register stages on each side of their file,
thousands of cells each, on a 1.2 mm die. They are tagged manual:

```sh
bazelisk test //test/pin_traps:tidy_row_large_test //test/pin_traps:random_io_large_test
```

| Trap | Own | Macro placer | Round 1 | Round 2 | Hand |
|---|---|---|---|---|---|
| `tidy_row_large`, pins only | 319 061 (0) | | 318 713 (0) | 317 784 (3 318) | 114 284 (0) |
| `tidy_row_large`, joint | | 403 564 (34) | 403 246 (29) | 402 608 (61) | 114 284 (0) |
| `random_io_large`, joint | 376 697 (2 271) | (own) | 96 252 (561) | 93 532 (508) | 114 284 (0) |
| `tidy_row_mod`, joint | 319 554 (0) | 252 771 (1) | 287 490 (1 898) | 287 541 (3 250) | 114 237 (0) |

With its ports free, the joint loop goes from 3.3 times the hand answer
to below it in one round, the ports moving with the files, at about 500
of overflow where the hand answer has none (the hand answer ties each
port to its owner's edge; the loop does not). With the ports on their
edges, the macro placer puts the files 3.5 times the hand answer away
and the rounds do not move them. The macro placer clusters by the RTL's
hierarchy, and in these parents the owners are logic of the top module,
not modules of their own: it sees one flat cluster, `(root)_glue_logic`,
of the four files and 8 704 cells, and splits it with a partitioner that
knows only connectivity.

`tidy_row_mod` is `tidy_row_large` with each owner a module of its own,
kept through synthesis: the same function, the hierarchy a real design
has. With it the macro placer does better than with one flat cluster
(252 771 against 403 564, and better than own's tidy row) and still
lands 2.2 times the hand answer; the joint rounds make it worse, with
overflow. Hierarchy is part of what the macro placer was missing, not
all of it.

Two of the macro placer's refusals here are carried as fixes, each only
changing what used to stop the run:

- **0136, a flip that cannot snap** (MPL-0005, now MPL-0081). The macro
  placer mirrors blocks to shorten wires and then snaps their pins to
  the track grid. asap7's M3 tracks are at 9 + 36k dbu and M5's at
  12 + 48k; a block with pins on both, mirrored, needs its origin at
  18 mod 36 and 24 mod 48, which disagree mod 12: no location aligns
  both. The macro now keeps an orientation that snaps.
- **0137, a cluster area cannot split** (MPL-0045, now MPL-0082). A flat
  cluster of one file and 5 276 cells cannot be halved by area, the file
  outweighing the cells nine to one; it is now split by instance count.

MPL-0006, a block the core's height, is left: the halo is the macro
placer's spacing rule, and the annealer would have to treat a halo at
the core's edge differently.

## A real design: aes-block with room

`aes_room` is ORFS's asap7/aes-block, its RTL and block configuration as
ORFS has them (20 `aes_sbox`, one `aes_rcon`), at `CORE_UTILIZATION` 25
instead of 47: at 47 the blocks barely tile (ORFS #4681) and nothing can
move. `aes_room_uniq` is the same with one `aes_sbox` module per instance
(`aes_uniq.py`, proven equivalent by yosys with a negative control,
`aes_uniq_equiv_test`), so each block gets pins of its own rather than
one set shared by twenty. Both are manual smoke tests: there is no hand
answer, and own is today's flow, r1 and r2 the joint rounds. Three
departures from ORFS's configuration, in every arm alike: `--ignore-timing`
for slang (the RTL's `<= #1`), the default pin assignment rather than
`-annealing` (which leaves pins outside the rounds' regions, PPL-0107),
and the blocks timed at cts with aes's own block constraints.

Parent at placement, global route wire in um and the minimum period:

| | Own | Round 1 | Round 2 |
|---|---|---|---|
| `aes_room` | 56 778, 788.3 ps | 45 594, 767.9 ps | 51 672, 847.3 ps |
| `aes_room_uniq` | 47 463, 831.4 ps | 49 498, 844.9 ps | 47 225, 783.6 ps |

The loop runs end to end on a real design and moves nothing by a
multiple: round 1 of `aes_room` is a fifth less wire, round 2 gives some
back, and the period moves by less than a tenth either way, which here
is noise. In every arm the worst path crosses an sbox from its input to
its output (`in2out_blocks`): aes-block hardens a combinational block on
the state's every path, a surgery problem (`surgery` skill, class 7).

The rounds also hit #11819's failure on a real design's RTL: with block
pins written from an earlier placement, the macro placer's orientation
step mirrors blocks it then cannot snap (18 of 21 in round 2). Stock
OpenROAD stops on MPL-0005 there; with patch 0136 it places. With the
blocks' own pins it never did.

## Not traps, and why

- **3, shortest wire and the worst overflow** (entry 35). Pins bunched in
  front of the parent logic they feed are the shorter wire (21 599 against
  35 198 um, 512 pins), but at this scale asap7's six routing layers carry
  them without overflow, at placement densities up to 0.95. Parked after
  four revisions.
- **6, a generous outline** (entry 42). With the pins fixed, wire hardly
  depends on the outline (4 859 against 4 390 um), and the die areas were
  set by hand in both arms: the trap measured nothing the flow did.
- **5, every block square** (entries 21, 22): the cost on XiangShan was
  rows removed without a blockage, a flow defect carried patch 0086 fixes,
  not a choice a pin or macro loop makes. Not attempted.

## XiangShan

`xiangshan_flow(..., pins_out = "pins_r1")` writes every block's pin
scripts from `XSTile_place` (`XSTile_pins_r1_pins`), on the block's own
outline and on the mocked one the parent places, and the `pins_r1` arm
rebuilds every block and the parent on them. The comparison is
`XSTile_pins_r1_kpi` against `XSTile_kpi`, and the two grt stages'
route-0 overflow. The parent's global route needs a machine with more
than 128 GB; nothing of the arm has been built.

The base arm is not in the remote cache at this branch's base either. A
`//tools/cache_evidence` capture of `XSTile_place` there: 11 677 spawns,
11 521 hits, 156 misses, 606 actions not reached behind them; the first
misses are a surgery proof (`xiangshan_surgered_proven_2.json`), every
block's synthesis SDC and the register files' stages. The run is both
arms from synthesis:

```sh
bazelisk build //test/coremark_joule/designs/asap7/xiangshan:XSTile_kpi \
  //test/coremark_joule/designs/asap7/xiangshan:XSTile_pins_r1_kpi
```
