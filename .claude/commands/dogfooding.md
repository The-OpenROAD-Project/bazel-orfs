> **Repo**: Run from the bazel-orfs root. Rules learned building XiangShan with bazel-orfs; they apply to any large design.

The standing rules from dogfooding bazel-orfs on XiangShan. A rule learned on one machine is written here, in a pull request, or it is not shared: a local memory reaches no other machine or session.

ARGUMENTS: $ARGUMENTS

## 1. Fix the tools, not the design

When a timing or flow problem comes from the tools, fix the tools. Never:

- write an SDC exception (`set_multicycle_path`, `set_false_path`) to hide it: an exception is a claim about the design's behaviour that nothing checks, and a wrong one fails in silicon while the flow reports clean;
- change the RTL to add a register or a cycle of latency: that is a behaviour change the designers did not specify and verification did not cover.

What is allowed: a fix in OpenROAD, yosys or ORFS (carried here as a patch until upstream takes it); a flow hard stop (rule 2); an equivalence-preserving mapping, such as a behavioural clock-gate module mapped onto the platform's ICG cell. Upstream RTL patches are for functional bugs only.

Example: XSCore's Frontend measured 14.1 ns alone, its worst path ending at XiangShan's behavioural `ClockGate` latch. The fix for the latch is a mapping onto the ICG cell (`xs_icg.ys`), not a multicycle path on the enable and not a register per SRAM bank. The other 8 ns turned out not to be a tool bug at all: see rule 10.

## 2. Hard stops where the problem is made

A stage that produces a broken result refuses, and names the cause, instead of passing it on to fail hours later somewhere else. Threshold on how bad, not how many, and print the worst offenders:

- cells left with no row under them after global placement (the legaliser's `initialSnap` then walks for hours);
- gross slew left by `repair_design`: a net whose loads span a millimetre under one driver;
- a block abstracted before its own clock tree, whose clock pin then carries the whole unbuffered clock net into the parent.

## 3. Finish the macros before grinding on the parent

Iterate a block to done before building the parent on it. Do not add machinery to spare the parent rebuilds that only happen when blocks are iterated under a finished parent; if such a change is proposed, first list the whole category of block changes it must leave the parent unaffected by, because every such shortcut is risk.

## 4. A design README says what is

A design's README gives the current number and the current problems. History (was, fell from, fixed in) lives in PR bodies, the KPI series and its plot, and the `ideas/` inventory. A fixed problem leaves the README, and a figure drawn for it is re-rendered to match.

## 5. A test in a public PR tests the intended behaviour

Prefer a pass/fail test that states the behaviour over a golden-output comparison: in OpenROAD, `check` and `exit_summary` from `test/helpers.tcl`, registered with `check_passfail = True` (Bazel) and `PASSFAIL_TESTS` (CMake), not a new `.ok`/`.defok`. Show it failing without the change before showing it pass.

## 6. A PR that depends on an unmerged upstream PR is a draft

An ORFS change that needs an OpenROAD change not yet in ORFS: test it locally against that OpenROAD, as an A/B with and without it, open it as a draft whose first line names the dependency, and mark it ready only when that PR is merged and ORFS's OpenROAD is bumped past it. Backwards-compatible OpenROAD code kept for the transition is removed afterwards. Every upstream write still needs the human's order (`CLAUDE.md`).

## 7. Choices in the flow script, facts in the database

A command's choice (accept congestion, say) is passed explicitly on every call that decides; facts (the route, its congestion markers) live in the `.odb`; no command reads a policy some earlier command left in a global. OpenROAD #11525 and ORFS #4563 are the worked example: `repair_antennas` and the incremental reroutes each overwrote `global_route -allow_congestion`, and a congested route stopped counting as a route.

## 8. Relative paths

Commands and docs use paths relative to the working directory, never `$PWD/...` or `/home/...`. A tool that `bazel run` starts from its runfiles tree resolves a relative path against `BUILD_WORKING_DIRECTORY`, as `--install` on a `_deps` target and `ODB_DEBUG_DIR` on an odb-debug target do; a new one does the same.

## 9. Unattended means continue

In an unattended campaign a task that fails or is blocked is written up, and the campaign goes on to the next task; nothing halts the run to ask. Obstacles like a patch conflict are fixed, not reported; only what could not be fixed is. Every question that needs the human belongs before the launch (`/no-paint-drying`), and a gate chooses the next task rather than ending the campaign.

## 10. Chesterton's fence: check what our flow skipped before blaming a tool

Before calling something a tool bug, assume its authors considered it and look for the step our flow skipped that the tool's normal flow relies on. The worked example: Frontend's placed checkpoint had 37,665 pins violating slew by up to 58x, which looked like `repair_design` failing on its own fanout buffers. A second `repair_design` on the same checkpoint cleared every one and took the block from 14.1 ns to 6.2 ns. ORFS runs that second pass in its global-route stage; our blocks are abstracted at `cts`, before it, so they never got it. The fix is ours (where the flow abstracts), not OpenROAD's.
