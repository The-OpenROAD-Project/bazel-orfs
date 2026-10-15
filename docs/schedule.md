# `orfs_schedule()`: a scheduler at home

A big design is many flows: hardened macros, then a parent that reads
their abstracts. Built all at once, Bazel runs as many actions as the
machine has cores, with no idea how much memory each needs: one parent's
global route can take 120 GB and a macro's synthesis 30, and on one
workstation that ends in the kernel's OOM killer. Built strictly one at
a time, it wastes most of the machine.

`orfs_schedule()` is the at-home answer: no cluster and no job queue,
one workstation and a record of what each flow needs. It runs the macros
in parallel waves that fit the memory there is, then the parent alone.
AI skills manage it: a Claude session writes the first record from a
quick assessment (the `scale-to-memory` skill), and later runs refine it
from measurement.

## Use

```python
load("@bazel-orfs//:openroad.bzl", "orfs_schedule")

orfs_schedule(
    name = "build",
    macros = {
        "CoupledL2": [":CoupledL2_kpi", ":CoupledL2_generate_abstract"],
        "Frontend": [":Frontend_kpi", ":Frontend_generate_abstract"],
        # ...
    },
    parent = {"XSTile": [":XSTile_kpi"]},
    resources = "resources.json",
)
```

```sh
bazelisk run //<pkg>:build                    # schedule and build
bazelisk run //<pkg>:build -- --plan-only     # print the waves, build nothing
bazelisk run //<pkg>:build -- --budget 100    # GB, instead of free memory
bazelisk run //<pkg>:build -- --units Frontend
```

Each unit is a name and the targets that build it. The name is what
`resources.json` records it under and the directory its ORFS logs are
written in, so it is the flow's `name`. XiangShan's
`//test/coremark_joule/designs/asap7/xiangshan:build` is the example in
this repository.

## What a run does

1. **Budget.** Free memory (`MemAvailable`) less a margin (`--margin`,
   5 GB), unless `--budget` is given.
2. **Waves.** The macro units are packed so each wave's summed peak fits
   the budget, largest first; an `estimated` peak is padded by 20 %. A
   unit larger than the budget runs alone. The parent units run alone,
   last. A unit with no entry stops the run (see below).
3. **Build.** One `bazelisk build` per wave in your workspace. Bazel
   allows one invocation per workspace at a time, so the waves run one
   after another, with Bazel's own parallelism inside each. A failed
   macro wave does not stop the other macro waves, which do not read
   each other; it stops the parent, which reads them all.
4. **Measure.** Every ORFS step log ends with `Elapsed time ... Peak
   memory ...`; cache hits carry the logs of the run that made them. The
   runner reads them (`logs/<platform>/<unit>/<variant>`, the files
   directly in it, never a recursive walk) and turns `estimated` entries
   into `measured` ones.
5. **Refresh.** An entry more than 20 % off is rewritten in your
   workspace, and the run says so. Commit `resources.json` when it is
   materially out of date: a new unit, a new stage, a peak that moved.

## `resources.json`

Version-controlled, beside the `BUILD` file that calls
`orfs_schedule()`:

```json
{
  "commit": "2c23c4a4",
  "date": "2026-10-15",
  "units": {
    "Frontend": {
      "source": "measured",
      "stages": {
        "synth": {"peak_gb": 14, "minutes": 25},
        "grt": {"peak_gb": 28, "minutes": 40}
      }
    },
    "XSTile": {
      "source": "estimated",
      "basis": "3.6 M instances x 33 kB at grt",
      "stages": {"grt": {"peak_gb": 120, "minutes": 210}}
    }
  }
}
```

A unit's footprint is its largest stage: a flow's stages run one after
another. `source` is `estimated` until a run measures it; `basis` says
how an estimate was made.

## Managed by AI skills

With no `resources.json`, the runner stops and points to the
`scale-to-memory` skill. The first schedule comes from an assessment,
not from a slow serial build that measures everything. A Claude session
following the skill:

1. **Reads the design, in seconds.** Which units are macros and which
   the parent, what nests in what, what the cache already holds: that is
   the schedule's shape.
2. **Estimates, in minutes.** From cheap or cached artifacts, a
   synthesis cell count or a floorplan's instance count, times the
   skill's per-instance memory and time factors per stage. The factors
   come from measured designs and are refreshed when measurements
   disagree.
3. **Writes `resources.json`** with `source: "estimated"` and a `basis`
   per entry, and runs `--plan-only` to show the waves before building.

After the first real run the record is measured, and later sessions only
commit its refreshes.

## Guards

- The skill runs the build inside a memory scope at the budget with swap
  allowed, so an underestimate pages instead of being killed; check for
  kernel OOM kills after a run.
- One parent at a time, ever.
- Stop a runaway job by its recorded PID, never by a pattern.
- A run that pages says the record is wrong: rerun with a lower
  `--budget` and let it refresh.

## Limits

- One workstation, one workspace: waves are consecutive Bazel
  invocations, not concurrent ones.
- Peaks are per unit, not per action.
- Macros of macros are not units of their own: a block builds the
  macros it reads (XiangShan's register files) inside its own wave, and
  its recorded peak absorbs them. Fine while they are small beside it.
- Remote execution is out of scope: there memory is the executor's
  problem, not the scheduler's.
