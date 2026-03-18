# KLayout Integration

KLayout is an optional dependency in bazel-orfs used for GDS generation.
By default, bazel-orfs uses the locally installed `klayout` binary from your
system PATH. This can be overridden to use a custom binary or a mock for
CI/testing.

## Security Note

The default klayout wrapper (`@bazel-orfs//:klayout`) executes the
`klayout` binary found on the system `PATH`. This means any binary named
`klayout` in your `PATH` will be executed with the permissions of the Bazel
build. For hermetic builds or untrusted environments, override `klayout` to
point to a known binary (e.g., `@docker_orfs//:klayout` or a pinned
`http_archive`).

## Configuration

KLayout is configured through the `orfs_repositories` module extension in your
`MODULE.bazel`. The default points to the system-installed `klayout`:

```starlark
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default(
    image = "docker.io/openroad/orfs:...",
    # Override klayout with a custom binary:
    # klayout = "@my_klayout//:klayout",
)
```

To use klayout from the ORFS docker image instead of the system installation:

```starlark
orfs.default(
    image = "docker.io/openroad/orfs:...",
    klayout = "@docker_orfs//:klayout",
)
```

## GDS Generation with `orfs_gds`

The `orfs_gds` rule generates GDS files using klayout via the ORFS `do-gds`
make target. It takes a routed design as input and produces the final GDS:

```starlark
load("@bazel-orfs//:openroad.bzl", "orfs_gds")

orfs_gds(
    name = "my_design_gds",
    src = ":my_design_final",
)
```

The `orfs_gds` rule is separate from `orfs_final` to support flows where
klayout is not available or GDS generation is not needed.

## Mock KLayout for Testing

For CI and development, a mock klayout binary is provided that generates
dummy GDS files without requiring a real klayout installation. The mock is
configured as a dev dependency in this repository's `MODULE.bazel`:

```starlark
bazel_dep(name = "mock-klayout", version = "0.0.1", dev_dependency = True)

local_path_override(
    module_name = "mock-klayout",
    path = "mock/klayout",
)
```

The mock klayout parses `-rd out=<path>` arguments (matching klayout's
`-rd` flag for passing variables to scripts) and creates a minimal dummy
GDS file at the specified output path. This allows the full flow to
complete without a real klayout installation.

To use the mock in your own project, add it as a dev dependency and
override the klayout parameter:

```starlark
orfs.default(
    image = "docker.io/openroad/orfs:...",
    klayout = "@mock-klayout//src/bin:klayout",
)
```

## Testing

Run the mock klayout test to verify the dummy GDS generation:

```sh
bazel test //test/klayout:mock_klayout_test
```
