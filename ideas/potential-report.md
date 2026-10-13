# A potential report: where the RTL or the flow leaves period on the table

Status: piloted 2026-10-13 in #1235 (draft), verdict go for finding
shapes and placing proxies of them; no-go for the literature column and
for synthesis-only estimates of delay. Nothing beyond the pilot is
implemented.

## The idea

An advisory pass, running beside the flow and read by no stage, that
finds a design's repeating structures and says for each whether a
rewrite of the RTL would buy period or area, how much, and whose
problem it is:

- **rtl**: a rewrite measured on a placed proxy beats the structure as
  written by more than a threshold;
- **flow**: the structure as written is far from what it should cost,
  and no rewrite closes the gap;
- **expected**: nothing to gain;
- **unmeasured**: a shape found, no number yet.

The report is a signal for an AI agent or a human to rewrite, never a
fix: every row carries the shape, where it is, the measured upside, the
rewrite's shape and the check that accepts it (equivalence of the leaf,
then the flow's own period). It lives in bazel-orfs; only hooks and bug
fixes would go upstream.

## Chesterton's fence

If sharing a ROB's decode were easy for synthesis, synthesis would do
it. Two reasons it does not here, the second ours:

- open-source synthesis sees neither placement nor that 352 instances
  are one leaf with a constant on one port;
- the flow keeps `RobEntryCell` and `SqEntryCell` as modules
  (`SYNTH_KEEP_MODULES`) so that yosys maps them once; slang's
  `--keep-hierarchy` gives every instance its own definition, so ABC
  maps them 352 and 64 times anyway, and no constant reaches the copies.

## What the pilot measured

**Finding the shapes is cheap and real.** Read from XiangShan's flat
Verilog with slang, nine modules in 25 s:

| module | shape |
|---|---|
| Rob | `RobEntryCell` x352: 28,864 compares of the entry's constant index against 82 distinct operands, 82 shared decoders in disguise |
| PhysicalStoreQueue | `SqEntryCell` x64: 832 compares against 13 operands; key bits driving 384 compare inputs |
| LoadQueueReplay | 40 x 40 age matrix; flat CAMs of 123 x 10 and 120 x 5 bits |
| TLBNonBlock | flat CAM, 48 x 11 bits |

**Only placement ranks a rewrite.** A ROB-shaped array, 256 entries
against four pointers, placed by the flow three ways:

| arm | period | area |
|---|---:|---:|
| entry kept, as XiangShan's Rob partition | 589.6 ps | 12,921 µm² |
| flattened | 444.4 ps | 8,781 µm² |
| pointers decoded once in the parent | 387.2 ps | 8,951 µm² |

The same rewrite on a 32-entry fixture, mapped to the library and timed
without wire, came out slower (271 against 203 ps). Synthesis-only
estimates rank area, never period; on Rob one did not finish in 51
minutes.

**The literature does not anchor standard cells.** A generated register
file of the Alpha 21264's shape (80 x 64, 4R 6W) reads in 35.2 FO4 after
repair; CACTI's 10.8 FO4 for the same configuration (Hrishikesh et al.,
ISCA 2002) is a custom sense-amplified array. The column needs
standard-cell anchors before it can call anything a flow gap.

## The plan

1. **Tier 1 in the flow.** `detect.py` on each kept module's
   canonicalised RTLIL as an output group of the synthesis target,
   advisory, in parallel with synthesis; the findings JSON beside the
   netlist.
2. **Tier 3 proxies, generated.** For each finding of a known kind
   (constant index, CAM, age matrix), generate the proxy at the measured
   scale (entries, widths, operand count) and its rewrite, and place both
   with the flow; tens of minutes, manual targets.
3. **The rows that matter, on XiangShan itself.** Rob without
   `RobEntryCell` kept, then the decode-once rewrite as a XiangShan
   patch, each measured on the parent; the report's number has to match
   the parent's.
4. **Standard-cell anchors** for the literature column, from logical
   effort on the structure's own decode and select, before any flow-gap
   verdict.

Dropped: the synthesis-only what-if as a delay signal, and SAT-solved
tiling until a verdict says placement, not logic, is the gap.
