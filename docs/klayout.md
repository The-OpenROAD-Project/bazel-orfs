# KLayout Integration

KLayout is an optional dependency in bazel-orfs used for GDS generation.
GDS generation is separated from the main flow (`orfs_flow`) into the
standalone `orfs_gds` rule, so designs can complete synthesis through
final reporting without requiring klayout.

By default, bazel-orfs uses the klayout binary from the ORFS docker image
(`@docker_orfs//:klayout`). This can be overridden globally via
`orfs.default()` or per-target via the `klayout` attribute on `orfs_gds`.

## Configuration

KLayout is configured through the `orfs_repositories` module extension in your
`MODULE.bazel`. The default uses the docker image klayout:

```starlark
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default(
    image = "docker.io/openroad/orfs:...",
    # Override klayout globally:
    # klayout = "@my_klayout//:klayout",
)
```

To use a locally installed klayout from your system PATH instead:

```starlark
orfs.default(
    image = "docker.io/openroad/orfs:...",
    klayout = "@bazel-orfs//:klayout",
)
```

Note: the `@bazel-orfs//:klayout` wrapper executes whichever `klayout`
binary is found on the system `PATH`. For hermetic builds, prefer the
docker image default or a pinned `http_archive`.

## GDS Generation with `orfs_gds`

The `orfs_gds` rule generates GDS files using klayout via the ORFS `do-gds`
make target. It takes a completed design (from `orfs_final`) as input and
produces the final GDS:

```starlark
load("@bazel-orfs//:openroad.bzl", "orfs_gds")

orfs_gds(
    name = "my_design_gds",
    src = ":my_design_final",
)
```

The `klayout` attribute can be overridden per-target. When not set, it
defaults to the global klayout configured in `orfs.default()`:

```starlark
orfs_gds(
    name = "my_design_gds",
    src = ":my_design_final",
    klayout = "@mock-klayout//src/bin:klayout",
)
```

## Assembling Macros with `orfs_macro`

Use `orfs_macro` to assemble `.lef`, `.lib`, and optionally `.gds` files
from different sources into a single macro target. GDS is optional:

```starlark
load("@bazel-orfs//:openroad.bzl", "orfs_gds", "orfs_macro")

# Without GDS (klayout not required)
orfs_macro(
    name = "my_macro",
    lef = ":my_design_generate_abstract",
    lib = ":my_design_generate_abstract",
    module_top = "my_design",
)

# With GDS
orfs_macro(
    name = "my_macro_with_gds",
    gds = ":my_design_gds",
    lef = ":my_design_generate_abstract",
    lib = ":my_design_generate_abstract",
    module_top = "my_design",
)
```

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

The mock klayout handles `-v` (version query), `-rd out=<path>`, and
`-rd out_file=<path>` arguments, creating minimal dummy GDS files at
the specified output paths. This allows the GDS generation step to
complete without a real klayout installation.

To use the mock per-target in tests:

```starlark
orfs_gds(
    name = "my_design_gds",
    src = ":my_design_final",
    klayout = "@mock-klayout//src/bin:klayout",
)
```

## Testing

Run the tests to verify klayout integration:

```sh
# Mock klayout unit test
bazel test //test/klayout:mock_klayout_test

# End-to-end macro assembly test (uses mock klayout for GDS)
bazel test //test:lb_32x128_sky130hd_macro_test

# Smoke test (flow without GDS)
bazel test //test/smoketest:lb_32x128_sky130hd_build_test
```
