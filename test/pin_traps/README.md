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
| 11 | `tidy_row`: register files in a row, away from their owners (overflow) | 11 325 (71) | 4 001 (0) | 10 665 (0) | 8 838 (0) | entry 53 |
| 12 | `random_io`: today's flow, every pin free, macros placed against random pins | 6 112 | 4 001 | 7 132 (575) | 6 331 (117) | ORFS patch 0077 |
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
| `tidy_row` | 11 325 (71) | 11 406 (0) | 11 717 (0) | 11 807 (30) | 4 001 (0) |
| `random_io` | 6 112 (1) | (own) | 7 132 (575) | 6 331 (117) | 4 001 (0) |
| `split_logic` | 23 738 (697) | refused | | | 18 447 (0) |

The macro placer alone lands where own's local rule does, and feeding
it the pins back does not converge on the hand answer: it swings, and
on `narrow_channel` round 1 doubles the wire. On `split_logic` it places
nothing: blocks the core's height do not fit with or without a channel
(MPL-0006), and on a die one row band taller it cannot align a block's
M5 pin with the track grid (MPL-0005). `narrow_channel`'s mpl arm has
that taller die and no channel too. None of these rounds is claimed by a
test; they are what a joint step inside the macro placer has to beat.

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
