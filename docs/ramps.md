# On and off: import and export

bazel-orfs helps you with ORFS. It does not replace it. An ORFS design is
a `config.mk`, and you can bring one in, work on it in either lane, and
take it back out whenever you want:

| | what it is | command |
|---|---|---|
| on-ramp | an ORFS design into a bazel-orfs clone, with a `BUILD.bazel` that builds it | `bazelisk run //:import -- <ORFS design dir>` |
| hermetic lane | Bazel builds it: pinned, cached, the same answer on any machine | `bazelisk build <flow>_final` |
| dirty lane | a plain ORFS tree for one stage, to hack with make ([dirty-lane.md](dirty-lane.md)) | `bazelisk run //:dirty -- start <flow> <stage>` |
| off-ramp | a flow out to a plain ORFS design: `config.mk`, `inputs/`, `run.sh` | `bazelisk run //:export -- <dir> <flow>` |

## Try it in a clone

Nothing here touches your ORFS checkout. Import only reads it, and
everything it writes goes into the clone, so deleting the clone removes
every trace.

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

## Export: hand it to make

```sh
bazelisk run //:export -- ~/gcd-orfs //imported/asap7/gcd:gcd
FLOW_HOME=~/OpenROAD-flow-scripts/flow ~/gcd-orfs/run.sh
```

`~/gcd-orfs` holds a `config.mk`, every input under `inputs/` and a
`run.sh` that runs ORFS's make. Nothing in it refers to the clone: copy
it to another machine, or hand it to someone who has never run Bazel. Use
it for a test with a locally built tool, a peer's review, or an ORFS
issue.

The values are the ones Bazel configures each stage with, merged into one
`config.mk`. That includes bazel-orfs's own defaults, such as
`OPENROAD_HIERARCHICAL=1`, so make runs the design the way Bazel did.
With the same ORFS and the same tools, the results are the same:

| flow | stages run by make | compared with Bazel's |
|---|---|---|
| gcd, imported from ORFS | synth … finish, 44 s | `5_route.odb` byte-identical |
| `//test:lb_32x128_top`, one hardened macro | synth … place, 19 s | `2_floorplan.odb` byte-identical |

Imported and then exported, ORFS's gcd keeps every design setting, with
its RTL and SDC byte-identical.

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
