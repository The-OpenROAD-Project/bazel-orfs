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

Substituting a host make
------------------------

On hosts where the registered LLVM toolchain doesn't apply (macOS,
non-x86_64 Linux), or when a developer simply wants to use their own
make, the standard Bazel escape hatch is `--override_repository`. It
replaces the entire `@gnumake` repo with a local directory — the
`gnumake()` repo rule's tarball download is skipped, no compile is
attempted, no bazel-orfs-specific helper is involved.

One-time setup (any path of the user's choosing):

    mkdir -p ~/.config/bazel/host_make
    touch ~/.config/bazel/host_make/REPO.bazel
    cat > ~/.config/bazel/host_make/make.sh <<'EOF'
    #!/bin/sh
    exec /opt/homebrew/bin/gmake "$@"
    EOF
    chmod +x ~/.config/bazel/host_make/make.sh
    cat > ~/.config/bazel/host_make/BUILD.bazel <<'EOF'
    sh_binary(
        name = "make",
        srcs = ["make.sh"],
        visibility = ["//visibility:public"],
    )
    EOF

Then in `user.bazelrc` (gitignored, per-machine):

    build --override_repository=+orfs_repositories+gnumake=/Users/foo/.config/bazel/host_make

The override key is the *canonical* repo name `+orfs_repositories+gnumake`
(bzlmod adds the `+orfs_repositories+` prefix because @gnumake is created
by the orfs_repositories module extension). The apparent name `gnumake`
will not match — Bazel silently keeps using the bazel-built make if you
write that.

The `REPO.bazel` file is just a Bazel marker that says "this directory
is a repo root"; it can stay empty.

ORFS Makefiles use GNU make 4.x extensions, so point at gmake — Apple's
/usr/bin/make is BSD make 3.81 and won't work.

`--override_module` is for Bazel modules; @gnumake is a repo created by
a module extension, so `--override_repository` is the right knob.
"""

_MAKE_VERSION = "4.4.1"

def _gnumake_impl(repository_ctx):
    repository_ctx.download_and_extract(
        url = [
            "https://ftp.gnu.org/gnu/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://ftpmirror.gnu.org/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://mirrors.kernel.org/gnu/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://mirror.freedif.org/GNU/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
        ],
        sha256 = "dd16fb1d67bfab79a72f5e8390735c49e3e8e70b4945a15ab1f81ddb78658fb3",
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
