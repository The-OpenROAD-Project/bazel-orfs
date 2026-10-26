# bazel-orfs: rules for an agent working on ORFS flows

These rules hold in bazel-orfs and in every workspace that depends on it.
bazel-orfs's own `CLAUDE.md` imports this file; a consumer gets it, with
the skills named below, from `bazelisk run @bazel-orfs//:agent -- setup`
(`tools/agent/README.md`), at the version `MODULE.bazel` pins.

## Analyse before every push

Before every push to a pull request branch, `bazelisk build --nobuild
--keep_going //...` passes: loading and analysis of every target, no
actions, minutes. An analysis error stops every target in CI at once, and
a pull request can be merged before a slower check finishes; a bump onto
an ORFS that removed a variable a flow sets is the usual one. The
`analyze-before-push` skill.

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

The bumper rewrites the blocks it recognizes, the pins among them. The
rest of what Bazel honours only from the root module, the toolchain
registrations, the `single_version_override`s
and the override patches copied into the consumer, is synced by hand, by
you, after the bump: diff bazel-orfs's `MODULE.bazel` and `patches/`
between the old pin and the new one, and carry each change into the
consumer's root, its reason with it. Do not write a generator for it; the
blocks change shape with every upstream, and a generator is out of date
the day the next one does. Details: bazel-orfs's `docs/openroad.md`,
"Root MODULE.bazel requirements".

A carried patch is shed cheapest way first, and every one ends in a
recorded state: `carried-patches` — drop a patch nothing uses, retire one
a bump carries (`@bazel-orfs//tools/carried_patches:check_carried_patches`
says `ABSORBED`, run over the copied patches after each bump too), and
report the rest as upstream candidates, sorted into bugfixes and new
topics.

## Import and export

`bazelisk run //:import` brings an ORFS design into a bazel-orfs clone,
`bazelisk run //:export` takes a flow back out to a plain ORFS design
(bazel-orfs's `docs/ramps.md`). When either refuses something, or maps it
wrong, fix the tool, `tools/ramp/import_design.py` or
`tools/ramp/export_design.py` in the clone, and run it again; do not
hand-edit what it wrote to cover a mapping it got wrong. Check the fix
with the round trip: import, export, and compare the two `config.mk`
files with ORFS's make (`make print-<VAR>`). Making an imported
`BUILD.bazel` idiomatic afterwards is a separate edit, and welcome.

When the imported Verilog was generated, building it in Bazel is the next
step. Search the Bazel Central Registry for a rule set for the
generator's language or hardware DSL before writing a `genrule`, and
prefer a registry module to a hand-written rule. Keep the copied Verilog
until the generated Verilog is identical to it, or shown equivalent, and
delete the copy in the same commit as the rule that replaces it.

## A new project

A new design is brought in for early results and fast iterations: the
top module a hard macro would be, the RTL pinned and fetched, a
hierarchical synthesis survey before any macro is chosen, a first flow
with every optimisation off, then stage by stage with a prediction and a
check at each one. The `new-project` skill, which names the skills that
own each step.

## Warm the GUI after every build

After every flow build or stage, finished or failed, start an odb-debug
daemon on the stage the human will want to look at and hand over the web
viewer's link with the build's result, unasked: the design loads while
they read it. The `warm-gui` skill.

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
  `@bazel-orfs//:dirty` tree + bring-your-own-binary edit/measure loop,
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

Whether a period problem is about where things sit or about the logic
itself is its own skill; no floorplan fixes logic on the wrong side of a
boundary:

- `surgery` — the test (would any placement fix it?), the eight classes
  of surgery problem seen here (storage without a module, constants
  behind a kept boundary, clock gates, simulation constructs, per-instance
  decode, cones cut by kept hierarchy, in2out paths through a hardened
  block, ports by the hundred thousand), and the rules: function kept and
  checked with a negative control that fails for the right reason, no
  register added, carried as `SYNTH_VERILOG_SURGERY`.

The rules learned dogfooding on XiangShan apply to any large design and
are a skill of their own:

- `dogfooding` — fix the tools, never the design (no multicycle or
  false-path exceptions, no added RTL registers); hard stops where a
  problem is made, and no linters or side flows (a guaranteed failure is
  moved earlier in the real flow, one source of truth); finish the
  macros before the parent; a design README says what is; public PR
  tests check intended behaviour, not `.ok` output; a PR on an unmerged
  upstream PR is a draft; relative paths; unattended means continue;
  check what our flow skipped before blaming a tool; trust the Bazel
  cache, never clean it; no ranking of alternatives before grt unless
  what is new this time is named; a green exit status is not a result:
  the silent failures to check, and a silent one made loud when found.

A target that another machine built but that is not a remote cache hit
here, or that rebuilds when nothing seemed to change, has its own skill:

- `cache-miss` — ask whether a target is cached without building it,
  from a laptop (`@bazel-orfs//tools/cache_evidence`): every miss and
  every action left unreached behind one; when another machine built it,
  compare tree hashes first, then the two machines' miss lists.

Running a flow's stages by hand, one after another in one tree, is fast
and gives up what Bazel guarantees; it has its own skill:

- `dirty-lane` — solved problems are hermetic, unsolved ones are hacked
  in the dirty lane and wrapped up hermetically once solved:
  `bazelisk run @bazel-orfs//:dirty -- start <flow> <stage>`,
  `next <stage>`, `status`, `archive`; what the lane gives up, when a
  number from it with its caveat beats no number, and when it is not
  enough. `orfs-deps-preflight` checks, before an hours-long stage run in
  a lane, that the code path under test will actually execute.

Building a design's macros and parent so they fit the machine's memory
is a scheduler at home, managed by its own skill:

- `scale-to-memory` — `orfs_schedule()` (`bazelisk run //<pkg>:build`,
  docs/schedule.md) packs the macros into waves that fit free memory and
  runs the parent alone; the first `resources.json` comes from a
  minutes-long assessment, later runs measure and refresh it. `--dirty
  <stage>` lays out a dirty-lane tree per unit and runs one stage of
  several units side by side within the same budget.

A long run is settled small first: `no-paint-drying` (settle questions at
seconds-to-minutes scale, then run unattended); `repair-timing-grt` for a
global-route repair that grinds.

How much of a period `repair_timing` leaves on the table, and in which
move, has its own skill and tools:

- `repair-headroom` — first make sure repair gave up (WNS < 0), then the
  odb-debug `headroom` tools on one stage, or `orfs_headroom` across a
  parent and its hardened blocks: useful skew, threshold voltage, the
  zero-wire and one-flop-loop floors, each undone after measuring; and
  grt-stage repair arms with repair's own stop reasons logged, to find
  out why it stopped.

A simulation that hangs, produces no output or computes the wrong answer
is a different problem from an OpenROAD failure, and has its own skill:

- `debug-rtl-sim` — the cheapest-first ladder for an RTL or gate-level
  simulation, and the harness properties each rung needs. Never read a
  raw log or waveform into context.
