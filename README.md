# bazel-orfs

[Bazel](https://bazel.build/) rules for running
[OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
(ORFS): RTL to GDS with OpenROAD, Yosys and an open PDK, driven by
`bazelisk build`.

## bazel-orfs helps you with ORFS

It does not replace it. An ORFS design is a `config.mk`: bring one in,
build it, and take it back out to make whenever you want. To get to know
bazel-orfs, clone it, as you would ORFS; like ORFS, it can also be used
from a repository of your own, but a clone is the quickest way to look
around. Your ORFS checkout is only read.

```sh
bazelisk run //:import -- ~/OpenROAD-flow-scripts/flow/designs/asap7/gcd
bazelisk build //imported/asap7/gcd:gcd_final
bazelisk run //:export -- \
    ~/OpenROAD-flow-scripts/flow/designs/asap7/gcd-bazel //imported/asap7/gcd:gcd
```

The first build in a fresh clone builds OpenROAD and Yosys from source,
30 to 60 minutes. After that gcd takes about three minutes from RTL to
final, and building it again with nothing changed takes under a second.
The export is an ORFS design like any other: in ORFS's `flow/`,
`make DESIGN_CONFIG=./designs/asap7/gcd-bazel/config.mk` as usual, and
with the same ORFS and tools the results are byte-identical. What
bazel-orfs writes for you goes under the clone by default, `imported/`
and `tmp/`, so deleting the clone deletes it; Bazel's own cache is
outside it, in `~/.cache/bazel`. [docs/ramps.md](docs/ramps.md) has the
rest, including how your AI adapts import and export to a project's own
ORFS.

## "Hermetic, and a new way of working"? Wrong, and right.

The usual assumption is that Bazel seals your flow in a sandbox and
makes you learn a new way of working. Both halves are wrong and right
at the same time; which one depends on whether you have solved the
problem yet.

- **Unsolved: dirty, and the same.** A plain directory with ORFS's
  make targets, the .tcl scripts and the openroad executable, the way
  ORFS always was. Edit a script, re-run a stage, open the .odb and
  poke at it. There's no Bazel in the way and nothing new to learn.
- **Solved: hermetic, and new.** `bazelisk build`: every version
  pinned, every stage cached, the same answer on any machine, today
  and next year.

```bash
bazelisk run //:dirty -- start <flow> <stage>
```

## Why "dirty"?

There are exactly two ways of working in bazel-orfs, and each needs a
name that leaves no doubt which one you're in:

- **Dirty**: a directory you change by hand. Fast, visible, and it
  promises nothing about reproducibility.
- **Hermetic**: pinned, cached, the same answer on any machine. It
  promises everything, and you don't hack it.

There's no third lane. Humans and AI assistants both work best with
hard stops. "Local", "dev" or "scratch" would blur the line, and
"dirty" says plainly which promises are off.

## Chesterton's fence: why does ORFS fork?

bazel-orfs started out a hermetic purist: pin everything, seal
everything, and treat a fork of ORFS as a hack to engineer away. Then
it asked the fence question: someone built this on purpose, so why?

Because the answer to an unsolved problem is often in the flow
scripts, OpenROAD, Yosys or another tool. You have to be able to
change any of them, now, and carry the change until it settles.
Forking is how ORFS does that, and it's right.

So bazel-orfs was reworked around that reason, with two ways to act
on it, both first class:

- **Forks**, the ORFS way: work in public forks and upstream as you
  go.
- **Modules**: carry patches in your own `MODULE.bazel` against pinned
  public archives. On a confidential project you don't publish a fork
  of a public repository. You keep your patches next to your design
  and upstream only what's relevant and leaks nothing.

Either way, swap your own openroad binary into the dirty lane and see
whether a fix holds long before upstream ships it.

## "Dirty is bad"? No: dirty is the solution.

For a problem you haven't solved yet, dirty is the only thing that
works:

- **Turnaround.** A stage on a large design takes hours. Rebuilding
  everything before it, cleanly, for every experiment leaves you
  testing one idea a day. In the dirty lane you re-run only the step
  you changed, and get your answer in minutes.
- **Seeing.** The answer is in the state partway through a stage: an
  .odb before repair, the .sdc as the tool actually read it, a log
  you can grep. A sandbox hides that state on purpose; a directory
  leaves it there for you.
- **Shortcuts.** Get an .odb or .sdc however you can and run a
  downstream stage on it. Split a stage at a checkpoint. Borrow
  pieces from another run. That's how you get to the hard part
  without paying for everything before it again, and how a three-hour
  failure becomes a reproducer an upstream maintainer can run in
  seconds.
- **Equivalence checking.** kepler-formal LEC needs hacking and
  patches of its own (`patches/kepler-formal-*.patch`), and it pays
  for them: a passing LEC is a strong signal that a hand change kept
  the logic, which is what lets you, or an AI, do Verilog surgery
  (`SYNTH_VERILOG_SURGERY`, carried as
  [patches/0094](patches/0094-orfs-synth-verilog-surgery.patch)) or
  hand-code a netlist to close timing, and trust the result.
- **Throwaway work.** While you're exploring, nobody needs to
  reproduce the dead ends. They need to reproduce the answer, so
  being reproducible at that stage buys you nothing and costs you
  speed.
- **AI.** An assistant working through a problem needs the same fast,
  visible, editable loop you do. The dirty lane gives it that.

[docs/dirty-lane.md](docs/dirty-lane.md) has the commands.

## Solved problems are hermetic

So where does hermetic come in? Go back to what a flow is for:

**Solved problems should be hermetic and never change. Unsolved
problems need a workbench.**

Once you know the answer, plug it in as a flow setting, a script or a
carried patch, and wrap it up as a hermetic build: one tool to
install, every version pinned, every stage cached, the same answer on
any machine, today and next year
([docs/hermetic.md](docs/hermetic.md)). Git records it as if you'd got
it right the first time.

Hermetic is where your answers end up. Dirty is where you find them,
and you find them the way you always have.

### Carry patches while upstream decides

bazel-orfs is built to vendor patches, the way Bazel itself is. ORFS,
OpenROAD, Yosys and every other dependency is a pinned archive with a
`patches` list, so a project can carry a fix or a policy change for as
long as it needs to, and drop it the day upstream lands something better.

- **ORFS**: `orfs.source(commit = ..., integrity = ..., patches = [...])`
  in your `MODULE.bazel`. bazel-orfs applies its own ORFS patches from
  [patches/](patches/) first, then yours.
- **OpenROAD, Yosys, anything else**: `patches` on the `git_override` or
  `archive_override` in the root `MODULE.bazel`, as for any Bazel module.

This is not only for bugs. Many OpenROAD issues are about *policy*, where
the tool's default is reasonable for most users and wrong for one project,
and the upstream fix has to wait for a decision about the right knob.
Two from titan73's reports:

- [OpenROAD #8558](https://github.com/The-OpenROAD-Project/OpenROAD/issues/8558):
  the gap between power domains is a hard-coded six row heights in
  `ifp`. Upstream had to settle whether that becomes a global setter or an
  option on `initialize_floorplan` and `make_rows`, and whether domains
  need different gaps. For the project that hit it, the fix is a one-line
  patch changing a constant, which an AI writes in a minute and the
  project carries until the option ships.
- [OpenROAD #8771](https://github.com/The-OpenROAD-Project/OpenROAD/issues/8771):
  a cell library without tie cells. Upstream's answer was that this is a
  discouraged design style and low priority, which is a fair policy for
  OpenROAD and no help to a project with the library it has. A patched
  tool, or a fake tie-cell LEF carried as a source, is the project's
  problem to solve and bazel-orfs makes it a small one.

Compare [OpenROAD #6063](https://github.com/The-OpenROAD-Project/OpenROAD/issues/6063),
a straightforward bug that titan73 fixed upstream the same week. Bugs
should go upstream. Policy can wait upstream while you ship.

The same mechanism is how bazel-orfs itself develops: a PR here carries
the ORFS, OpenROAD and Yosys patches it needs, is tested against real
designs through `@orfs//flow/designs/...`, and the patches are upstreamed
one by one and deleted here as they land.

ORFS and OpenROAD are work in progress. For large designs expect to get
involved with the community, or to need a support contract with
[Precision Innovations](https://www.linkedin.com/in/tomspyrou/).

## Requirements

[Bazelisk](https://bazel.build/install/bazelisk). That is all.

Bazelisk reads [.bazelversion](./.bazelversion) and fetches the right
Bazel. That version is also a hard minimum: `MODULE.bazel` declares
`bazel_compatibility = [">=9.1.1"]`, so an older Bazel stops during module
resolution with an explicit version error rather than failing later in a
way that looks like a build bug. The floor applies to projects that depend
on bazel-orfs too, whatever their own `.bazelversion` says.

### Optional: nix and direnv

With [nix](https://nixos.org/download/) and
[direnv](https://direnv.net/docs/installation.html) (hooked into your
shell), a clone needs one command and no Bazelisk install:

```sh
git clone https://github.com/The-OpenROAD-Project/bazel-orfs.git
cd bazel-orfs
direnv allow
```

[.envrc](./.envrc) loads [shell.nix](./shell.nix), which puts a pinned
`bazelisk` on PATH. Where the host has a standard Linux layout (Ubuntu,
Debian, Fedora, RHEL, WSL, a container) it runs against the host directly:
no root, no setup. Where the layout is missing (NixOS), it runs in a
bubblewrap FHS that supplies it. The choice is made on every call;
`BAZEL_ORFS_FHS=1` or `0` forces it. The nixpkgs pin lives in
[npins/sources.json](./npins/sources.json); `npins update` moves it.

| Host | Works |
|---|---|
| Ubuntu, Debian, Fedora, RHEL 8+, SLES 15, WSL2, containers | yes, directly on the host |
| NixOS | yes, in the FHS |
| macOS | no: bazel-orfs builds on Linux only, and the shell says so |

Both paths have been tried on Ubuntu (the FHS one forced with
`BAZEL_ORFS_FHS=1`); the other rows are by design, not yet by test.

## Quick start

Run these from a clone of this repository:

```bash
git clone https://github.com/The-OpenROAD-Project/bazel-orfs.git
cd bazel-orfs
```

### Build an ORFS design and open it in the GUI

```bash
bazelisk run @orfs//flow/designs/asap7/gcd:gcd_final gui_final
```

This builds `gcd`, the smallest design shipped with ORFS, from RTL through
synthesis, floorplan, placement, clock tree synthesis, routing and final
reporting on the asap7 PDK, then opens the result in the OpenROAD GUI.
The first run also builds OpenROAD and Yosys from source,
which takes 30 to 60 minutes. Every later run is incremental and cached.

What you are looking at is ORFS's own `flow/designs/asap7/gcd/config.mk`,
read by bazel-orfs and turned into Bazel targets. You can try any other
design under `@orfs//flow/designs/<pdk>/<design>`. The target prefix is
the design's `DESIGN_NAME` from its `config.mk`, which is not always the
directory name, so list before guessing:

```bash
bazelisk run @orfs//flow/designs/asap7/uart:uart_final gui_final
bazelisk query '@orfs//flow/designs/nangate45/aes:*' | grep '_final$'
bazelisk run @orfs//flow/designs/nangate45/aes:aes_cipher_top_grt gui_grt
```

This is not how you describe your own project. The expectation is
idiomatic Bazel: an `orfs_flow()` in your own BUILD file, as in the next
section and in [examples/](examples/). Consuming `config.mk` as a
domain-specific language is a facility for experiments inside bazel-orfs:
try a theory across many real designs, carrying the OpenROAD, ORFS and
bazel-orfs patches it needs in a single pull request, before anything is
upstreamed. The canonical experiment is parameter tuning, such as racing
and pinning floorplan parameters across every ORFS design with the
auto-floorplan targets ([docs/auto_floorplan.md](docs/auto_floorplan.md)).
The ORFS designs are the right test bed for that because the OpenROAD
maintainers know every pebble on that beach: a shift in any of them is
recognised for what it is.

Mileage varies. It is a testing facility, not a supported way to build
every ORFS design: not all designs are hooked up, and an ORFS bump that
upsets one is a fix here, not an incident. See
[docs/orfs-design-builds.md](docs/orfs-design-builds.md) for what the
facility is for and how the `config.mk` files are consumed.

### Build the example flow

```bash
bazelisk run //examples:mac_final gui_final
```

[examples/](examples/) is the clean, fast, idiomatic version: a 20-line
multiply-accumulate in Verilog, a two-constraint SDC, and a BUILD file with one
`orfs_flow()`. It runs the full flow on asap7 in a couple of minutes and is
the template to copy for your own project.

### Results and the GUI

Stage results land under `bazel-bin/<package>/results/<pdk>/<design>/base/`
and reports under `bazel-bin/<package>/reports/...`. Every stage target is
also a `bazelisk run` entry point:

```bash
bazelisk run <target>_<stage> gui_<stage>    # OpenROAD's web viewer: prints a link
bazelisk run <target>_<stage> open_<stage>   # OpenROAD Tcl shell
bazelisk run @bazel-orfs//:odb_debug -- <target>_<stage>  # the viewer in the background, then its link
```

GUI and shell are available for `floorplan`, `place`, `cts`, `grt`,
`route` and `final`.

Not every flow in this repository runs to `final`. The regression flows
under `//test` stop as early as they can to keep CI fast, so a target such
as `//test:L1MetadataArray_route` may not exist. List what a design
provides before guessing:

```bash
bazelisk query 'filter("^//test:L1MetadataArray_(synth|floorplan|place|cts|grt|route|final)$", //test:*)'
```

## Write your own flow

This is [examples/BUILD](examples/BUILD), minus comments:

```starlark
load("//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "mac",
    arguments = FAST_SETTINGS | {
        "CORE_UTILIZATION": "40",
        "PLACE_DENSITY": "0.65",
    },
    sources = {
        "SDC_FILE": [":constraints.sdc"],
    },
    verilog_files = ["mac.v"],
)
```

`arguments` are ORFS variables, validated at build time against ORFS's
`variables.yaml`, so a typo fails the build instead of silently changing
nothing. `sources` are ORFS variables whose values are files. `FAST_SETTINGS`
is a dict of variables that turn off the slow, sign-off-oriented parts of
the flow; the example BUILD spells it out and
[docs/performance.md](docs/performance.md) explains each entry.

One `orfs_flow()` creates one target per stage, plus an abstract target
that emits the LEF and LIB for use as a macro in a parent design:

```
//examples:mac_synth
//examples:mac_floorplan
//examples:mac_place
//examples:mac_cts
//examples:mac_grt
//examples:mac_route
//examples:mac_final
//examples:mac_generate_abstract
```

Bazel knows which stage each variable belongs to. Change `PLACE_DENSITY`
and only placement and later stages rebuild; synthesis and floorplan come
from cache.

Where to go next:

- [docs/customize.md](docs/customize.md): variables, constraints, macros
  and abstracts, mock areas, iterating on floorplan settings, design space
  exploration.
- [docs/dirty-lane.md](docs/dirty-lane.md): the dirty lane. Deploy a
  stage to a directory under `tmp/` and re-run single substeps outside
  Bazel, with a locally built ORFS or OpenROAD if you like.
- [docs/performance.md](docs/performance.md): speeding up builds,
  monitoring long stages, where CI time goes.
- [docs/reference.md](docs/reference.md): target naming, dependency
  deployment, how Bazel takes over from the ORFS Makefile.
- [docs/schedule.md](docs/schedule.md): `orfs_schedule()`, a scheduler
  at home: a design's macros in waves that fit the machine's memory, the
  parent alone, managed by an AI skill.

### Examples versus tests

`examples/` and `test/` are different things, and the difference is kept
on purpose:

- **`examples/`** is written to be read. One design, its files next to it,
  nothing shared with other packages, no variant tricks. CI builds it so
  it cannot rot, but when clarity and coverage pull in different
  directions, clarity wins here.
- **`test/`** is written to break when a rule changes. Thousands of lines
  of fixtures, variants, mocked tools, sweeps and standalone stages, most
  of it exercising one rule attribute each. It is where coverage goes, and
  it is not a place to learn from.

Examples may double as tests. Tests are not examples.

## Use bazel-orfs from your own project

Add bazel-orfs, OpenROAD, ORFS and the slang frontend to your
`MODULE.bazel`. Bazel honours overrides only from the root module, so your
root repeats the pins and overrides bazel-orfs's own `MODULE.bazel` makes,
starting from the commits bazel-orfs pins; `bazelisk run @bazel-orfs//:bump`
keeps them current after that. The complete set, with the toolchain,
version overrides, patches and `.bazelrc` lines a from-source OpenROAD build
needs, is in
[docs/openroad.md](docs/openroad.md#root-modulebazel-requirements). The
core of it:

```starlark
bazel_dep(name = "bazel-orfs")
git_override(
    module_name = "bazel-orfs",
    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs.git",
    commit = "<bazel-orfs commit>",
)

bazel_dep(name = "openroad")
archive_override(
    module_name = "openroad",
    # Copy this block verbatim from bazel-orfs's MODULE.bazel at the
    # bazel-orfs commit above, with the patch files it names: its
    # patch_cmds fetch OpenROAD's submodules and apply bazel-orfs's fixes.
    # `bazelisk run @bazel-orfs//:bump` regenerates it on every bump.
    integrity = "...",
    patch_cmds = [...],
    patch_strip = 1,
    patches = [...],
    strip_prefix = "OpenROAD-<commit>",
    urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/<commit>.tar.gz"],
)
bazel_dep(name = "qt-bazel")
git_override(
    module_name = "qt-bazel",
    remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
    commit = "<the qt-bazel commit bazel-orfs pins>",
)
bazel_dep(name = "sv-elab", version = "<the version bazel-orfs uses>")
archive_override(
    module_name = "sv-elab",
    # Copy this block from bazel-orfs's MODULE.bazel too, with the patch
    # it names: it follows OpenROAD's third-party/sv-elab, and the bump
    # moves it with OpenROAD.
    integrity = "...",
    patch_strip = 1,
    patches = [...],
    strip_prefix = "sv-elab-<commit>",
    urls = ["https://github.com/povik/sv-elab/archive/<commit>.tar.gz"],
)

orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.source(
    commit = "<the ORFS commit bazel-orfs pins>",
    integrity = "<its integrity>",
)
orfs.default(
    yosys_plugins = ["@sv-elab//src/yosys_plugin:slang.so"],
)
use_repo(orfs, "gnumake")
```

Then `load("@bazel-orfs//:openroad.bzl", "orfs_flow")` in a BUILD file
and write the flow exactly as in [examples/BUILD](examples/BUILD).

All tools build from source by default. To use a system `openroad` or a
real `klayout` instead, or to override a tool on one target, see
[docs/tools.md](docs/tools.md). [docs/openroad.md](docs/openroad.md)
covers the from-source OpenROAD build and its gotchas.

To give an agent (Claude Code) in your workspace the skills, rules and
odb-debug MCP server bazel-orfs's own development uses, at the version
your `MODULE.bazel` pins, run `bazelisk run @bazel-orfs//:agent -- setup`
once and commit what it lists: [tools/agent](tools/agent/README.md).

## Find your way around

| I want to... | Go to |
|---|---|
| Run my first build | [Quick start](#quick-start) |
| Write a flow for my own design | [Write your own flow](#write-your-own-flow), [examples/](examples/) |
| Add bazel-orfs to my project | [Use bazel-orfs from your own project](#use-bazel-orfs-from-your-own-project) |
| Use a system OpenROAD or KLayout | [docs/tools.md](docs/tools.md) |
| Pass variables and constraints, force a rebuild | [docs/customize.md](docs/customize.md) |
| Create macros with LEF/LIB, estimate macro sizes | [docs/customize.md](docs/customize.md#work-with-macros-and-abstracts) |
| Tweak floorplan or placement and iterate | [docs/customize.md](docs/customize.md#tweak-and-iterate-on-designs) |
| Sweep design parameters | [docs/customize.md](docs/customize.md#design-space-exploration) |
| Hack in the dirty lane: run a substep, edit Tcl, use a local ORFS or OpenROAD | [docs/dirty-lane.md](docs/dirty-lane.md) |
| Speed up CI or development builds | [docs/performance.md](docs/performance.md) |
| Monitor a long-running build | [docs/performance.md](docs/performance.md#monitor-long-running-builds) |
| Understand where CI time goes | [docs/performance.md](docs/performance.md#where-ci-time-goes) |
| Query timing interactively | [docs/performance.md](docs/performance.md#query-timing-interactively) |
| Experiment across ORFS designs (the `config.mk` DSL) | [docs/orfs-design-builds.md](docs/orfs-design-builds.md) |
| Debug or create a `make issue` archive | [docs/reference.md](docs/reference.md#create-a-make-issue-archive), [docs/debugging.md](docs/debugging.md) |
| Diagnose a build failure on my host | [docs/debugging.md](docs/debugging.md#host-platform--older-distributions) |
| Fast PPA estimate, gate a PR against merge-base | [docs/estimate.md](docs/estimate.md) |
| Pin slow-to-build artifacts | [tools/pin/README.md](tools/pin/README.md) |
| Give my agent bazel-orfs's skills and MCP server | [tools/agent/README.md](tools/agent/README.md) |
| Upgrade bazel-orfs, ORFS or OpenROAD | [Upgrade bazel-orfs](#upgrade-bazel-orfs) |
| Target and stage naming, internals | [docs/reference.md](docs/reference.md) |

### Additional tools and integrations

| Tool | Description | Documentation |
|------|-------------|---------------|
| Artifact pinning | Cache long-running build results | [tools/pin](tools/pin/README.md) |
| SRAM macros | fakeram and mock SRAM | [sram](sram/README.md) |
| Equivalence checking (LEC) | kepler-formal logic equivalence, for bazel-orfs's own generators (dev-only) | [test/lec](test/lec/README.md) |

## Upgrade bazel-orfs

    bazelisk run @bazel-orfs//:bump

A single command that updates all version pins in your `MODULE.bazel` and
runs `bazelisk mod tidy`. It detects which project it's running in and does
the right thing — no need to remember which versions to update or where.

What it updates:

- **ORFS** commit and integrity (latest from GitHub)
- **bazel-orfs** git commit (latest from GitHub)
- **OpenROAD** git commit (latest from GitHub, if configured)

Before writing anything it checks that the ORFS patches bazel-orfs itself
carries (`ORFS_PATCHES` in `orfs_source.bzl`) still fit the ORFS commit it
is moving you to, and stops naming the patch and the commit if not -- the
alternative is a `ctx.patch` failure inside bazel-orfs's patch dir during
`mod tidy`, after `MODULE.bazel` was already rewritten. `--ignore` turns
that into a warning.

In downstream projects, it also injects commented-out boilerplate for
[building OpenROAD from source](docs/openroad.md) — uncomment to test the
latest OpenROAD before ORFS catches up. This is useful when an OpenROAD bug
fix or feature hasn't made it into ORFS yet.

`//:bump` rewrites the override shapes it recognizes and stops, naming the
block, when it meets one it does not — it never writes a partial
`MODULE.bazel`. If your file is old enough that a block is unrecognized,
re-seed it from the [root MODULE.bazel requirements](docs/openroad.md#root-modulebazel-requirements) and re-apply your edits. See
[Shapes the bumper recognizes](docs/openroad.md#shapes-the-bumper-recognizes).

## Repository layout

The root directory contains only external-facing concerns:

- `.bzl` rule files (`openroad.bzl`, `sweep.bzl`, `ppa.bzl`, etc.) loaded by downstream consumers
- `MODULE.bazel` and `BUILD` with public tools (`bump`, `plot_clock_period_tool`)
- Template files consumed by rules (`make.tpl`, `deploy.tpl`, `mock_area.tcl`)
- `tools/` (pin, deploy), `extensions/` (pin), `patches/` (vendored ORFS and dependency patches)

Everything else lives in subdirectories, split by purpose:

- `examples/` — the flow to copy. Read this first.
- `test/` — CI regression flows (tag_array_64x184, lb_32x128, L1MetadataArray, etc.) and their fixtures. Coverage, not clarity; see [Examples versus tests](#examples-versus-tests).
- `sram/` — SRAM macro tests with fakeram and megaboom variants
- `subpackage/` — cross-package reference tests
- `docs/` — everything linked from [Find your way around](#find-your-way-around)

Most files under `test/` are short implementation details easily derived from
context: Tcl helper scripts, SDC constraint files, and simple RTL are
boilerplate an LLM can regenerate from the BUILD target definitions.
Non-trivial files worth understanding: `test/rtl/L1MetadataArray.sv` (cache
metadata controller) and the plot scripts.
