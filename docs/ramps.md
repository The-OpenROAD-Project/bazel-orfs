# On and off: import and export

bazel-orfs helps you with ORFS. It does not replace it. An ORFS design is
a `config.mk`, and you can bring one in, work on it in either lane, and
take it back out whenever you want:

| | what it is | command |
|---|---|---|
| on-ramp | an ORFS design into a bazel-orfs clone, with a `BUILD.bazel` that builds it | `bazelisk run //:import -- <ORFS design dir>` |
| hermetic lane | Bazel builds it: pinned, cached, the same answer on any machine | `bazelisk build <flow>_final` |
| dirty lane | a plain ORFS tree for one stage, to hack with make ([dirty-lane.md](dirty-lane.md)) | `bazelisk run //:dirty -- start <flow> <stage>` |
| off-ramp | a flow out to a plain ORFS design, `config.mk` and `inputs/`, made with ORFS's make as usual | `bazelisk run //:export -- <dir> <flow>` |

## Try it in a clone

The easy way to get to know bazel-orfs is the same as for ORFS: clone it.
That is not the only way. Just as you can use ORFS from a repository of
your own, you can use bazel-orfs from yours (the README's "Use bazel-orfs
from your own project"); a clone just saves setting one up while you look
around.

Nothing here touches your ORFS checkout. Import only reads it.

```sh
git clone https://github.com/The-OpenROAD-Project/bazel-orfs
cd bazel-orfs
bazelisk run //:import -- ~/OpenROAD-flow-scripts/flow/designs/asap7/gcd
#   import: 3 files into imported/asap7/gcd
bazelisk build //imported/asap7/gcd:gcd_final
bazelisk build //imported/asap7/gcd:gcd_final    # again: from the cache
```

The first build in a fresh clone also builds OpenROAD and Yosys from
source, which takes 30 to 60 minutes. After that, gcd takes about three
minutes from RTL to final, and building it again with nothing changed
takes under a second (measured: 0.4 s). Change one setting and only the
stages that read it run again.

Import copies the design directory and every file its `config.mk` names
into `imported/<platform>/<design>/`: the RTL, the SDC, the tcl, the macro
LEF and LIB. The platform and the flow scripts come from the ORFS that
bazel-orfs pins. `imported/` is git-ignored. Running import again
replaces the copy.

The values come from ORFS's own make (`make print-VAR`), so wildcards,
includes and conditionals come out the way the ORFS flow would see them.

## Where the files go

By default, what bazel-orfs writes for you goes under the clone:
`imported/` for import, and `tmp/` for the dirty lane's trees and other
scratch work. So it does not fill up your system's `/tmp`, and deleting
the clone deletes it. Both are git-ignored. They are only defaults:
`//:import --dest` and `//:dirty start --dir` put them anywhere you
like.

Bazel's own cache is different. Bazel keeps it outside the clone, in
`~/.cache/bazel` by default, and refuses to keep it inside a repository.
It is shared by every clone and workspace on the machine, which is why a
second clone does not build OpenROAD again. To remove it after a try-out,
run `bazelisk shutdown` in the clone and delete the directory
`bazelisk info output_base` names, or all of `~/.cache/bazel`.

## Look at the BUILD.bazel

`imported/asap7/gcd/BUILD.bazel` is what a bazel-orfs design looks like:

```starlark
orfs_flow(
    name = "gcd",
    arguments = {
        "CORE_ASPECT_RATIO": "1",
        "CORE_MARGIN": "0.5",
        "CORE_UTILIZATION": "65",
        "PLACE_DENSITY": "0.35",
        "SKIP_LAST_GASP": "1",
        "SYNTH_USE_SYN": "1",
    },
    pdk = "@orfs//flow:asap7",
    sources = {
        "SDC_FILE": ["constraint.sdc"],
    },
    verilog_files = ["designs/src/gcd/gcd.v"],
)
```

It is written literally, one setting per `config.mk` variable. That is
correct, but it is not how you would write it by hand. Ask your AI to
make it idiomatic. The clone already has the skills set up for it
(`.claude/skills/`: `prefer-slang`, `macro-constraints`, `dogfooding`
and the rest), and [examples/BUILD](../examples/BUILD) shows the style.

One difference from ORFS's make: `orfs_flow()` synthesises with slang
where ORFS's make reads the Verilog with yosys's own frontend. The
generated `BUILD.bazel` says so when that applies.

## Export: make as usual in ORFS

```sh
bazelisk run //:export -- \
    ~/OpenROAD-flow-scripts/flow/designs/asap7/gcd-bazel //imported/asap7/gcd:gcd
cd ~/OpenROAD-flow-scripts/flow
make DESIGN_CONFIG=./designs/asap7/gcd-bazel/config.mk
```

An export is an ORFS design like any other: a `config.mk` and its
inputs under `inputs/`. Put it next to ORFS's own designs and make it as
usual; results, logs and reports go where ORFS always puts them. Export
prints the make line to type. For a flow Bazel builds only partway, the
line names the last stage (`make DESIGN_CONFIG=... place`), and so does
the `config.mk`. Nothing in the export refers to the clone: copy it to
another machine, or hand it to someone who has never run Bazel. Use it
for a test with a locally built tool, a peer's review, or an ORFS issue.

An export of gcd shares `results/asap7/gcd/base` with ORFS's own gcd:
the design is the same name. Export says so when that directory holds an
earlier run; `FLOW_VARIANT=bazel` on the make line keeps the two apart.

The values are the ones Bazel configures each stage with, merged into one
`config.mk`. That includes bazel-orfs's own defaults, such as
`OPENROAD_HIERARCHICAL=1`, so make runs the design the way Bazel did.
With the same ORFS and the same tools, the results are the same:

| flow | stages run by make | compared with Bazel's |
|---|---|---|
| gcd, imported from ORFS | synth … finish, 49 s | `5_route.odb` byte-identical |
| `//test:lb_32x128_top`, one hardened macro | synth … place, 21 s | `2_floorplan.odb` byte-identical |

Measured with the export under the pinned ORFS's `flow/designs/` and
plain `make` run from `flow/`, with the OpenROAD and Yosys binaries Bazel
used.

Imported and then exported, ORFS's gcd keeps every design setting, with
its RTL and SDC byte-identical.

### What config.mk can say

A more advanced flow does things ORFS's make has no place for. Its RTL
may be generated, as in [examples/generated](../examples/generated/BUILD),
where Bazel runs the generator and the flow reads what it writes. An
export is limited to what a `config.mk` can say, ORFS's idioms, so
anything else travels as the file it made, or not at all:

| in the Bazel flow | in the export |
|---|---|
| generated RTL | the Verilog as built, under `inputs/`: a snapshot |
| the generator, its options, its tests | not exported: they stay in Bazel |
| a hardened macro | its abstract (`.lef`, `.lib`), as built |
| `orfs_run` steps, sweeps, variants, checks | not exported |

`//examples/generated:mac`, exported and made with the pinned ORFS and
the tools Bazel used, ran from synth to finish in 45 s with a final
report identical to Bazel's: the same cells, area, extraction and IR
drop. Its `.odb` is not byte-identical, unlike gcd's: Yosys records the
source file's path in the netlist, and the path is the export's, not the
clone's; the netlists differ in nothing else. gcd synthesises with
OpenROAD, which records none.

## Import and export with your AI

Your project may well not be on the latest ORFS. It may carry patches,
set variables upstream does not know, or override flow scripts. Import
and export are a starting point, and your AI does the rest, locally:

- **Work in a clone.** The tools are plain Python in your clone,
  `tools/ramp/import_design.py` and `tools/ramp/export_design.py`. Your
  AI can patch them to match your project and run them again.
- **They stop at what they do not know.** Neither one guesses. When it
  meets something it cannot map, such as `BLOCKS` (hierarchical macros,
  not handled yet), a file that does not exist or a variable two stages
  set differently, it names the thing and the file to patch.
- **The round trip is the check.** Import, export, and compare the two
  `config.mk` files with ORFS's make.
- **Afterwards.** A fix that helps others is a pull request to
  bazel-orfs. A fix that only your project needs stays a patch in your
  clone.

## Next exercise: build your RTL in Bazel

The Verilog you imported may very well have been generated, by a
generator written in Scala, Python, Rust or some other language. Once the
generator runs in Bazel, the Verilog is a build output: change the
generator, and only the stages it reaches build again.

Ask your AI, for example: "build `imported/asap7/mydesign/src/*.v` from
my generator in `~/my-gen`, inside Bazel". It replaces the copied
Verilog with a rule that generates it.

- **Language rules.** Bazel has rules for Scala (`rules_scala`), Python
  (`rules_python`) and Rust (`rules_rust`), and a `genrule` covers
  anything else.
- **Hardware rule sets.** Beyond the generic language rules, the
  [Bazel Central Registry](https://registry.bazel.build) has rule sets
  for specific hardware DSLs, and for HDL tooling: Verilog and VHDL,
  simulators and Python testbenches. Search it for yours before writing
  a `genrule`.
- **The check.** Keep the copied Verilog until the generated Verilog is
  identical to it, or shown equivalent. Otherwise "my layout changed"
  cannot be told apart from "my generator changed".
