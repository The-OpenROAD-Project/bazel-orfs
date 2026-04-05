"""Repository rule that builds GNU Make from source."""

_VERSION = "4.4.1"
_SHA256 = "dd16fb1d67bfab79a72f5e8390735c49e3e8e70b4945a15ab1f81ddb78658fb3"

def _gnumake_impl(repository_ctx):
    repository_ctx.download_and_extract(
        url = [
            "https://ftp.gnu.org/gnu/make/make-{version}.tar.gz".format(version = _VERSION),
            "https://ftpmirror.gnu.org/make/make-{version}.tar.gz".format(version = _VERSION),
            "https://mirrors.kernel.org/gnu/make/make-{version}.tar.gz".format(version = _VERSION),
            "https://mirror.freedif.org/GNU/make/make-{version}.tar.gz".format(version = _VERSION),
        ],
        sha256 = _SHA256,
        stripPrefix = "make-{version}".format(version = _VERSION),
    )

    # Configure (generates config.h and build.sh)
    result = repository_ctx.execute(
        ["./configure", "--without-guile", "--disable-nls"],
        timeout = 120,
    )
    if result.return_code != 0:
        fail("GNU Make configure failed:\n" + result.stderr)

    # Bootstrap build — compiles make using only the C compiler, no
    # pre-existing make binary required.
    result = repository_ctx.execute(
        ["sh", "build.sh"],
        timeout = 120,
    )
    if result.return_code != 0:
        fail("GNU Make bootstrap build failed:\n" + result.stderr)

    repository_ctx.file("BUILD.bazel", """\
exports_files(
    ["make"],
    visibility = ["//visibility:public"],
)
""")

gnumake = repository_rule(
    implementation = _gnumake_impl,
    doc = "Downloads and bootstraps GNU Make {version} from source.".format(version = _VERSION),
)
