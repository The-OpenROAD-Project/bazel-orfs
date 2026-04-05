# OpenROAD Demo Gallery

Build, explore, and test [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD)
with real open-source ASIC designs — without cloning their repos.

This project provides **examples and testing of OpenROAD** by building
third-party RTL projects through the full RTL-to-GDS flow using
[bazel-orfs](https://github.com/The-OpenROAD-Project/bazel-orfs), **out of band**
from the project's home repository. Bazel fetches all source code and
dependencies directly from upstream. This repo contains only configuration:
`MODULE.bazel`, `BUILD` files, SDC constraints, and patch files.

The focus is on getting something up and running quickly — initial results use
aggressive speed defaults for fast turnaround. Quality of Results (QoR) will
increase dramatically with limited effort into tweaking the settings and steps
for the build flow for each project. Project maturity is indicated in the table below.

[bazel-orfs](https://github.com/The-OpenROAD-Project/bazel-orfs) allows special
handling of projects to maximize QoR or do project-specific interesting things —
hierarchical synthesis with custom macro abstracts, per-stage argument overrides,
mock memory generation, and more.

Each demo project independently verifies that OpenROAD can handle real-world
designs across different domains (CPUs, multipliers, accelerators), serving
as both a showcase and a regression test suite for the OpenROAD flow.

**Pull requests welcome!** See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add projects and use Claude Code skills.

## How to Use This Repository

Don't try to read all of this yourself. Point an AI at it.

Each project directory contains a README with quantitative build results,
collected logs, JSON metrics, and reports from every ORFS stage that completed.
This data is designed to be consumed by Claude (or any LLM) — it's small,
structured, and self-describing.

**To build your own project**, clone this repo, open Claude Code, and ask:

> Read the project READMEs for serv, vlsiffra, and gemmini. Look at their
> BUILD.bazel files, build_times.yaml, and collected metrics. Then make a plan
> for building my project `<your-project>` — what parameters to start with,
> what to watch for, and how long it might take.

Claude can compare your design against existing projects, predict which stages
will be slow, suggest hierarchical decomposition if needed, and estimate
memory requirements — all from the data already collected here.

**To learn from existing builds**, ask Claude to read the logs and metrics:

> Compare the routing behavior of serv vs. gemmini. Why did gemmini OOM?
> What would need to change to make it fit in 30 GB RAM?

The accumulated data across projects is more useful than any single project's
results. See [PHILOSOPHY.md](PHILOSOPHY.md) for the approach.

## Projects

| Project | Description | PDK | Reported Freq | Reproduced Freq | Cells | Area (μm²) | Version | Project version | Last updated | Status |
|---------|-------------|-----|---------------|-----------------|-------|-------------|---------|-----------------|--------------|--------|
| [serv](serv/) | Bit-serial RISC-V CPU | ASAP7 | — | 0.89 GHz | 8,350 | 1,024 | | `f5ddfaa` | 2026-03-18 | Done |
| [vlsiffra](vlsiffra/) | 32-bit pipelined multiplier | ASAP7 | 2.7 GHz | 1.52 GHz | 5,489 | 706 | | `22e7acc` | 2026-03-18 | Done |
| [gemmini](gemmini/) | 16×16 INT8 systolic array (Chisel) | ASAP7 | — | 0.63 GHz | 896,465 | 103,705 | | `8c3f992` | 2026-03-19 | GRT |
| [gemmini_4x4](gemmini_4x4/) | 4×4 INT8 systolic array (Chisel) | ASAP7 | — | 0.74 GHz | 48,454 | 5,840 | `97416b2` | `8c3f992` | 2026-03-19 | Route |
| [gemmini_2x2](gemmini_2x2/) | 2×2 INT8 systolic array (Chisel) | ASAP7 | — | 0.73 GHz | 13,174 | 1,591 | `97416b2` | `8c3f992` | 2026-03-19 | Route |
| [gemmini_8x8](gemmini_8x8/) | 8×8 INT8 systolic array, flat (Chisel) | ASAP7 | — | — | — | — | | `8c3f992` | 2026-03-19 | New |
| [gemmini_8x8_abutted](gemmini_8x8_abutted/) | 8×8 systolic array, abutted macros (Chisel) | ASAP7 | 1 GHz | 0.74 GHz | 65,139 | 52,370 | `51ad123` | `8c3f992` | 2026-03-24 | CTS |
| [coralnpu](coralnpu/) | RISC-V NPU core with FPU (Chisel) | ASAP7 | — | — | 112,266 | 20,230 | | `04c48f5` | 2026-03-21 | GRT |
| [picorv32](picorv32/) | Size-optimized RISC-V RV32IMC CPU | ASAP7 | — | 0.84 GHz | 12,159 | 1,446 | `51ad123` | `87c89ac` | 2026-03-23 | Done |
| [pymtl3](pymtl3/) | Stream checksum unit (pymtl3) | ASAP7 | — | 0.42 GHz | 1,678 | 192 | `46ea257` | `ea5ca68` | 2026-03-24 | Done |
| [cva6](cva6/) | RISC-V CPU (CVA6 cv32a60x, HPDcache) | ASAP7 | — | 0.29 GHz | 80,306 | 15,189 | | `02e11e3` | 2026-03-25 | Place |
| [tensor_accelerator](tensor_accelerator/) | 4-level hierarchical TPU (4×TPC, systolic arrays) | ASAP7 | — | — | — | 44,562 | | `ae1078d` | 2026-03-25 | CTS |
| [genben](genben/) | 5-stage pipelined RISC-V CPU (GenBen GA_94) | ASAP7 | — | — | 14,032 | — | | `a103f9a` | 2026-03-25 | Place |

<details>
<summary>Column descriptions</summary>

- **Project**: Link to the project's directory with build files and README
- **Description**: Short description of the design
- **PDK**: Process design kit used (e.g., ASAP7 7nm)
- **Reported Freq**: Frequency reported in the upstream project's publications or README
- **Reproduced Freq**: Frequency achieved by this demo (1 / (clock_period − WNS) if WNS < 0)
- **Cells**: Total standard cell count after synthesis + physical optimization
- **Area (μm²)**: Total cell area
- **Version**: Git hash of *this repository* when the results were produced. Check out this
  version to reproduce the build results in the gallery. Run `/demo-update` to refresh on latest main.
- **Project version**: Short git hash of the upstream project source (`MODULE.bazel` `http_archive`)
- **Last updated**: Date when metrics were last refreshed
- **Status**: "Done" = full flow completed; "Building" = work in progress

</details>

_Run `/demo-update <project>` to refresh statistics after a build._

| [serv](serv/) | [vlsiffra](vlsiffra/) | [gemmini_2x2](gemmini_2x2/) | [gemmini_4x4](gemmini_4x4/) | [picorv32](picorv32/) |
|:--------:|:--------:|:--------:|:--------:|:--------:|
| [<img src="docs/serv/route.webp" width="150">](serv/) | [<img src="docs/vlsiffra/route.webp" width="150">](vlsiffra/) | [<img src="docs/gemmini_2x2/route.webp" width="150">](gemmini_2x2/) | [<img src="docs/gemmini_4x4/route.webp" width="150">](gemmini_4x4/) | [<img src="docs/picorv32/route.webp" width="150">](picorv32/) |

| [gemmini_8x8](gemmini_8x8/) | [gemmini_8x8_abutted](gemmini_8x8_abutted/) | [gemmini](gemmini/) | [coralnpu](coralnpu/) | [pymtl3](pymtl3/) |
|:--------:|:--------:|:--------:|:--------:|:--------:|
| [<img src="docs/gemmini_8x8/route.webp" width="150">](gemmini_8x8/) | [<img src="docs/gemmini_8x8_abutted/route.webp" width="150">](gemmini_8x8_abutted/) | [<img src="docs/gemmini/route.webp" width="150">](gemmini/) | [<img src="docs/coralnpu/route.webp" width="150">](coralnpu/) | [<img src="docs/pymtl3/route.webp" width="150">](pymtl3/) |

| [cva6](cva6/) | [tensor_accelerator](tensor_accelerator/) | [genben](genben/) |
|:--------:|:--------:|:--------:|
| [<img src="docs/cva6/route.webp" width="150">](cva6/) | [<img src="docs/tensor_accelerator/place.webp" width="150">](tensor_accelerator/) | [<img src="docs/genben/place.webp" width="150">](genben/) |

## Upcoming

| Project | Description | Link |
|---------|-------------|------|
| MegaBoom | 4-wide RISC-V OoO core (BoomTile from Chisel source) | [riscv-boom](https://github.com/riscv-boom/riscv-boom) · [plan](docs/megaboom/PLAN.md) |
| OpenTitan (Ibex) | Google/lowRISC secure RISC-V microcontroller core | [lowRISC/ibex](https://github.com/lowRISC/ibex) |
| Basilisk | PULP team Linux-capable RISC-V core | [pulp-platform/basilisk](https://github.com/pulp-platform/basilisk) |

Want to try? Clone this project, start Claude Code, and run `/demo-add <project-name-or-url>`.
If you get stuck, create a PR and ask for help.

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│  This repo (tiny — just config)                         │
│  MODULE.bazel ──► Bazel fetches:                        │
│    ├── bazel-orfs (build rules)                         │
│    ├── vlsiffra source (Python + Verilog)               │
│    └── ORFS Docker image (OpenROAD + PDK)               │
│                                                         │
│  vlsiffra/BUILD.bazel:                                  │
│    1. genrule: run Amaranth HDL → Verilog               │
│    2. orfs_flow: Verilog → synthesize → place → route   │
│                  → GDS                                  │
└─────────────────────────────────────────────────────────┘
```

No source code is copied into this repository. No dependencies are vendored.
Everything is fetched by Bazel from upstream at build time. Each project is
pinned to a specific git commit hash via `http_archive` in `MODULE.bazel`.
If upstream source needs modifications for the ORFS flow (unsupported language
constructs, synthesis workarounds), patches are created in `<project>/patches/`
and managed idiomatically through Bazel's `http_archive` `patches` attribute.

## Dependencies

The only dependency you need to install is
[bazelisk](https://github.com/bazelbuild/bazelisk). Bazel then fetches
everything else automatically on the first build:

- **Bazel** itself (version pinned in `.bazelversion`)
- **OpenROAD + Yosys + PDKs** (extracted from a Docker image — no Docker needed at runtime)
- **Python toolchain + packages** (Amaranth HDL, Pillow, etc.)
- **RTL source code** for each project (from upstream GitHub repos)

No system compilers, no manual package installs, no Docker daemon required.

## Quick Start

1. Install [bazelisk](https://github.com/bazelbuild/bazelisk)
2. Build a project:

```bash
# Synthesize vlsiffra multiplier
bazel build //vlsiffra:multiplier_synth

# Full RTL-to-GDS flow
bazel build //vlsiffra:multiplier_final

# Open in OpenROAD GUI after routing
bazel run //vlsiffra:multiplier_route -- $(pwd)/route gui_route
```

## Testing

`bazel test //...` is designed to be fast — it exercises the full ORFS flow
using **mock tools** (mock-openroad + mock-yosys) that complete in seconds.
Only one small design (`smoketest/counter`) also builds with real OpenROAD
and Yosys, providing an A/B comparison between mock and real outputs.

All other designs' real builds are tagged `manual` and skipped by
`bazel test //...`. To run a specific design's real flow:

```bash
bazel build //serv:serv_rf_top_final
```

## Build Times

![Build Times by Stage](docs/build_times.png)

_Updated by `bazelisk run //scripts:build_time_chart`. See [build_times.yaml](build_times.yaml) for raw data._

## Research Questions

Things we'd like to learn from the accumulated data across projects:

- **Build time prediction** — can we predict per-stage runtime from post-synthesis
  metrics (cell count, hierarchy depth, memory count)? A model that estimates
  "this design will take ~6 hours to route and need ~29 GB RAM" after synthesis
  would save hours of wasted builds. The data in `build_times.yaml` and per-project
  metrics JSONs is the training set.
- **Macro decomposition heuristics** — when should a flat design be split into
  macros? Is there a cell count threshold (e.g. >100K cells flat = always decompose)?
  How does routing time scale with cell count — linear, quadratic, worse?
- **Slack margin tuning** — can we predict the right `SETUP_SLACK_MARGIN` from
  the post-synthesis WNS to avoid futile timing repair? Current approach is
  reactive (observe WNS, set margin); a predictive model would save a full
  floorplan iteration.
- **Memory vs. threads tradeoff** — how does peak memory scale with thread count
  during detail routing? Can we auto-select threads to fit available RAM?
- **Design complexity fingerprinting** — do certain design patterns (systolic
  arrays, pipelined datapaths, control-heavy FSMs) have predictable ORFS
  behavior? Can we classify a design after synthesis and apply known-good
  parameters?

These questions motivate the data collection approach described in
[PHILOSOPHY.md](PHILOSOPHY.md).

## Development Tips

### Working on upstream projects

Use `git worktree add` to check out upstream projects in the `upstream/`
directory so Claude can find them faster and you can create patches and
commits directly:

```bash
# Add a worktree for the upstream project you're patching
git -C ~/OpenROAD-flow-scripts worktree add $(pwd)/upstream/OpenROAD-flow-scripts main
git -C ~/megaboom worktree add $(pwd)/upstream/megaboom main

# Work on patches, then generate a diff for http_archive patches
cd upstream/megaboom
# ... make changes ...
git diff > ../../coralnpu/patches/my_fix.patch
```

The `upstream/` directory is in `.gitignore` and `.bazelignore`.

## Philosophy

See [PHILOSOPHY.md](PHILOSOPHY.md) — building mental models over automation,
no-estimates via real data, and CI-less by design.

## License

BSD 3-Clause License — same as [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD).
See [LICENSE](LICENSE).

This repository contains **no third-party source code**. It only references
upstream projects by URL and commit hash. Bazel fetches all source code at
build time from the original repositories. Where modifications are needed for
the ORFS flow, small patch files are maintained in `<project>/patches/` —
these are original works describing changes, not copies of the upstream code.
This approach avoids licensing entanglement: the repository contains only
configuration, build rules, and patches.
