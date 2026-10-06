> **Repo**: Run from the bazel-orfs root, or from any workspace that depends on bazel-orfs (`bazelisk run @bazel-orfs//:deps -- ...`). Applies to every ORFS flow.

A flow's stages in one tree, run by hand, stage after stage. During bring-up that turns an hour of rebuilds per change into minutes, because nothing downstream is rebuilt behind your back. It also gives up what Bazel guarantees, and this skill says what it gives up and when that matters.

ARGUMENTS: $ARGUMENTS

## The lane

```sh
# Bazel builds everything floorplan needs (synthesis) and installs it,
# with floorplan's scripts, in one tree per flow: tmp/<package>/<flow>.
bazelisk run //:deps -- start //test:lb_32x128 floorplan
#   next: tmp/test/lb_32x128/make do-floorplan

tmp/test/lb_32x128/make do-floorplan     # edit _main/config.mk or scripts, re-run

# Carry on in the same tree: place's scripts and config, and the
# floorplan you made, untouched.
bazelisk run //:deps -- next place
tmp/test/lb_32x128/make do-place

# Where each result came from, and which settings were edited.
bazelisk run //:deps -- status
```

- `start <flow> <stage>` refuses to replace a tree; `--fresh` replaces it, `--dir` puts a second one beside it, `--variant` picks a flow variant. A stage target's label (`//test:lb_32x128_place`) works in place of `<flow> <stage>`.
- `next <stage>` never overwrites an earlier stage's result in the tree. It refuses when the tree lacks one (`results/` only: an earlier stage's logs and reports are not installed, since Bazel's would describe a different run). It installs the stage's own `config.mk`, keeping an edited one as `config.mk.<stage>`: each stage runs with its own variables, as in the build (the deployed-tree guard in `make.tpl` says why).
- The tree's `make` runs only its current stage's targets; synthesis is `do-yosys-canonicalize do-yosys <RESULTS_DIR>/1_2_yosys.sdc do-1_synth`, which `start` prints. A design that Bazel synthesises on its parallel path (`SYNTH_NUM_PARTITIONS`) gets a serial synthesis in the tree, which can differ or fail; start such a lane at floorplan.
- `OPENROAD_EXE=/path/to/openroad <tree>/make do-<stage>` runs a binary of your own (`/byo-openroad`).
- `archive <flow> <stage> <file.tar.gz>` is the self-contained reproducer (`/untar-and-run-report`).
- Building `//:deps` is instant, and `start` builds only the stage target's output groups: the same actions, keys and cache entries as a plain `bazel build`, so after a finished build nothing re-runs.

## What the lane gives up

- **Dependencies are not respected.** An edit to floorplan's settings does not invalidate the place you already ran; re-running it is your job. A script edited in the tree is a copy; `next` refreshes the stage's scripts from the workspace.
- **A later stage's inputs come from Bazel's view of the flow.** When `next <stage>` needs something generated from an earlier stage (a planner's `MACRO_PLACEMENT_TCL`, an `orfs_arguments` file), Bazel builds it from its own earlier stages, not from the ones you ran by hand.
- **Nothing in the tree reaches the Bazel cache.** There is no way to inject a lane result into it; a clean build recomputes every stage.

## Using a number from the lane

Perfection is the enemy of the good. When a clean build takes hours, a lane number with its caveat can be worth more than no number:

- when there is no time to re-run; or
- when the risk that the lane's shortcuts moved the result is judged low;
- and a fresh build from scratch will come soon enough anyway as the project proceeds.

Write the caveat beside the number, in the same words wherever it goes (PR, README, `kpi.json` note): *from a `_deps` lane, not a clean build*, and which stages were run by hand. `status` prints both. The next clean build confirms or replaces the number.

## When the lane is not enough

- Two arms of an A/B, unless both ran in the lane the same way.
- A number a decision rests on, that the next clean build will not revisit soon.
- When the tree's history (which stages ran with what) is no longer certain: `status` is the record, and a hand edit outside `make` is not in it.
- When a setting has settled: it moves into the BUILD file.

## Leaving the lane

Move the settled edits into the flow's BUILD file and sources, then `bazel build`. The tree is not reused; `start --fresh` makes a new one from the build.
