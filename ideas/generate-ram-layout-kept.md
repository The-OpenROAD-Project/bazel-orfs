# A register file's own flow keeps generate_ram's layout: what is left for generate_ram

Status: **carried, follow-ups open.** ORFS patch 0158 keeps generate_ram's
layout in a register file's own flow; the read path and pin access below
are generate_ram's to improve, not a reason to place its netlist again.

## Problem

A register file built as a macro of its own (XiangShan's nine, each a flow
whose top is the register file's module) inlined generate_ram's netlist and
placed it again with global placement: generate_ram's layout was thrown
away, about 384k cells for RenameBufferFile, 280k of them the array core
generate_ram had already arranged, and 12-15 min of global placement per
file (today's perf captures). An improvement to generate_ram's layout never
reached the flow: tuning global placement on its netlist is a local optimum.

## Idea

Keep the layout (patch 0158): the floorplan the shape of generate_ram's
outline, every generated cell FIRM where generate_ram placed it, global
placement left only what synthesis added or resized. Improve generate_ram
where the kept layout is worse than global placement's.

Measured on the 64 x 256 register file of test/regfile/macro, from a dirty
lane, not a clean build, one run per arm, both with the metrics reports and
timing-driven placement off:

| | kept layout | placed again |
|---|---:|---:|
| placement | 39-49 s | 72 s |
| CTS | 16-19 s | 44 s |
| pin access at global route | 142-145 s | 57 s |
| repair_timing at global route | 25-65 s | 8 s |
| in2out slack (600 ps budget) | -15.9 to -21.0 ps | +0.1 ps |
| in2reg slack | +72 to +81 ps | +0.6 ps |

## Follow-ups

1. **The read path.** Address to data misses its budget by 16-21 ps with
   generate_ram's periphery where generate_ram put it; global placement's
   meets it. generate_ram placing its read periphery for the ports, not
   only for the array, is the candidate.
2. **Pin access.** Two and a half times longer on the kept layout,
   repeatably. Unexplained; a guess is that generate_ram's cells sit at
   offsets to the routing tracks that make each instance's pin access its
   own. XiangShan's register files skip pin access (their abstract is
   written at global route), so it costs them nothing today.

## Impact

Turnaround of every register-file macro; measured on one XiangShan file
when its clean build is in (see the PR).

## Effort

Small for the measurements; medium for a generate_ram change, which is
OpenROAD's (carried here first, upstream on the human's order).
