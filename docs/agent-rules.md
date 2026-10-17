# bazel-orfs: rules for an agent working on ORFS flows

These rules hold in bazel-orfs and in every workspace that depends on it.
bazel-orfs's own `CLAUDE.md` imports this file; a consumer gets it, with
the skills named below, from `bazelisk run @bazel-orfs//:agent -- setup`
(`tools/agent/README.md`), at the version `MODULE.bazel` pins.

## Synthesis frontend

`orfs_flow` synthesises with slang: `SYNTH_HDL_FRONTEND` defaults to
`slang` and a flow that sets another frontend is refused unless it passes
`yosys_frontend_reason = "<why>"` next to the setting (`SYNTH_USE_SYN`
flows are exempt). yosys's own Verilog frontend is effectively deprecated
for SystemVerilog and parses at a few MB/s: XiangShan's flat core cost
seven minutes of canonicalisation per synthesis on it, one on slang.
The `prefer-slang` skill.

## Bumping

`bazelisk run @bazel-orfs//:bump` rewrites the override shapes it
recognizes and stops, naming the block, when it meets one it does not. It
never writes a partial file: `MODULE.bazel` is read once and written once
at the end, so a refusal leaves it byte-identical.

If a bump is refused because a block is unrecognized, fix the file — the
bumper does not carry migrations for old shapes. Re-seed `MODULE.bazel`
from the template in bazel-orfs's `README.md` and re-apply the local
edits. `--ignore` downgrades the refusal to a warning and updates only the
parts the bumper recognizes; the unrecognized block is left untouched.

`bump.py` always downloads the newest `bump_impl.py`, so the bumper is
never stale; the only thing that can be out of date is the consumer's
file. Details: bazel-orfs's `docs/openroad.md`, "Shapes the bumper
recognizes".

## Never clean the Bazel cache

Never run `bazel clean` or delete an output base, partly or wholly. A
surprising rebuild is investigated through its keys (`cache-miss`); an
artifact that must be rebuilt is re-keyed by a code change that reaches
its key.

## Debugging OpenROAD/ORFS failures

When an ORFS stage fails in openroad/yosys/opensta — a crash, a hang, a
parallel race, or a nondeterministic result — the skills are the single
source of truth; do not duplicate their mechanics:

- `openroad-debug` — diagnose the failure (decode the exit code,
  characterize a hang vs race with the `-threads 1` test, set up a fast
  `@bazel-orfs//:deps` tree + bring-your-own-binary edit/measure loop,
  split a stage at an ODB checkpoint) and shape a self-contained
  reproducer.
- `byo-openroad` — the bring-your-own OpenROAD binary loop for a source
  change.
- `odb-debug` — ask a stage's ODB questions through a persistent OpenROAD
  session (macros, cells inside macros, slivers, legality, worst paths)
  from a shell or the `odb-debug` MCP server.

Which modules to harden, and the floorplan their interfaces dictate, is
its own skill; a global route that will not converge on a hierarchical
design usually starts there, not in the router:

- `macro-selection` — the space and time tables that name the cuts, the
  planner that draws the floorplan from them, the calibration and the
  gates; tools in `@bazel-orfs//tools/macro_select`.

Which registers the timer never sees is its own skill, and stock
OpenSTA's `check_setup` is blind to the worst case:

- `check-setup` — what each warning means, why the count in
  `2_1_floorplan.log` is not enough, the pins and their modules through
  odb-debug's `check_setup` tool, what this flow's `set_max_delay` SDC
  produces by design, and the carried patches 0108/0109 (a flop behind a
  tied-enable ICG, a clock that reaches a register only on the wrong
  edge).

How to constrain a hardened block is its own skill, and the advice in
circulation is wrong for this flow:

- `macro-constraints` — only register-to-register paths can fail timing
  closure, boundary paths are optimization targets written with
  `set_max_delay`, and `set_input_delay` cannot be written at all without
  assuming a clock insertion latency the block does not know.
  `flow/platforms/asap7/constraints.sdc` is the reference.

The rules learned dogfooding on XiangShan apply to any large design and
are a skill of their own:

- `dogfooding` — fix the tools, never the design (no multicycle or
  false-path exceptions, no added RTL registers); hard stops where a
  problem is made; finish the macros before the parent; a design README
  says what is; public PR tests check intended behaviour, not `.ok`
  output; a PR on an unmerged upstream PR is a draft; relative paths;
  unattended means continue; check what our flow skipped before blaming
  a tool; trust the Bazel cache, never clean it.

A target that another machine built but that is not a remote cache hit
here, or that rebuilds when nothing seemed to change, has its own skill:

- `cache-miss` — ask whether a target is cached without building it,
  from a laptop (`@bazel-orfs//tools/cache_evidence`): every miss and
  every action left unreached behind one; when another machine built it,
  compare tree hashes first, then the two machines' miss lists.

Running a flow's stages by hand, one after another in one tree, is fast
and gives up what Bazel guarantees; it has its own skill:

- `deps-lane` — `bazelisk run @bazel-orfs//:deps -- start <flow> <stage>`,
  `next <stage>`, `status`, `archive`; what the lane gives up, when a
  number from it with its caveat beats no number, and when it is not
  enough. `orfs-deps-preflight` checks, before an hours-long stage run in
  a lane, that the code path under test will actually execute.

A long run is settled small first: `no-paint-drying` (settle questions at
seconds-to-minutes scale, then run unattended); `repair-timing-grt` for a
global-route repair that grinds.

A simulation that hangs, produces no output or computes the wrong answer
is a different problem from an OpenROAD failure, and has its own skill:

- `debug-rtl-sim` — the cheapest-first ladder for an RTL or gate-level
  simulation, and the harness properties each rung needs. Never read a
  raw log or waveform into context.
