---
name: surgery
description: >-
  Tell a surgery problem from a placement problem: a period, area or flow problem whose fix
  is a function-preserving change to the RTL's structure (logic moved across a hierarchy
  boundary, storage given a module of its own, constants folded across a kept boundary, a
  clock gate mapped, a simulation construct removed, a per-instance decode hoisted, ports
  packed, a compare of a sum done without the adder) and that no floorplan, pin assignment,
  placement density or tool knob can fix. The nine classes seen on real designs here, the
  sign of each, the rules a surgery follows (function kept, checked by LEC or simulation
  with a negative control, no register added, carried as SYNTH_VERILOG_SURGERY), and what is
  not surgery. Use when a worst path crosses a hardened block from an input pin to an output
  pin, when a kept module boundary cuts a cone, before proposing a placement or pin fix for
  a path whose logic is the problem, and before writing or reviewing an RTL edit.
---

# surgery

Most period problems on a large design are where things sit: a block's
pins, its outline, the parent's floorplan, the placer's density. Those
are placement problems; the pin traps of the study in #1294 show a dozen
of them. Some are not. When the logic itself is on the wrong side of a boundary, or a
boundary hides what the tools would otherwise do, no placement removes
it: the fix is surgery, a change to the RTL's structure that keeps its
function.

Surgery in this flow is `SYNTH_VERILOG_SURGERY` (ORFS #4649): a
script that edits copies of the sources before synthesis, so vendored RTL
stays as upstream has it and the change is on the books next to the
design's config. XiangShan's are the same thing done once for every
part: a chain of scripts over the elaborated core that every flow reads
(`test/coremark_joule/designs/asap7/xiangshan/surgery/`). A surgery is
either a change the RTL might make for a tapeout, or a stand-in for a
feature yosys or OpenROAD does not have.

## The test: would any placement fix it?

Ask before choosing a fix. Hold the blocks where they are and ask what a
better placement could save; if the answer is "the path still runs
through that logic", it is not a placement problem.

- **Look at the worst path's pins.** A path that enters a hardened block
  on an input pin and leaves on an output pin crosses an in2out arc of
  the block's timing model. With odb-debug, `worst_paths` lists the pins;
  the study in #1294 has a probe that names such blocks for every arm
  (`test/pin_traps/probe.tcl`, `timing.in2out_blocks`).
- **Look at what the boundaries hide.** A kept module (`SYNTH_KEEP_MODULES`,
  a hardened block) is a wall for constant propagation, ABC's
  restructuring and yosys's memory inference.
- **Build the miniature.** The in2out trap of #1294 is the shape: the
  same placement in both arms, the RTL as written against the RTL after
  surgery, 450.7 against 316.6 ps, and yosys proving the two parents
  equivalent.

## The classes seen here

Nine classes, each seen on a real design in this repository, with the
sign that gives it away. The plausible ones not seen, and the ones
measured negative, are below.

1. **Storage without a module of its own.** An array inline in a big
   module, or a bank of separate registers, has no module for
   `AUTO_MEMORIES_REGFILES` to replace, so it stays flops behind wide
   muxes. Sign: a register file's worth of flops and a mux tree where
   the design has a memory. Surgery: move the array into a module and
   instance it where it was (tinyRocket, swerv, cva6, coralnpu: ORFS
   patches 0097-0099, 0103, 0123; XiangShan's Ftq queues, RenameBuffer
   and RobEntryFile). The most frequent class.
2. **Constants behind a kept boundary.** Generated RTL leaves constants
   on instance connections, and yosys folds them only where it flattens.
   Sign: inputs every instance ties to one literal, outputs yosys proves
   constant. Surgery: drop the port, declare the literal inside
   (XiangShan, 2,382 ports in five rounds:
   `test/coremark_joule/designs/asap7/xiangshan/surgery/`).
3. **A clock gate the timer cannot see as one.** A behavioural gate (a
   latch and an AND) is clock as data to STA; a gate whose enable is
   tied high leaves its registers untimed. Sign: a worst path through a
   latch in a clock path, registers `check_setup` reports unclocked.
   Surgery: map the gate onto the platform's ICG, fold constant enables
   (XiangShan Utility patch 0010; Frontend's 14.1 ns path was the
   behavioural gate's latch, `ideas/xiangshan-timing.md` entry 25).
4. **Simulation and FPGA constructs.** `bind`s of verification layers,
   random initialisation, a memory model a define turns into the wrong
   thing for this PDK (coralnpu: a fakeram without the write mask wrote
   all 16 bytes of every masked write; ORFS patch 0102). Sign: the flow
   refuses the construct, or worse, accepts it. Surgery: remove it, or
   replace the model with the RTL the memory flow expects.
5. **The same decode in every instance.** Hundreds of kept instances,
   each comparing its constant index against the same broadcast
   pointers, are hundreds of copies of a decoder ABC never sees as one.
   Sign: thousands of identical comparators in kept cells (XiangShan's
   Rob, 6,417 nine-bit compares, entry 9). Surgery: decode once in the
   parent and hand each instance its bit (`ideas/potential-report.md`:
   589.6 ps kept, 444.4 flattened, 387.2 decoded in the parent).
6. **A cone cut by a kept boundary.** Hierarchy kept for synthesis
   runtime or for hardening cuts a combinational cone in two, and
   neither side can be restructured with the other. Sign: the worst
   path's logic straddles a kept module's ports. Surgery: move the cone
   to one side, or cut elsewhere; classes 2 and 5 are special cases.
7. **An in2out path through a hardened block on the parent's worst
   path.** The parent's path enters a block, runs through its logic with
   no register, and leaves: the block's place in the die is set by its
   own interface, so the path's wire to it and back is fixed. Sign:
   `in2out_blocks` on the worst path (XiangShan: Region_1's write-back
   arbiter, 419 ps of entry 26's worst path; 751 ps through
   VecRegionModule in entry 44's census). Surgery: move the through
   logic into the parent, or move the cut so the logic lands on one side.
   No register added. On ORFS's asap7/aes-block the hardened `aes_sbox`
   is combinational, and in every arm of #1294's aes-block runs the worst
   path crosses one; a pin or block move there leaves the period within
   noise. #1294's in2out trap is the miniature.
8. **Ports by the hundred thousand.** A kept cell instanced hundreds of
   times, each with hundreds of ports, makes hierarchical linking
   string-keyed and slow (XiangShan, 156k ports, 18 minutes, entry 6).
   Sign: the flow's runtime, not the period. Surgery: pack the shared
   inputs into one bus (XiangShan patch 0007).
9. **A sum computed only to be compared.** The RTL adds two operands
   and compares the sum with a third, `A + B == K`, and synthesis builds
   the sum first: yosys's `share` merges an adder written for the
   compare alone into a neighbour whose operand is muxed by a late
   signal, so the compare waits for that signal, and ABC maps the wide
   compare as a chain once the module meets its own target. Neither
   sees that the compare needs no sum. Sign: on the worst path, an adder
   behind a late select, then a wide `!=` into one bit; a second adder
   written for the compare is merged back. Surgery: per bit, the carry
   the sum needs, `Need = A ^ B ^ K`, against the carry the bit makes
   with it, `Made = A & B | (A | B) & ~K`; the sum is `K` exactly when
   `~Need[0] & Made[n-2:0] == Need[n-1:1]`. The adder stays for whatever
   else reads the sum (XiangShan's BranchUnit and JumpUnit mispredict
   compares, `surgery/xs_bju_surgery.py`: the parent's worst path into
   Frontend 1,461.6 to 1,372.3 ps post-synthesis, ResolveQueue's family
   1,135.7 to 908.4 ps).

A small one: a boundary kept in the RTL so SDC names resolve, where the
synthesis knob renames the module (ORFS asap7 mock-cpu,
`(* keep_hierarchy *)` on fifo1).

## Plausible, measured negative, or not surgery

- **Duplicating a high-fanout driver.** Function-preserving when the
  driver is logic; a register duplicated is a register added. Plausible,
  not seen: XiangShan's 1,410-fanout enables were handled by buffering
  (entry 1).
- **Peeling a block's boundary flops into the parent.** Moves registers
  rather than adding them; paid on miniatures (881 to 396 ps) and found
  no target among XSTile's 1,000 worst endpoints once the clocks were
  balanced (entry 41). Measured negative.
- **A pipeline register** (coralnpu's EX/MEM address register, ORFS
  #4653) adds a register and changes cycle behaviour. It is not surgery
  by this definition, and `dogfooding` forbids it unless the human
  overrides, as they did for coralnpu.
- **Multicycle and false-path exceptions** are not a fix at all
  (`dogfooding`).
- **Flow defects** (an unbuffered clock pin on an abstract, PDN supplies
  of dont_touch cells: carried patch 0124, and ORFS's mode macro stop) are fixed in the
  flow, not the RTL.

## The rules

- **Function is kept.** Every surgery here is checked: kepler-formal LEC
  (`test/lec/lec.bzl`'s `lec_test`) or simulation against the original,
  and each check has a negative control, a broken surgery that must fail.
  A check that cannot fail proves nothing, and neither does one that
  fails for another reason: the control checks that kepler-formal
  reported the outputs nonequivalent, not that it stopped on an input it
  could not read. kepler-formal is combinational: a surgery keeps the
  registers and their names, which is the rule anyway (no register
  added), and proofs stay at module size until its scaling fixes
  (kepler-formal #267-#272) are in. yosys's `equiv_*` passes are too slow
  on real designs, and the guard refuses them; #1294's yosys proofs
  predate the rule.
- **The hazard is an unfaithful replacement.** A generator that read
  FltRegionModule's register file combinationally from its address port,
  where the RTL registers it, made a 1,161 ps in2out path that does not
  exist; LEC found it (entries 46 and 47). A register-file port
  connected under a `when` is another: XiangShan patch 0002's
  `RegVecFile.read` inside the Ftq's train `when` gated the read address
  by the fire, a mux ahead of a 612 ps read that the `Reg(Vec)` it
  replaced never had; `read` now stops under a `when`. Before treating an
  in2out path as class 7, check that the logic on it is the RTL's.
- **No register is added** unless the human says so for that change.
- **Stop on what is not recognised.** A surgery script names the shape it
  expects and fails on anything else, so a new upstream version reapplies
  or stops where upstream moved, never silently skips.
- **The RTL stays as written.** Designs are what they are for their own
  reasons; a surgery is the flow's, disclosed next to the design, and the
  vendored source stays byte-identical to upstream.
- **Measure what it bought.** A surgery's README or PR gives the number
  before and after, with the placement held, so the gain is the
  surgery's and not the floorplan's.
