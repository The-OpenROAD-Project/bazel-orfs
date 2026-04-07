"""Repository rule that downloads and builds Yosys + yosys-slang from source.

Yosys is built from source using make/cmake in a genrule, which requires a
C++ toolchain.  Exposing this as a transitive bazel_dep would impose C++
compiler requirements on every consumer of bazel-orfs — even those that
never build a synthesis target.  Instead, the orfs_repositories extension
creates the @yosys repo internally, hiding the C++ build from consumers'
dependency graphs.
"""

_YOSYS_REPO = "https://github.com/The-OpenROAD-Project/yosys"
_YOSYS_SLANG_REPO = "https://github.com/povik/yosys-slang"
_ABC_REPO = "https://github.com/YosysHQ/abc"
_SLANG_REPO = "https://github.com/MikePopoloski/slang"
_FMT_REPO = "https://github.com/fmtlib/fmt"
_CXXOPTS_REPO = "https://github.com/jarro2783/cxxopts"

# Default commit SHAs — keep in sync with yosys/extension.bzl
YOSYS_COMMIT = "d3e297fcd479247322f83d14f42b3556db7acdfb"
ABC_COMMIT = "8e401543d3ecf65e3a3631c7a271793a4d356cb0"
CXXOPTS_COMMIT = "4bf61f08697b110d9e3991864650a405b3dd515d"
YOSYS_SLANG_COMMIT = "64b44616a3798f07453b14ea03e4ac8a16b77313"
SLANG_COMMIT = "d7888c90a048e47384e530fef9863e65952c9e3c"
FMT_COMMIT = "553ec11ec06fbe0beebfbb45f9dc3c9eabd83d28"

_RULES_BZL = '''\
"""Rules for the yosys repo."""

def _extract_share_impl(ctx):
    """Extract yosys share directory from tar into a tree artifact."""
    share = ctx.actions.declare_directory("share")
    ctx.actions.run_shell(
        inputs = [ctx.file.tar],
        outputs = [share],
        command = "tar -xf {tar} -C {out} --strip-components=1".format(
            tar = ctx.file.tar.path,
            out = share.path,
        ),
    )
    return [DefaultInfo(files = depset([share]))]

extract_share = rule(
    implementation = _extract_share_impl,
    attrs = {
        "tar": attr.label(
            mandatory = True,
            allow_single_file = [".tar"],
        ),
    },
)

def _cc_files_impl(ctx):
    """Extract raw header and library files from a cc_library for genrule use."""
    cc_info = ctx.attr.dep[CcInfo]
    headers = cc_info.compilation_context.headers.to_list()
    default_files = ctx.attr.dep[DefaultInfo].files.to_list()
    return [DefaultInfo(files = depset(headers + default_files))]

cc_files = rule(
    implementation = _cc_files_impl,
    attrs = {
        "dep": attr.label(mandatory = True, providers = [CcInfo]),
    },
)
'''

_BUILD_BAZEL = '''\
load("//:rules.bzl", "cc_files", "extract_share")

filegroup(
    name = "yosys_srcs",
    srcs = glob(
        ["yosys-src/**"],
        exclude = ["yosys-src/.git/**"],
    ),
)

filegroup(
    name = "abc_srcs",
    srcs = glob(["abc-src/**"], allow_empty = True),
)

filegroup(
    name = "cxxopts_srcs",
    srcs = glob(["cxxopts-src/**"], allow_empty = True),
)

filegroup(
    name = "slang_srcs",
    srcs = glob(
        ["yosys-slang-src/**"],
        exclude = ["yosys-slang-src/.git/**"],
    ),
)

filegroup(
    name = "tcl_srcs",
    srcs = glob(["tcl-src/**"]),
)

filegroup(
    name = "flex_srcs",
    srcs = glob(["flex-src/**"]),
)

cc_files(
    name = "libffi_files",
    dep = "@libffi",
)

extract_share(
    name = "yosys_share",
    tar = ":yosys-share.tar",
    visibility = ["//visibility:public"],
)

genrule(
    name = "yosys_make",
    srcs = [
        ":yosys_srcs",
        ":abc_srcs",
        ":cxxopts_srcs",
        ":slang_srcs",
        ":tcl_srcs",
        ":flex_srcs",
        ":libffi_files",
    ],
    outs = [
        "yosys",
        "yosys-abc",
        "yosys-config",
        "yosys-share.tar",
    ],
    cmd = " && ".join([
        # Save absolute output paths before cd'ing
        "OUT_YOSYS=$$(pwd)/$(location yosys)",
        "OUT_ABC=$$(pwd)/$(location yosys-abc)",
        "OUT_CONFIG=$$(pwd)/$(location yosys-config)",
        "OUT_SHARE=$$(pwd)/$(location yosys-share.tar)",
        # Build TCL from source (static library + headers)
        "TCL_SRC=$$(find . -path '*/tcl-src/unix/configure' | head -1 | xargs dirname | xargs dirname)",
        "cp -rL $$TCL_SRC $$TMPDIR/tcl-src",
        "cd $$TMPDIR/tcl-src/unix",
        "./configure --prefix=$$TMPDIR/tcl-install --disable-shared --enable-threads 2>&1 | tail -5",
        "make -j$$(nproc) 2>&1 | tail -5",
        "make install 2>&1 | tail -5",
        "cd $$OLDPWD",
        "TCL_INCLUDE=$$TMPDIR/tcl-install/include",
        "TCL_LIBDIR=$$TMPDIR/tcl-install/lib",
        # Locate FlexLexer.h from flex source (hermetic, no system libfl-dev needed)
        "FLEX_INCLUDE=$$(pwd)/$$(find . -path '*/flex-src/src/FlexLexer.h' | head -1 | xargs dirname)",
        # Locate prebuilt libffi headers and library (from BCR @libffi)
        "FFI_INCLUDE=$$(pwd)/$$(dirname $$(find . -name 'ffi.h' -path '*/libffi*' | head -1))",
        "FFI_LIBDIR=$$(pwd)/$$(dirname $$(find . -name 'liblibffi.a' | head -1))",
        "ln -sf $$FFI_LIBDIR/liblibffi.a $$FFI_LIBDIR/libffi.a",
        # Copy yosys source to writable location; link in submodule sources
        "YOSYS=$$(find . -name Makefile -path '*/yosys-src/Makefile' -not -path '*/abc/*' | head -1 | xargs dirname)",
        "ABC=$$(find . -path '*/abc-src/Makefile' | head -1 | xargs dirname)",
        "CXXOPTS=$$(find . -path '*/cxxopts-src/include/cxxopts.hpp' | head -1 | xargs dirname | xargs dirname)",
        "cp -rL $$YOSYS $$TMPDIR/yosys-src",
        "rm -rf $$TMPDIR/yosys-src/abc $$TMPDIR/yosys-src/libs/cxxopts",
        "cp -rL $$ABC $$TMPDIR/yosys-src/abc",
        "cp -rL $$CXXOPTS $$TMPDIR/yosys-src/libs/cxxopts",
        "cd $$TMPDIR/yosys-src",
        "export CXXFLAGS=\\"-I$$FLEX_INCLUDE -I$$FFI_INCLUDE\\"",
        "export LIBRARY_PATH=$$FFI_LIBDIR$${LIBRARY_PATH:+:$$LIBRARY_PATH}",
        "make install -j$$(nproc)" +
        " PREFIX=$$TMPDIR/install" +
        " ENABLE_TCL=1 ENABLE_ABC=1 ENABLE_PLUGINS=1" +
        " ENABLE_READLINE=0 ENABLE_EDITLINE=0" +
        " ENABLE_LIBYOSYS=0 ENABLE_PYOSYS=0" +
        " TCL_INCLUDE=$$TCL_INCLUDE" +
        " TCL_LIBS=\\"-L$$TCL_LIBDIR -ltcl8.6 -lpthread -ldl -lz -lm\\"",
        "cp $$TMPDIR/install/bin/yosys $$OUT_YOSYS",
        "cp $$TMPDIR/install/bin/yosys-abc $$OUT_ABC",
        "cp $$TMPDIR/install/bin/yosys-config $$OUT_CONFIG",
        # Build yosys-slang plugin
        "cd $$OLDPWD",
        "SLANG=$$(find . -name CMakeLists.txt -path '*/yosys-slang-src/CMakeLists.txt' | head -1 | xargs dirname)",
        "cp -rL $$SLANG $$TMPDIR/yosys-slang-src",
        "cd $$TMPDIR/yosys-slang-src",
        "cmake -S . -B build" +
        " -DCMAKE_CXX_STANDARD=20" +
        " -DYOSYS_CONFIG=$$TMPDIR/install/bin/yosys-config" +
        " -DCMAKE_BUILD_TYPE=Release" +
        " 2>&1 | tail -20",
        "cmake --build build -j$$(nproc) 2>&1 | tail -20",
        # Package share directory (techmap, plugins, etc.) as a tar
        "mkdir -p $$TMPDIR/install/share/yosys/plugins",
        "cp $$TMPDIR/yosys-slang-src/build/slang.so $$TMPDIR/install/share/yosys/plugins/",
        "tar -cf $$OUT_SHARE -C $$TMPDIR/install/share yosys",
    ]),
    visibility = ["//visibility:public"],
)
'''

def _yosys_sources_impl(repository_ctx):
    # --- Download yosys source ---
    repository_ctx.download_and_extract(
        url = ["{repo}/archive/{commit}.tar.gz".format(
            repo = _YOSYS_REPO,
            commit = repository_ctx.attr.yosys_commit,
        )],
        sha256 = repository_ctx.attr.yosys_sha256,
        stripPrefix = "yosys-{commit}".format(commit = repository_ctx.attr.yosys_commit),
        output = "yosys-src",
    )

    # --- Download ABC (yosys submodule) ---
    repository_ctx.download_and_extract(
        url = ["{repo}/archive/{commit}.tar.gz".format(
            repo = _ABC_REPO,
            commit = repository_ctx.attr.abc_commit,
        )],
        sha256 = repository_ctx.attr.abc_sha256,
        stripPrefix = "abc-{commit}".format(commit = repository_ctx.attr.abc_commit),
        output = "abc-src",
    )

    # --- Download cxxopts (yosys submodule) ---
    repository_ctx.download_and_extract(
        url = ["{repo}/archive/{commit}.tar.gz".format(
            repo = _CXXOPTS_REPO,
            commit = repository_ctx.attr.cxxopts_commit,
        )],
        sha256 = repository_ctx.attr.cxxopts_sha256,
        stripPrefix = "cxxopts-{commit}".format(commit = repository_ctx.attr.cxxopts_commit),
        output = "cxxopts-src",
    )

    # Remove BUILD files from extracted submodules to prevent them from
    # becoming separate Bazel packages (which blocks glob from crossing
    # into their directories).
    for build_file in ["cxxopts-src/BUILD.bazel", "abc-src/BUILD.bazel"]:
        repository_ctx.delete(build_file)

    # --- Download yosys-slang ---
    repository_ctx.download_and_extract(
        url = ["{repo}/archive/{commit}.tar.gz".format(
            repo = _YOSYS_SLANG_REPO,
            commit = repository_ctx.attr.yosys_slang_commit,
        )],
        sha256 = repository_ctx.attr.yosys_slang_sha256,
        stripPrefix = "yosys-slang-{commit}".format(
            commit = repository_ctx.attr.yosys_slang_commit,
        ),
        output = "yosys-slang-src",
    )

    # --- Download slang (yosys-slang submodule) ---
    repository_ctx.download_and_extract(
        url = ["{repo}/archive/{commit}.tar.gz".format(
            repo = _SLANG_REPO,
            commit = repository_ctx.attr.slang_commit,
        )],
        sha256 = repository_ctx.attr.slang_sha256,
        stripPrefix = "slang-{commit}".format(commit = repository_ctx.attr.slang_commit),
        output = "yosys-slang-src/third_party/slang",
    )

    # --- Download fmt (yosys-slang submodule) ---
    repository_ctx.download_and_extract(
        url = ["{repo}/archive/{commit}.tar.gz".format(
            repo = _FMT_REPO,
            commit = repository_ctx.attr.fmt_commit,
        )],
        sha256 = repository_ctx.attr.fmt_sha256,
        stripPrefix = "fmt-{commit}".format(commit = repository_ctx.attr.fmt_commit),
        output = "yosys-slang-src/third_party/fmt",
    )

    # --- Download TCL source (for headers + static library build) ---
    tcl_version = repository_ctx.attr.tcl_version
    repository_ctx.download_and_extract(
        url = ["https://github.com/tcltk/tcl/archive/refs/tags/core-{version}.tar.gz".format(
            version = tcl_version.replace(".", "-"),
        )],
        sha256 = repository_ctx.attr.tcl_sha256,
        stripPrefix = "tcl-core-{version}".format(
            version = tcl_version.replace(".", "-"),
        ),
        output = "tcl-src",
    )

    # --- Download flex source (for FlexLexer.h header) ---
    repository_ctx.download_and_extract(
        url = ["https://github.com/westes/flex/archive/refs/tags/v{version}.tar.gz".format(
            version = repository_ctx.attr.flex_version,
        )],
        sha256 = repository_ctx.attr.flex_sha256,
        stripPrefix = "flex-{version}".format(
            version = repository_ctx.attr.flex_version,
        ),
        output = "flex-src",
    )

    # --- Write BUILD and rules files directly into the repo ---
    repository_ctx.file("rules.bzl", _RULES_BZL)
    repository_ctx.file("BUILD.bazel", _BUILD_BAZEL)

yosys_sources = repository_rule(
    implementation = _yosys_sources_impl,
    attrs = {
        "yosys_commit": attr.string(mandatory = True, doc = "Yosys git commit SHA"),
        "yosys_sha256": attr.string(default = "", doc = "SHA256 of yosys source tarball"),
        "abc_commit": attr.string(mandatory = True, doc = "ABC git commit SHA (yosys submodule)"),
        "abc_sha256": attr.string(default = "", doc = "SHA256 of ABC source tarball"),
        "cxxopts_commit": attr.string(mandatory = True, doc = "cxxopts git commit SHA (yosys submodule)"),
        "cxxopts_sha256": attr.string(default = "", doc = "SHA256 of cxxopts source tarball"),
        "yosys_slang_commit": attr.string(mandatory = True, doc = "yosys-slang git commit SHA"),
        "yosys_slang_sha256": attr.string(default = "", doc = "SHA256 of yosys-slang tarball"),
        "slang_commit": attr.string(mandatory = True, doc = "slang git commit SHA (yosys-slang submodule)"),
        "slang_sha256": attr.string(default = "", doc = "SHA256 of slang source tarball"),
        "fmt_commit": attr.string(mandatory = True, doc = "fmt git commit SHA (yosys-slang submodule)"),
        "fmt_sha256": attr.string(default = "", doc = "SHA256 of fmt source tarball"),
        "tcl_version": attr.string(default = "8.6.16", doc = "TCL version to download"),
        "tcl_sha256": attr.string(default = "", doc = "SHA256 of TCL source tarball"),
        "flex_version": attr.string(default = "2.6.4", doc = "Flex version for FlexLexer.h header"),
        "flex_sha256": attr.string(default = "", doc = "SHA256 of flex source tarball"),
    },
    doc = "Downloads Yosys + yosys-slang sources; builds via genrule in BUILD.bazel.",
)
