"""
This module extension provides rules for OpenROAD-flow-scripts build stages.

By default, tools are real implementations: OpenROAD and OpenSTA from
the @openroad module, yosys from the Bazel Central Registry (@yosys),
GNU Make from source (@gnumake).  Only klayout uses a mock (mock-klayout)
since GDS generation is end-of-line and most users don't need it.

Users override individual tools via orfs.default() tag attributes.

A stub @docker_orfs repo with no-op executables is always created to
satisfy any residual label references in attrs.bzl.

A docker_orfs_image repo is also created, providing the OpenROAD binary
from the latest ORFS Docker image.  It is lazily fetched — the multi-GB
download only happens when a target from @docker_orfs_image is built
(e.g. via @bazel-orfs//:openroad-latest).
"""

load("//:config.bzl", "global_config")
load("//:docker.bzl", "docker_pkg")
load("//:gnumake.bzl", "gnumake")
load("//:load_json_file.bzl", "load_json_file")
load("//:mock_klayout.bzl", "mock_klayout")
load("//:stub.bzl", "stub_docker_orfs")

# Latest ORFS Docker image — bump.py keeps these in sync.
LATEST_ORFS_IMAGE = "docker.io/openroad/orfs:26Q2-32-gca75a11e2"
LATEST_ORFS_SHA256 = "a50429aaed8cbaf2103b46196507f7c9445c95066d00a91953bd47c27dad6f31"

_default_tag = tag_class(
    attrs = {
        "image": attr.string(
            mandatory = False,
            doc = "Deprecated: Docker image is no longer used. Accepted for backward compatibility.",
        ),
        "sha256": attr.string(
            mandatory = False,
            doc = "Deprecated: Docker image is no longer used. Accepted for backward compatibility.",
        ),
        "klayout": attr.label(
            mandatory = False,
            cfg = "exec",
        ),
        "make": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@gnumake//:make"),
        ),
        "makefile": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:makefile"),
        ),
        "makefile_yosys": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:makefile_yosys"),
        ),
        "openroad": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@openroad//:openroad"),
        ),
        "opensta": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@openroad//src/sta:opensta"),
        ),
        "pdk": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:asap7"),
        ),
        "yosys": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@yosys//:yosys"),
        ),
        "variables_yaml": attr.label(
            mandatory = False,
            default = Label("@orfs//flow:scripts/variables.yaml"),
        ),
        "yosys_abc": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@abc//:abc_bin"),
        ),
        "yosys_share": attr.label(
            mandatory = False,
            default = Label("@yosys//:yosys_share"),
        ),
    },
)

def _orfs_repositories_impl(module_ctx):
    # Stub repo with no-op executables for residual @docker_orfs references
    stub_docker_orfs(name = "docker_orfs")

    # Docker image repo — lazily fetched only when a target is built.
    # Provides @docker_orfs_image//:openroad (aliased as @bazel-orfs//:openroad-latest).
    docker_pkg(
        name = "docker_orfs_image",
        build_file = Label("//:docker_openroad.BUILD.bazel"),
        image = LATEST_ORFS_IMAGE,
        sha256 = LATEST_ORFS_SHA256,
        # Post-extraction fixups:
        # 1. Delete BUILD files that would create subpackages
        # 2. Symlink libtclreadline.so into the tclreadline package dir
        #    so Tcl's `load [file dirname [info script]]/libtclreadline.so`
        #    finds it (the absolute /usr/lib/... path doesn't work in the sandbox)
        patch_cmds = [
            "find OpenROAD-flow-scripts -name BUILD -delete -o -name BUILD.bazel -delete",
            "ln -sf ../../../x86_64-linux-gnu/libtclreadline-2.3.8.so usr/lib/tcltk/x86_64-linux-gnu/tclreadline2.3.8/libtclreadline.so || true",
        ],
    )

    # GNU Make built from source
    gnumake(name = "gnumake")

    # Mock klayout that produces dummy GDS files — used as default
    # when no real klayout is provided by the consumer.
    mock_klayout(name = "mock_klayout")

    for default in module_ctx.modules[0].tags.default:
        global_config(
            name = "config",
            klayout = default.klayout if default.klayout else "@mock_klayout//:klayout",
            make = default.make,
            makefile = default.makefile,
            makefile_yosys = default.makefile_yosys,
            openroad = default.openroad,
            opensta = default.opensta,
            pdk = default.pdk,
            yosys = default.yosys,
            yosys_abc = default.yosys_abc,
            yosys_share = default.yosys_share,
        )

        load_json_file(
            name = "orfs_variable_metadata",
            src = default.variables_yaml,
        )

orfs_repositories = module_extension(
    implementation = _orfs_repositories_impl,
    tag_classes = {
        "default": _default_tag,
    },
)
