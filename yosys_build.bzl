"""Repository rule that downloads Yosys + yosys-slang sources.

The actual build uses a genrule that calls make/cmake directly,
giving full control over compiler flags. This avoids toolchains_llvm's
broken __DATE__ redaction while keeping builds as proper Bazel actions
(sandboxed, cacheable).
"""

_YOSYS_REPO = "https://github.com/The-OpenROAD-Project/yosys"
_YOSYS_SLANG_REPO = "https://github.com/povik/yosys-slang"
_ABC_REPO = "https://github.com/YosysHQ/abc"
_SLANG_REPO = "https://github.com/MikePopoloski/slang"
_FMT_REPO = "https://github.com/fmtlib/fmt"
_CXXOPTS_REPO = "https://github.com/jarro2783/cxxopts"

_BUILD_FILE = """\
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

genrule(
    name = "yosys_make",
    srcs = [":yosys_srcs", ":abc_srcs", ":cxxopts_srcs"],
    outs = [
        "yosys",
        "yosys-abc",
        "yosys-config",
    ],
    cmd = " && ".join([
        # Save absolute output paths before cd'ing
        "OUT_YOSYS=$$(pwd)/$(location yosys)",
        "OUT_ABC=$$(pwd)/$(location yosys-abc)",
        "OUT_CONFIG=$$(pwd)/$(location yosys-config)",
        # Copy source to writable location; link in submodule sources
        "YOSYS=$$(find . -name Makefile -path '*/yosys-src/Makefile' -not -path '*/abc/*' | head -1 | xargs dirname)",
        "ABC=$$(find . -path '*/abc-src/Makefile' | head -1 | xargs dirname)",
        "CXXOPTS=$$(find . -path '*/cxxopts-src/include/cxxopts.hpp' | head -1 | xargs dirname | xargs dirname)",
        "cp -rL $$YOSYS $$TMPDIR/yosys-src",
        "rm -rf $$TMPDIR/yosys-src/abc $$TMPDIR/yosys-src/libs/cxxopts",
        "cp -rL $$ABC $$TMPDIR/yosys-src/abc",
        "cp -rL $$CXXOPTS $$TMPDIR/yosys-src/libs/cxxopts",
        "cd $$TMPDIR/yosys-src",
        "make install -j$$(nproc)" +
        " PREFIX=$$TMPDIR/install" +
        " ENABLE_TCL=1 ENABLE_ABC=1 ENABLE_PLUGINS=1" +
        " ENABLE_READLINE=0 ENABLE_EDITLINE=0" +
        " ENABLE_LIBYOSYS=0 ENABLE_PYOSYS=0",
        "cp $$TMPDIR/install/bin/yosys $$OUT_YOSYS",
        "cp $$TMPDIR/install/bin/yosys-abc $$OUT_ABC",
        "cp $$TMPDIR/install/bin/yosys-config $$OUT_CONFIG",
    ]),
    visibility = ["//visibility:public"],
)
"""

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

    # --- Generate BUILD.bazel ---
    repository_ctx.file("BUILD.bazel", _BUILD_FILE)

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
    },
    doc = "Downloads Yosys + yosys-slang sources; builds via genrule in generated BUILD.",
)
