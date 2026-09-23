# One canonicalise session per flow, not one per kept module

Status: plan approved in principle on 2026-09-21, to be done before the
next synthesis from the top. Nothing implemented yet.

## The cost

After the whole-design canonicalise writes one RTLIL checkpoint
(`1_1_yosys_canonicalize.rtlil`, 4.9 GB for XiangShan's core), bazel-orfs
runs one action per kept module, "Re-canonicalize for partition cache"
(`synth_canonicalize_module.tcl`, `private/rules.bzl` actions 2c): each
reads the whole checkpoint again, `hierarchy -check -top X` deletes
everything outside X's tree, X's kept children are blackboxed, the
volatile attributes (`src`, `area`, `capacitance`) are stripped, and
`partition_<X>_canonical.rtlil` plus a `.name` sidecar are written. The
partition action reads only that slice.

Take 23: 47 such sessions for the parent and 62 for the four blocks
(Frontend 16, MemBlock 27, VecRegionModule 13, Region_1 6), each 84 s
and 4.9 GB. About 2.5 CPU hours per synthesis, and the one phase whose
memory shape caps `--jobs`: twelve of them together are 59 GB on a 62 GB
machine, which is how a session was killed on 2026-09-17. Every other
phase runs at 1 to 5 GB per action. It recurs on every synthesis-input
change.

## Chesterton's Fence

Commit f3c52546 (2026-06-01) introduced the per-module slice for one
reason, stated in the script's header: a partition's input must be
byte-stable under upstream edits that do not touch that module, so the
partition action stays a cache hit. Before it every partition hung off the
global checkpoint and any edit re-synthesised everything. One action per
module was the direct way to get one bazel output per module, and
`hierarchy -top` is destructive, so one process per module was also the
easy way to slice. The checkpoints of the time were tens of megabytes.

Nothing in the fence needs one action per module: bazel caches a
consumer on the digest of its inputs, so one action producing every
slice gives the partitions the same stability, provided the slicer
writes deterministic bytes. The fence stays; only the number of reads
changes.

## The change

Primitives verified on a toy (yosys 0.68, 2026-09-21): `write_rtlil
-selected` writes only the selected modules; `design -copy-to stubs M`
then `blackbox M` in that design gives a port-only stub; two RTLIL
fragments concatenated read back as one design.

1. `synth_canonicalize_slices.tcl` replaces `synth_canonicalize_module.tcl`.
   One session: read the checkpoint once; resolve every kept module's
   canonical name with the existing three-spellings logic (`\Foo`,
   `$paramod\Foo\...`, `Foo$Top.path`); strip the volatile attributes once
   (SYNTH_REPEATABLE_BUILD forced, as today); copy every kept module into
   a `stubs` design and blackbox them there, write one stub file per kept
   module; then per kept module X: its body is X plus its descendants,
   walked one module at a time and stopped at kept modules and library
   blackboxes, written with `write_rtlil -selected`, followed by the
   stubs of X's kept children and the library blackboxes, then the
   `.name` sidecar. No `hierarchy -top`, no per-module design copy.
   **Compute the walk explicitly** (cell types of each module, in Tcl,
   or from the RTLIL text the script already scans for `module` lines);
   do not lean on `%s`/`%m` selection expansion, which is fickle (`%m`
   leaves a `$`-named module partially selected, see
   xiangshan-timing.md entry 8). A module shared between X's own tree and
   a kept child's tree belongs to X's body, as `hierarchy -top` had it.
2. `private/rules.bzl` and `parallel_synth.mk`: the per-module loop
   becomes one `run_shell`, `do-yosys-canonicalize-slices`, with every
   `partition_*_canonical.rtlil` and `.name` as outputs. File names and
   the sidecar contract stay; `synth_partition.sh` and the partition
   actions do not change.
3. `test/synth_partition`: on a small hierarchical design with a leaf
   shared between a kept module's own tree and a kept child's tree, each
   slice holds its target and non-kept descendants, its kept children as
   port-only blackboxes and no other kept body; each slice reads back
   and passes `hierarchy -check -top X`; two runs are byte-identical.
   The last property is the fence, tested.
4. Measure on the parent's real checkpoint: one session against 47 x 84 s
   and 47 x 4.9 GB. Expected: one read plus seconds per slice, one
   process of about 10 GB.
5. Then `--jobs 16`: partitions at 1 to 5 GB are the only memory users.

ETA: script 1 h, rules and makefile 45 min, tests and lint 45 min,
measurement 15 min.
