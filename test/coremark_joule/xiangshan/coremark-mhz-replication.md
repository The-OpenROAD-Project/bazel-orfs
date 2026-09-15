# Replicating XiangShan's published CoreMark/MHz

**Status: open. Not blocking the energy measurement.**

## What was measured

```
cycles_3                437,712
cycles_2                317,320
one iteration           120,392
CoreMark/MHz              8.3062
```

XiangShan V3 (Kunminghu), commit `37ce1b5`, `-march=rv64gc -mabi=lp64d
-mcmodel=medany` with the study's baseline flags, CRCs correct on both
runs.

The number cross-checks against a second observable: `first_output`, the
cycle CoreMark's first character reaches the harness, differs by 120,380
between the two runs against the cycle count's 120,392. The 12-cycle
residue is accounted for -- `crcfinal` differs between a two- and a
three-iteration run (0x72be against 0x2e87), so the report prints
different characters and the tail after first output costs slightly
different work.

So 8.31 is what this configuration does. The question is why the
published figure for this core is nearer 10.

## Hypotheses, in the order worth testing

**1. ISA extensions. Expected effect: large.** The study builds
`rv64gc`, which has no bit-manipulation instructions. Kunminghu
implements Zba and Zbb, and CoreMark's list and matrix kernels lean on
exactly what those provide -- shifted-add addressing and byte/bit
operations. A published score would be built for the core it runs on.
Test: build `rv64gc_zba_zbb`, one run pair, twenty minutes each. This is
the first thing to try and the most likely single explanation.

**2. Compiler flags and version. Expected effect: moderate.** The
baseline flag set is lowRISC's, chosen so all four cores in the study are
built identically -- which is the right default for comparing
microarchitectures and the wrong one for reproducing a vendor's number.
ACM CF'25 states the same practice ("compile with the same toolchain and
optimization flags"), so uniformity is defensible; it just is not what a
headline figure does. Test: the flag sweep the study already owes, with
the per-core best reported as a second column.

**3. Configuration deltas. Expected effect: small.** This study shrinks
the L2 from 2 MB to 512 KB and the last-level cache from 32 MB to 1 MB,
both outside the measurement boundary and both to avoid paying for
simulation nobody reads. CoreMark's working set fits in a 64 KB L1 after
the first iteration, so neither should matter -- but "should" is a
hypothesis. Test: restore DefaultConfig's sizes and re-run.

**4. Memory latency. Expected effect: in the wrong direction.** The DPI
memory accepts a request the cycle it is offered. A real DRAM does not,
so this inflates the measured figure rather than depressing it, and
cannot explain a deficit. It is worth quantifying anyway, because it
bounds how much of any agreement is luck: give `memory_request` a fixed
latency and see how far the number moves.

**5. The published figure itself. Expected effect: unknown.** The study's
own roadmap carries XiangShan at ~10-15 CoreMark/MHz, which is a range
rather than a measurement, and it is not yet traced to a primary source
with a stated configuration, toolchain and ISA string. Test: read
XiangShan's own MICRO'22 paper and the project's published results, and
record what configuration each number is for. A comparison against an
unsourced range is not a replication.

## What this does not affect

The energy measurement. CoreMark/Joule is `CoreMark/MHz x frequency /
power`, so the x-axis value enters it directly -- but every hypothesis
above changes the workload or the build, not the method, and the same
binary produces both the cycle count and the switching activity. A
revised CoreMark/MHz moves the point along both axes consistently and
invalidates nothing about how the power was obtained.
