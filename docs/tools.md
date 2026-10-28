# Tool configuration

bazel-orfs builds all EDA tools from source by default. This works on all
platforms and requires only Bazelisk — no Docker, no system packages.
This page covers the knobs; [openroad.md](openroad.md) covers the
from-source OpenROAD build in depth.


KLayout defaults to a mock implementation since GDS output is the end of
the flow and not needed for most development. Override with a real klayout
when you need actual GDS files.

#### Build OpenROAD from source (default)

Add OpenROAD, ORFS and the slang frontend to your `MODULE.bazel`, with the
toolchain, overrides and `.bazelrc` lines in
[openroad.md](openroad.md#root-modulebazel-requirements). Start from the
commits bazel-orfs pins; `bazelisk run @bazel-orfs//:bump` keeps them
current after that.

First build takes 30-60 minutes; subsequent builds are incremental.
See [docs/openroad.md](openroad.md) for details and gotchas, and
[docs/debugging.md](debugging.md) for debugging tips (synthesis, bumps,
from-source toolchain, overrides, host platform).

#### Use locally installed tools

To use OpenROAD, yosys, or klayout from your system PATH:

```starlark
orfs.default(
    openroad = "@bazel-orfs//:openroad",  # uses `openroad` from PATH
)
```

The `@bazel-orfs//:openroad` and `@bazel-orfs//:klayout` targets are thin
wrappers that `exec` the corresponding binary from PATH.

#### Configure klayout

KLayout defaults to mock-klayout, which writes an empty GDS. To use a
real klayout for one build, without touching `MODULE.bazel` (handy when
hacking on bazel-orfs itself), pass the flag on the command line or put
it in `user.bazelrc`:

```
build --@bazel-orfs//:klayout_tool=@bazel-orfs//:klayout
```

`@bazel-orfs//:klayout` runs `klayout` from the action's `PATH`, which
`--incompatible_strict_action_env` sets to `/bin:/usr/bin:/usr/local/bin`;
for an install elsewhere, point the flag at a label of your own that
runs it.

To make it the default, override it globally in `MODULE.bazel`:

```starlark
orfs.default(
    klayout = "@bazel-orfs//:klayout",  # system klayout from PATH
)
```

#### Per-target overrides

Any tool can be overridden on individual targets:

```starlark
orfs_flow(
    name = "my_design",
    openroad = "@openroad//:openroad",
    klayout = "@bazel-orfs//:klayout",
    verilog_files = ["my_design.v"],
)
```
