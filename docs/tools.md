# Tool configuration

bazel-orfs builds all EDA tools from source by default. This works on all
platforms and requires only Bazelisk — no Docker, no system packages.
This page covers the knobs; [openroad.md](openroad.md) covers the
from-source OpenROAD build in depth.


KLayout defaults to a mock implementation since GDS output is the end of
the flow and not needed for most development. Override with a real klayout
when you need actual GDS files.

#### Build OpenROAD from source (default)

Add OpenROAD to your `MODULE.bazel`. Run `bazelisk run @bazel-orfs//:bump`
to auto-fill the latest commit, or specify a version manually:

```starlark
bazel_dep(name = "openroad")
git_override(
    module_name = "openroad",
    commit = "<openroad-commit-sha>",
    init_submodules = True,
    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",
)
bazel_dep(name = "qt-bazel")
git_override(
    module_name = "qt-bazel",
    commit = "df022f4ebaa4130713692fffd2f519d49e9d0b97",
    remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
)
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default()
use_repo(orfs, "gnumake")
```

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

KLayout defaults to mock-klayout. To use a real klayout, add to `user.bazelrc`:

```
build --@bazel-orfs//:klayout=@bazel-orfs//:klayout
```

Or override globally in `MODULE.bazel`:

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
