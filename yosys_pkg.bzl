"""Package the hermetic @yosys build as a relocatable PREFIX tarball.

The tarball follows the standard `make install` PREFIX layout:

  bin/yosys
  bin/yosys-abc
  share/yosys/...
  share/yosys/plugins/*.so   (optional, via the plugins attribute)

Yosys resolves its data directory as <bindir>/../share/yosys/ and abc as
<bindir>/yosys-abc (proc_self_dirname()), so the tarball can be extracted
into any prefix (e.g. /usr/local or a user directory) without patching.
"""

load("@rules_pkg//pkg:mappings.bzl", "pkg_attributes", "pkg_files", "strip_prefix")
load("@rules_pkg//pkg:tar.bzl", "pkg_tar")

# Label() resolves in bazel-orfs's repo mapping, so consumers of the
# macro don't need their own @yosys/@abc bazel_dep.
_YOSYS = Label("@yosys//:yosys")
_YOSYS_SHARE = Label("@yosys//:yosys_share")
_ABC = Label("@abc//:abc_bin")

def yosys_prefix_tar(name, plugins = [], visibility = None):
    """Create <name>.tar.gz with a relocatable PREFIX install of yosys.

    Args:
      name: name of the resulting pkg_tar target.
      plugins: optional list of yosys plugin shared-object labels
        (e.g. @yosys-slang//src/yosys_plugin:slang.so) placed in
        share/yosys/plugins/ where `plugin -i <name>` finds them.
      visibility: standard visibility.
    """
    pkg_files(
        name = name + "_bin",
        srcs = [
            _YOSYS,
            _ABC,
        ],
        attributes = pkg_attributes(mode = "0755"),
        prefix = "bin",
        renames = {
            # proc_self_dirname() + "yosys-abc" is how yosys finds abc.
            _ABC: "yosys-abc",
        },
    )
    pkg_files(
        name = name + "_share",
        # The share tree is declared as share/<dst> in @yosys's root
        # package; remap to the installed share/yosys/<dst> layout.
        srcs = [_YOSYS_SHARE],
        prefix = "share/yosys",
        strip_prefix = strip_prefix.from_pkg("share"),
    )
    srcs = [
        name + "_bin",
        name + "_share",
    ]
    if plugins:
        pkg_files(
            name = name + "_plugins",
            srcs = plugins,
            attributes = pkg_attributes(mode = "0755"),
            prefix = "share/yosys/plugins",
        )
        srcs.append(name + "_plugins")
    pkg_tar(
        name = name,
        srcs = srcs,
        extension = "tar.gz",
        tags = ["manual"],
        visibility = visibility,
    )
