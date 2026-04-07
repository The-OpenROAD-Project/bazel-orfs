"""Module extension that downloads Yosys + yosys-slang sources.

The actual build uses a genrule in BUILD.bazel that calls make directly,
giving full control over compiler flags while keeping builds as proper
Bazel actions (sandboxed, cacheable).
"""

_YOSYS_REPO = "https://github.com/The-OpenROAD-Project/yosys"
_YOSYS_SLANG_REPO = "https://github.com/povik/yosys-slang"
_ABC_REPO = "https://github.com/YosysHQ/abc"
_SLANG_REPO = "https://github.com/MikePopoloski/slang"
_FMT_REPO = "https://github.com/fmtlib/fmt"
_CXXOPTS_REPO = "https://github.com/jarro2783/cxxopts"

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

    # --- Symlink the BUILD.bazel from the module ---
    repository_ctx.symlink(repository_ctx.attr._build_file, "BUILD.bazel")

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
        "flex_version": attr.string(default = "2.6.4", doc = "Flex version for FlexLexer.h header"),
        "flex_sha256": attr.string(default = "", doc = "SHA256 of flex source tarball"),
        "_build_file": attr.label(default = Label("//:repo.BUILD.bazel"), doc = "BUILD file for the generated repo"),
    },
    doc = "Downloads Yosys + yosys-slang sources; builds via genrule in BUILD.bazel.",
)

_default_tag = tag_class(
    attrs = {
        "yosys_commit": attr.string(default = "d3e297fcd479247322f83d14f42b3556db7acdfb"),
        "abc_commit": attr.string(default = "8e401543d3ecf65e3a3631c7a271793a4d356cb0"),
        "cxxopts_commit": attr.string(default = "4bf61f08697b110d9e3991864650a405b3dd515d"),
        "yosys_slang_commit": attr.string(default = "64b44616a3798f07453b14ea03e4ac8a16b77313"),
        "slang_commit": attr.string(default = "d7888c90a048e47384e530fef9863e65952c9e3c"),
        "fmt_commit": attr.string(default = "553ec11ec06fbe0beebfbb45f9dc3c9eabd83d28"),
    },
)

def _yosys_ext_impl(module_ctx):
    for default in module_ctx.modules[0].tags.default:
        yosys_sources(
            name = "yosys",
            yosys_commit = default.yosys_commit,
            abc_commit = default.abc_commit,
            cxxopts_commit = default.cxxopts_commit,
            yosys_slang_commit = default.yosys_slang_commit,
            slang_commit = default.slang_commit,
            fmt_commit = default.fmt_commit,
        )

yosys_ext = module_extension(
    implementation = _yosys_ext_impl,
    tag_classes = {
        "default": _default_tag,
    },
)
