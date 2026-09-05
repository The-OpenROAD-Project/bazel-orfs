# bazel-orfs

[Bazel](https://bazel.build/) rules for running
[OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
(ORFS): RTL to GDS with OpenROAD, Yosys and an open PDK, driven by
`bazelisk build`.

## Why Bazel on top of ORFS?

**Nothing to install.** Bazel downloads, builds and caches every
dependency: OpenROAD, OpenSTA, Yosys, ABC, GNU Make, Qt, Python, the C++
toolchain and the PDKs. A developer machine or a CI runner needs Bazelisk
and a standard Linux install, and gets a bit-for-bit reproducible flow. No
Docker, no `apt install`, no "works on my machine". The RHEL 8 story in
[bazel-orfs #869](https://github.com/The-OpenROAD-Project/bazel-orfs/issues/869)
is what this buys you: the two things that broke were a host `curl` and a
host Python that had leaked into the build, and both were fixed by making
them hermetic.

**Plumbing an AI understands.** bazel-orfs has turned out to be the
right shape for AI-assisted work. Every input is a label, every stage is a
target, every variable is checked against ORFS's own `variables.yaml`, and
a stage that fails can be re-run outside the sandbox with one command. An
AI assistant wires up a new design, a new PDK or a patched tool without
being told how, because there is exactly one way to do each of those
things and the build tells you when you got it wrong.

**All of Bazel, all of ORFS.** Artifacts, parallel builds, remote caching,
remote execution, and a flow that only rebuilds the stages a change
touches. ORFS is used unmodified, so you get the latest OpenROAD and ORFS
features, the ORFS debugging tools such as `make issue` and
`deltaDebug.py`, and GitHub issues you file are immediately actionable for
the OpenROAD and ORFS maintainers.

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
The first run also builds OpenROAD, Yosys and the Qt GUI from source,
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
bazelisk run <target>_<stage> gui_<stage>    # OpenROAD GUI
bazelisk run <target>_<stage> open_<stage>   # OpenROAD Tcl shell
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
- [docs/local-flow.md](docs/local-flow.md): deploy a stage to a directory
  under `tmp/` and re-run single substeps outside Bazel, with a locally
  built ORFS if you like.
- [docs/performance.md](docs/performance.md): speeding up builds,
  monitoring long stages, where CI time goes.
- [docs/reference.md](docs/reference.md): target naming, dependency
  deployment, how Bazel takes over from the ORFS Makefile.

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

Add bazel-orfs and OpenROAD to your `MODULE.bazel`. The OpenROAD and Qt
pins must be in the root module because Bazel only honours overrides from
there; `bazelisk run @bazel-orfs//:bump` fills them in and keeps them
current.

```starlark
bazel_dep(name = "bazel-orfs")
git_override(
    module_name = "bazel-orfs",
    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs.git",
    commit = "<bazel-orfs commit>",
)

bazel_dep(name = "openroad")
git_override(
    module_name = "openroad",
    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",
    commit = "<openroad commit>",
    init_submodules = True,
)
bazel_dep(name = "qt-bazel")
git_override(
    module_name = "qt-bazel",
    remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
    commit = "df022f4ebaa4130713692fffd2f519d49e9d0b97",
)

orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default()
use_repo(orfs, "gnumake")
```

Then `load("@bazel-orfs//:openroad.bzl", "orfs_flow")` in a BUILD file
and write the flow exactly as in [examples/BUILD](examples/BUILD).

All tools build from source by default. To use a system `openroad` or a
real `klayout` instead, or to override a tool on one target, see
[docs/tools.md](docs/tools.md). [docs/openroad.md](docs/openroad.md)
covers the from-source OpenROAD build and its gotchas.

## Carry patches while upstream decides

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
| Run a single substep, edit Tcl, use a local ORFS | [docs/local-flow.md](docs/local-flow.md) |
| Speed up CI or development builds | [docs/performance.md](docs/performance.md) |
| Monitor a long-running build | [docs/performance.md](docs/performance.md#monitor-long-running-builds) |
| Understand where CI time goes | [docs/performance.md](docs/performance.md#where-ci-time-goes) |
| Query timing interactively | [docs/performance.md](docs/performance.md#query-timing-interactively) |
| Experiment across ORFS designs (the `config.mk` DSL) | [docs/orfs-design-builds.md](docs/orfs-design-builds.md) |
| Debug or create a `make issue` archive | [docs/reference.md](docs/reference.md#create-a-make-issue-archive), [docs/debugging.md](docs/debugging.md) |
| Diagnose a build failure on my host | [docs/debugging.md](docs/debugging.md#host-platform--older-distributions) |
| Fast PPA estimate, gate a PR against merge-base | [docs/estimate.md](docs/estimate.md) |
| Pin slow-to-build artifacts | [tools/pin/README.md](tools/pin/README.md) |
| Upgrade bazel-orfs, ORFS or OpenROAD | [Upgrade bazel-orfs](#upgrade-bazel-orfs) |
| Target and stage naming, internals | [docs/reference.md](docs/reference.md) |

### Additional tools and integrations

| Tool | Description | Documentation |
|------|-------------|---------------|
| Artifact pinning | Cache long-running build results | [tools/pin](tools/pin/README.md) |
| Post-synthesis cleanup | najaeda netlist cleaning (experimental) | [naja](naja/README.md) |
| SRAM macros | fakeram and mock SRAM | [sram](sram/README.md) |
| Equivalence checking (LEC) | kepler-formal logic equivalence | [lec](lec/README.md) |

LEC lives in a subdirectory that is a **separate Bazel module**. Downstream
consumers add their own `bazel_dep` and `git_override` for it:

| Sub-module directory | Bazel module name | What it provides |
|----------------------|-------------------|------------------|
| `lec/` | `bazel-orfs-lec` | Logic equivalence checking |

```starlark
bazel_dep(name = "bazel-orfs-lec")

git_override(
    module_name = "bazel-orfs-lec",
    commit = "<same commit as bazel-orfs>",
    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs",
    strip_prefix = "lec",
)
```

## Upgrade bazel-orfs

    bazelisk run @bazel-orfs//:bump

A single command that updates all version pins in your `MODULE.bazel` and
runs `bazelisk mod tidy`. It detects which project it's running in and does
the right thing — no need to remember which versions to update or where.

What it updates:

- **ORFS** commit and integrity (latest from GitHub)
- **bazel-orfs** git commit (latest from GitHub)
- **OpenROAD** git commit (latest from GitHub, if configured)

In downstream projects, it also injects commented-out boilerplate for
[building OpenROAD from source](docs/openroad.md) — uncomment to test the
latest OpenROAD before ORFS catches up. This is useful when an OpenROAD bug
fix or feature hasn't made it into ORFS yet.

`//:bump` supports `MODULE.bazel` files whose `bazel-orfs` pin is **at most
30 days behind the commit being bumped to** — measured between commit
dates, not against the clock. An older pin is a hard stop that tells you
how to re-seed the file. See
[Supported window](docs/openroad.md#supported-window) for why, and for the
matching cleanup policy on the bumper's own compatibility code.

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
