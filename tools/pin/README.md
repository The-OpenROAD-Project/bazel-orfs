# Pinning of artifacts

Pinning artifacts can be useful with OpenROAD flows because some targets can take a very long time to run and hardly ever change:

- Netlist of a large register file, multiplier, floating point unit, etc. may hardly ever change, so pin these artifacts and only re-synthesize the parts of the design that is under active development
- Macro and pin placement is only known after placement, which can take a long time and also it may be desirable to keep macro placement and pin placement stable while other parts of the design changes.

## MODULE.bazel changes

Create a pinning repository:

```starlark
pin = use_extension("@bazel-orfs//:extensions/pin.bzl", "pin")
pin.artifacts(
    artifacts_lock = "//:artifacts_lock.txt",
    repo_name = "pinned",
)
use_repo(pin, "pinned")
```

## BUILD.bazel changes to define pinned artifacts

```starlark
pin_data(
    name = "pin",
    srcs = [
        ":someslowtarget",
    ],
    artifacts_lock = "artifacts_lock.txt",
    bucket = "some-google-bucket",
)
```

## Using pinned artifacts from a BUILD.bazel file

```starlark
filegroup(
    name = "foo",
        srcs = [
            "@pinned//someslowtarget",
            ..
```

## Updating pinned artifacts

This will build the artifacts, upload them to the bucket and update `artifacts_locked.txt`

    bazelisk run :pin
