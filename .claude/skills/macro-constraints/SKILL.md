---
name: macro-constraints
description: >-
  How to constrain a hardened macro or block: only register-to-register paths can fail
  timing closure, boundary paths are optimization targets written with set_max_delay, and
  set_input_delay/set_output_delay cannot be written at all without assuming a clock
  insertion latency. Use before editing a design's constraints.sdc, when a block's WNS is
  dominated by boundary paths, or when someone proposes input/output delays for a macro.
---

# macro-constraints

`flow/platforms/asap7/constraints.sdc` is right. The advice you will find
everywhere else, that a hardened block needs `set_input_delay` and
`set_output_delay` describing its surroundings, is wrong for this flow, and
the reasons are worth knowing before you spend a day acting on it.

## The three facts the platform file rests on

**Only a register-to-register path can fail timing closure.** Everything
else is an optimization target. A block's input-to-register, register-to-output
and input-to-output paths are *segments* of register-to-register paths that
exist at the parent, and the parent times them end to end, through the
block's liberty model, the parent's wire, and the next block. That is where
the check belongs and where it happens. Missing an optimization target is
not a closure failure, and the regression checks cannot tell you which of
the two you are looking at, so you have to know.

**`set_input_delay` cannot be written without assuming clock insertion
latency.** Its value is relative to the clock insertion point, which is the
time at the block's clock pin. You do not know that when you write the
constraints, it changes when the clock tree is built, and baking a guess
into the block ties the block to a parent it has not been placed in yet.
`set_max_delay -ignore_clock_latency` says the same thing about the paths
that matter without asserting anything about the tree.

**No input delay means no hold buffers at the boundary**, which is what you
want in a block whose surroundings are not yet fixed.

## What to do instead

Write the boundary as optimization targets, over-constrained, and refine per
design:

```tcl
set_max_delay -ignore_clock_latency $in2reg_max  -from $non_clk_inputs
set_max_delay -ignore_clock_latency $reg2out_max -to   $outputs
set_max_delay -ignore_clock_latency $in2out_max  -from $non_clk_inputs -to $outputs
```

The platform defaults each to 80 ps when the design says nothing, a figure
for a small macro. On anything larger that is an impossible target, and an
optimizer chasing it upsizes cells and inserts buffers whose power your
design then carries. Set the three explicitly, as a fraction of the period.

## Reading a block's WNS

A hardened block's worst slack usually is not a closure number. Separate the
path groups before you quote it:

- register to register, inside the block: this one can fail closure, and it
  is the block's own frequency.
- input to register, register to output, input to output: optimization
  targets. A violation here may or may not become a parent-level closure
  failure, and the parent's own run is what decides.

Quoting a block's overall WNS as "the block runs at N ps" without that split
is how a study ends up chasing an optimization target for a week.

## When the budgets do look wrong

Two blocks that talk to each other are each given a fraction of the period
for their side of the interface, and the parent's wire between them is
charged to neither. If both fractions are large, the parent's path through
them cannot close even when both blocks hit their targets exactly. That is
worth knowing, and it is still not a reason to reach for input and output
delays: it is a reason to choose the fractions with the interface in mind.
It is also rarely the thing in front of you. Fix the model artefacts first,
the ones that move the number by nanoseconds, and come back to the boundary
fractions when the design is closing within a few hundred picoseconds.
