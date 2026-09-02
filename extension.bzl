"""
This module extension provides rules for OpenROAD-flow-scripts build stages.

Tools are built from source: OpenROAD and OpenSTA from the @openroad
module, yosys from the Bazel Central Registry (@yosys), ABC from BCR
(@abc), and GNU Make from source (@gnumake).  Only klayout uses a mock
(mock-klayout) since GDS generation is end-of-line and most users
don't need it.

Users override individual tools via orfs.default() tag attributes.

To replace the bazel-built @gnumake//:make with a host-installed make
(e.g. on macOS where the LLVM toolchain isn't registered), use Bazel's
standard --override_repository=+orfs_repositories+gnumake=... flag in
user.bazelrc — see the docstring in //:gnumake.bzl for a copy-paste
overlay example.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("//:config.bzl", "global_config")
load("//:gnumake.bzl", "gnumake")
load("//:load_json_file.bzl", "load_json_file")
load("//:mock_klayout.bzl", "mock_klayout")
load("//:orfs_source.bzl", "orfs_archive_args")

_source_tag = tag_class(
    attrs = {
        "commit": attr.string(
            doc = "ORFS commit to fetch. Required: there is no default, " +
                  "because the ORFS commit decides which designs, PDKs " +
                  "and flow scripts you build against.",
        ),
        "integrity": attr.string(
            doc = "Subresource Integrity string for the ORFS tarball, " +
                  "e.g. \"sha256-...\". Required. A failing fetch prints " +
                  "the observed value.",
        ),
        "urls": attr.string_list(
            doc = "Override where the tarball comes from. Defaults to " +
                  "the canonical ORFS GitHub archive for `commit`. Use " +
                  "for a mirror, an air-gapped cache, or a fork -- " +
                  "GitHub's /archive/<sha> on the canonical repo does " +
                  "not reliably serve a commit that exists only on a " +
                  "fork, even one that is an open PR's head.",
        ),
    },
)

_default_tag = tag_class(
    attrs = {
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
        "openroad_qt": attr.label(
            mandatory = False,
            cfg = "exec",
            default = Label("@openroad//:openroad-qt"),
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
        "yosys_plugins": attr.label_list(
            mandatory = False,
            doc = "Extra .so plugin files to expose via YOSYS_PLUGIN_PATH " +
                  "during yosys actions. Use to load out-of-tree plugins " +
                  "(e.g. yosys-slang) without merging them into yosys_share.",
        ),
    },
)

def _orfs_repositories_impl(module_ctx):
    # ORFS itself, fetched and patched here rather than declared as a
    # bazel_dep. `patches` on archive_override/git_override is honoured
    # only from the root module, so a module dependency would put the
    # patching on whoever is root -- OpenROAD would have to carry ORFS
    # patches, and bazel-orfs could not patch ORFS at all when it is not
    # root. A module extension runs either way. The root module chooses
    # the version with orfs.source() and carries no patches.
    #
    # modules[0] is the root module, matching how orfs.default() below
    # already resolves.
    # No default pin. The ORFS commit decides which designs, PDKs and
    # flow scripts you build against, so inheriting one silently from
    # whatever bazel-orfs happened to be developed against is worse than
    # being told to choose. There is then exactly one place to look for
    # the version, and one place for //:bump to rewrite.
    sources = module_ctx.modules[0].tags.source
    if len(sources) != 1:
        fail(
            "expected exactly one orfs.source() tag in the root module, " +
            "got {}. Add to MODULE.bazel:\n".format(len(sources)) +
            '    orfs = use_extension("@bazel-orfs//:extension.bzl", ' +
            '"orfs_repositories")\n' +
            '    orfs.source(commit = "<sha>", integrity = "sha256-...")\n' +
            "and keep it current with `bazelisk run @bazel-orfs//:bump`.",
        )
    source = sources[0]
    for attr in ("commit", "integrity"):
        if not getattr(source, attr):
            fail("orfs.source() needs {} =".format(attr))

    http_archive(
        name = "orfs",
        **orfs_archive_args(source.commit, source.integrity, source.urls)
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
            openroad_qt = default.openroad_qt,
            opensta = default.opensta,
            pdk = default.pdk,
            yosys = default.yosys,
            yosys_abc = default.yosys_abc,
            yosys_share = default.yosys_share,
            yosys_plugins = default.yosys_plugins,
        )

        load_json_file(
            name = "orfs_variable_metadata",
            src = default.variables_yaml,
        )

orfs_repositories = module_extension(
    implementation = _orfs_repositories_impl,
    tag_classes = {
        "default": _default_tag,
        "source": _source_tag,
    },
)
