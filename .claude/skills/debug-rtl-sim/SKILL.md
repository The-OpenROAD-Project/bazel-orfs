---
name: debug-rtl-sim
description: Debug an RTL or gate-level simulation that hangs, times out, produces no output, or computes the wrong answer, without dumping logs or waveforms into context. Covers the cheapest-first ladder (which gate failed, how the run stopped, a bounded fetch trace, bounded disassembly, reduce to the smallest failing case, and only then a windowed waveform), the harness properties that make each rung possible (distinct exit codes, a cycle budget, a probe port, the program as a runtime plusarg), and why a plausible-looking number from a broken configuration is the failure mode to fear most. Use when a simulation "just hangs", when a core produces no output, when a workload passes on one configuration and not another, or before reaching for a waveform.
---

## The rule

**Never read a raw simulation log or waveform into context.** A CoreMark-scale
run produces hundreds of megabytes to yield a dozen useful lines, and the
dozen lines are reachable directly. Every rung below is bounded output:
tens of lines, chosen before the run.

This is not only about context. Reading a large log encourages pattern
matching on whatever scrolled past, and the bug is usually in what did
*not* get printed.

## The ladder

Work down it. Each rung is cheaper than the next and most failures stop
at rung 2 or 3.

### 1. Which gate failed?

A simulation harness should have at least two gates, and the split is the
diagnosis:

- a **smoke gate** -- does the design boot and execute anything at all?
- a **workload gate** -- does it compute the right answer?

A design that fails the smoke gate has a boot, wrapper or memory-image
problem. One that passes it and fails the workload gate has something
else entirely. Without the split, both look like "no output".

If there is no smoke gate, write one before debugging further. It pays
for itself immediately. Make it check a **read-back**, not just output:
printing a constant string exercises no load path, so a broken byte
enable or a mis-wired read is invisible. A loop with a known sum
(`0+1+...+99 == 4950`) catches it in one character of output.

### 2. How did the run stop?

Three endings, and they must be distinguishable from the exit code alone:

| ending | means |
|---|---|
| halt written | the program ran to completion; check the answer |
| trap / fault | the design and the program disagree about the ISA or the memory map |
| cycle budget exhausted | it never reached the end -- but see rung 3 before calling it a hang |

A harness that returns the same code for all three forces a rerun to
learn what already happened.

Not every core reports faults on a pin. Where none exists, put the
reporting in software: point the exception vectors at a handler that
writes a marker and stops. A fault then appears as a character in the
captured output and a clean halt, instead of vectoring somewhere silently
and looking exactly like a hang.

### 3. Is it stalled, or just doing too much work?

These look identical from outside and have nothing in common.

Add a **bounded execution trace**: a small ring buffer of the last N
*distinct* fetch addresses with their cycle numbers, printed when the run
stops without halting. Recording only transitions means a held address is
one entry, so N=16 covers a loop body rather than a dozen cycles of one
stall.

Read it as:

- **one or two addresses repeating** -- genuinely stuck; go to rung 4.
- **addresses advancing at about one per cycle** -- the design is fine and
  the *program* is doing far more work than expected. Look at what the
  software is doing, not at the hardware. A stubbed timer that sends a
  benchmark into a self-calibrating loop will do this.
- **address 0, or the reset vector** -- a fault with no handler
  installed, restarting the program forever.

This rung needs a probe port on the wrapper carrying the fetch address
out to the harness. It costs one wire and it is simulation-only.

### 4. Bounded disassembly

Look up ±20 instructions around the address, never the whole program:

```sh
<toolchain>/bin/<triple>-objdump -d \
    --start-address=0x<addr-0x40> --stop-address=0x<addr+0x40> program.elf
```

Build the ELF with the same flags the failing target uses, or the
addresses will not line up.

### 5. Reduce to the smallest failing case

If rungs 1-4 have not answered it, stop reasoning about the large
workload. Write the smallest program that fails and run it. This is
almost always faster than one more hypothesis, and it converts a vague
failure into a specific one.

Bisect along whatever differs between a working and a failing
configuration -- ISA variant, optimisation level, one parameter -- and
change one thing at a time.

### 6. Only now, a waveform

And windowed: a bounded cycle range around a known failure cycle,
filtered to named signals. If you do not yet know the failure cycle,
rungs 1-5 were skipped.

## Harness properties that make this possible

Build these in before you need them:

- **Distinct exit codes** for halt, trap and budget exhaustion.
- **A cycle budget** with a default, so a broken run fails instead of
  hanging a build forever.
- **A probe port** for the fetch address, and a ring buffer in the
  harness that prints on failure.
- **The program as a runtime argument**, not a build input. One simulator
  binary then runs every program, which matters most for gate-level
  simulators, where the build is the expensive part.
- **Captured output as a declared file**, separate from the cycle count,
  so a failing run still leaves both behind to read.

## The failure mode to fear

**A broken configuration that produces a plausible number.**

A worked example from this repository. A core was wired with its boot
address tied to 0, but that core fetches its first instruction from
`boot_addr + 0x80` and places its exception vectors at `boot_addr`. It
was therefore starting 0x80 bytes into `.text`, on whatever instruction
happened to live there. Two ISA variants ran forever. The third limped
through the benchmark to a result within a few percent of the core's
published figure.

Had only the core's native ISA been run, the number would have been
recorded and believed. What exposed it was measuring a second
configuration that had no independent reason to disagree.

The lesson is not "check boot addresses". It is that agreement with a
published number is not evidence of correctness, and a study should
include at least one configuration whose answer is predictable for
reasons other than the one being measured.

## What not to do

- Do not patch on a hypothesis and re-run to see if it helped. Two
  changes in flight and you can no longer attribute the outcome. If a
  change is right on its own terms, keep it -- but say plainly that it
  was not the bug.
- Do not treat "it finished" as "it is correct". Gate on a checksum the
  workload computes, not on termination.
- Do not start with a waveform.

## When the RTL is right and the netlist is not

If a design passes its gates in RTL and fails after synthesis, or behaves
differently between synthesis and a later stage, the question is
equivalence rather than simulation: logical equivalence checking (LEC)
between RTL and netlist, or sequential equivalence checking (SEC) across
a transformation. Nothing in this repository wires that up today, so it
is a tool to reach for deliberately rather than a target to run.

For failures inside OpenROAD itself rather than in a simulation, use the
`openroad-debug` skill instead.
