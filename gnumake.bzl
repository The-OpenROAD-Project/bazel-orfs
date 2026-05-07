"""Repository rule that fetches GNU Make source and overlays a Bazel BUILD file.

The host `cc` would produce a host-dependent make binary whose content hash
cascades into Bazel remote cache misses for every orfs_run / orfs_flow
action (make is the Makefile-wrapper entrypoint for every stage).

The BUILD file overlay (//tools/gnumake:BUILD.gnumake) compiles gmake as a
plain `cc_binary` against the project's registered hermetic clang
(`@llvm_toolchain` from toolchains_llvm) — the same toolchain used to build
yosys and openroad — with `-Wl,--build-id=none -Wl,-s` to strip the random
build-id and symbols. Output is deterministic on a fixed host. Strict
cross-distro byte identity (the previous zig+musl-static guarantee) would
require vendoring a sysroot and is out of scope here; it would benefit
yosys/openroad equally and should be a project-wide change.

Linux x86_64 only — that's the only host the registered LLVM tarball
supports today.
"""

_MAKE_VERSION = "4.4.1"
_MAKE_SHA256 = "dd16fb1d67bfab79a72f5e8390735c49e3e8e70b4945a15ab1f81ddb78658fb3"

def _gnumake_impl(repository_ctx):
    repository_ctx.download_and_extract(
        url = [
            "https://ftp.gnu.org/gnu/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://ftpmirror.gnu.org/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://mirrors.kernel.org/gnu/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://mirror.freedif.org/GNU/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
        ],
        sha256 = _MAKE_SHA256,
        stripPrefix = "make-{v}".format(v = _MAKE_VERSION),
    )

    # Overlay the vendored config.h (autoconf output for Linux glibc, captured
    # once and committed) and the cc_binary BUILD file. No ./configure run,
    # no host C compiler, no Zig.
    repository_ctx.symlink(
        Label("//tools/gnumake:config.h"),
        "src/config.h",
    )
    repository_ctx.symlink(
        Label("//tools/gnumake:BUILD.gnumake"),
        "BUILD.bazel",
    )

gnumake = repository_rule(
    implementation = _gnumake_impl,
    doc = "Downloads GNU Make {v} source and overlays a Bazel cc_binary BUILD file.".format(
        v = _MAKE_VERSION,
    ),
)
