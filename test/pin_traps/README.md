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
loop: never worse than own, and on a trap whose answer is a block's pins,
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
| 1 | `face_away`: a block's free pins follow its logic to the side away from the parent's | 9 187 | 2 201 | 2 232 | 2 185 | |
| 2 | `both_own`: two blocks, each its own, neither facing the other across a 4.32 um gap | 13 424 | 7 249 | 7 579 | 7 411 | XiangShan inventory entry 13 |
| 7 | `flip`: the parent mirrors a block rather than ask for pins; 14 of 64 pins land off its tracks | 4 628 | 4 340 | 3 354 | 3 302 | `macro_anneal.flip_legal` |
| 8 | `wide_pins`: pins two wire widths wide; pin access stops on DRT-0073 | DRT-0073 | ok | | | entry 12 |
| 9 | `narrow_channel`: a channel sized for the wires has no rows for the parent's registers | 13 771 | 4 459 | 9 207 | 9 247 | entry 5 |
| 10 | `split_logic`: partners side by side cut the parent's logic in two (overflow) | 23 738 (697) | 18 447 (0) | 17 201 (196) | 17 333 (401) | entry 31 |
| 11 | `tidy_row`: register files in a row, away from their owners (overflow) | 11 325 (71) | 4 001 (0) | 10 928 (0) | 8 867 (6) | entry 53 |
| 12 | `random_io`: today's flow, every pin free, macros placed against random pins | 6 112 | 4 001 | 6 088 | 6 049 | ORFS patch 0077 |
| 13 | `aspect`: a square core twenty blocks cannot tile; the macro placer refuses it (MPL-0065), and places all twenty on 100 x 78 um of the same area | refused | 20 of 20 | | | ORFS #4681 |
| | `mini_top`: traps 1, 9 and 10 in bands of one die | 46 730 (166) | 28 787 (0) | 29 370 (70) | 26 960 (67) | |

Trap 7 shows the mirror's geometry, not a failure: the parent's pin
access still finds the 14 off-track pins. In trap 8 the pin it stops on is
the block's clock pin, which the pin placer put beside the first wide pin,
as XiangShan's one pin per block.

Traps 1, 2 and 7 are answered by a block's pins, and the loop reaches the
hand answer in one round. Traps 9 to 12 are answered by where the parent
puts its blocks, which the pin loop does not move: the pins help there and
do not reach the hand answer.

## Not traps, and why

- **3, shortest wire and the worst overflow** (entry 35). Pins bunched in
  front of the parent logic they feed are the shorter wire (21 599 against
  35 198 um, 512 pins), but at this scale asap7's six routing layers carry
  them without overflow, at placement densities up to 0.95. Parked after
  four revisions.
- **6, a generous outline** (entry 42). With the pins fixed, wire hardly
  depends on the outline (4 859 against 4 390 um), and the die areas were
  set by hand in both arms: the trap measured nothing the flow did.
- **4, a selfish block** (entry 35, CoupledL2's pins): needs a timing
  probe and a block whose period moves with its pins. Not attempted.
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
