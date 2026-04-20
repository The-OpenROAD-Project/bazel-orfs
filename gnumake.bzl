"""Repository rule that builds GNU Make hermetically from source.

The host `cc` would produce a host-dependent make binary whose content hash
cascades into Bazel remote cache misses for every orfs_run / orfs_flow action
(make is the Makefile-wrapper entrypoint for every stage).

Instead, we download Zig and bootstrap with `zig cc`. On Linux we statically
link against musl so the output is byte-identical across machines regardless
of host glibc or host compiler version; on macOS we target the native libc
(Apple doesn't allow fully-static libc linking).
"""

_MAKE_VERSION = "4.4.1"
_MAKE_SHA256 = "dd16fb1d67bfab79a72f5e8390735c49e3e8e70b4945a15ab1f81ddb78658fb3"

_ZIG_VERSION = "0.12.0"

# Per-host prebuilt zig tarballs from ziglang.org. Zig bundles clang, lld,
# and libcs for every target, so nothing else is needed to compile make.
_ZIG_HOSTS = {
    "linux-x86_64": struct(
        sha256 = "c7ae866b8a76a568e2d5cfd31fe89cdb629bdd161fdd5018b29a4a0a17045cad",
        subdir = "zig-linux-x86_64-{}",
        target = "x86_64-linux-musl",
        extra_flags = "-static",
    ),
    "linux-aarch64": struct(
        sha256 = "754f1029484079b7e0ca3b913a0a2f2a6afd5a28990cb224fe8845e72f09de63",
        subdir = "zig-linux-aarch64-{}",
        target = "aarch64-linux-musl",
        extra_flags = "-static",
    ),
    "mac-x86_64": struct(
        sha256 = "4d411bf413e7667821324da248e8589278180dbc197f4f282b7dbb599a689311",
        subdir = "zig-macos-x86_64-{}",
        target = "x86_64-macos",
        extra_flags = "",
    ),
    "mac-aarch64": struct(
        sha256 = "294e224c14fd0822cfb15a35cf39aa14bd9967867999bf8bdfe3db7ddec2a27f",
        subdir = "zig-macos-aarch64-{}",
        target = "aarch64-macos",
        extra_flags = "",
    ),
}

def _host_key(repository_ctx):
    name = repository_ctx.os.name.lower()
    arch = repository_ctx.os.arch.lower()
    if arch in ("amd64", "x86_64"):
        arch = "x86_64"
    elif arch in ("arm64", "aarch64"):
        arch = "aarch64"
    if "linux" in name:
        os = "linux"
    elif "mac" in name or "darwin" in name:
        os = "mac"
    else:
        fail("Unsupported host OS for hermetic gnumake: {}".format(name))
    key = "{}-{}".format(os, arch)
    if key not in _ZIG_HOSTS:
        fail("Unsupported host for hermetic gnumake: {} (supported: {})".format(
            key,
            ", ".join(_ZIG_HOSTS.keys()),
        ))
    return key

_CC_WRAPPER = """#!/bin/sh
# configure invokes this as $CC; delegate to `zig cc` with a pinned target
# and reproducibility flags so the output is byte-identical across hosts:
#   -ffile-prefix-map=...    strip absolute paths from __FILE__ and debug info
#   -Wl,--build-id=none      suppress the randomly-generated ELF build-id
#   -Wl,--strip-all          drop .debug_* and .symtab from the final binary
# (-static, where applicable, is folded into extra_flags below.)
exec {zig} cc -target {target} {extra_flags} \
    -ffile-prefix-map={repo}= \
    -Wl,--build-id=none \
    -Wl,--strip-all \
    "$@"
"""

def _gnumake_impl(repository_ctx):
    host_key = _host_key(repository_ctx)
    host = _ZIG_HOSTS[host_key]

    # Zig tarball — unpacked into the repo dir under zig/.
    repository_ctx.download_and_extract(
        url = [
            "https://ziglang.org/download/{v}/{name}.tar.xz".format(
                v = _ZIG_VERSION,
                name = host.subdir.format(_ZIG_VERSION),
            ),
        ],
        sha256 = host.sha256,
        stripPrefix = host.subdir.format(_ZIG_VERSION),
        output = "zig",
    )
    zig = repository_ctx.path("zig/zig")

    # GNU Make source.
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

    # cc wrapper that pins target + reproducibility flags.
    repository_ctx.file(
        "cc-wrapper.sh",
        _CC_WRAPPER.format(
            zig = zig,
            target = host.target,
            extra_flags = host.extra_flags,
            repo = str(repository_ctx.path(".")),
        ),
        executable = True,
    )
    cc = str(repository_ctx.path("cc-wrapper.sh"))

    # Keep zig's own build cache inside the repo so it's hermetic and cleaned
    # up with `bazel clean --expunge`.
    env = {
        "CC": cc,
        "ZIG_LOCAL_CACHE_DIR": str(repository_ctx.path("zig-cache")),
        "ZIG_GLOBAL_CACHE_DIR": str(repository_ctx.path("zig-cache")),
    }

    result = repository_ctx.execute(
        ["./configure", "--without-guile", "--disable-nls"],
        timeout = 300,
        environment = env,
    )
    if result.return_code != 0:
        fail("GNU Make configure failed:\nstdout:\n{}\nstderr:\n{}".format(result.stdout, result.stderr))

    # Bootstrap build — compiles make using only the C compiler, no
    # pre-existing make binary required.
    result = repository_ctx.execute(
        ["sh", "build.sh"],
        timeout = 600,
        environment = env,
    )
    if result.return_code != 0:
        fail("GNU Make bootstrap build failed:\nstdout:\n{}\nstderr:\n{}".format(result.stdout, result.stderr))

    repository_ctx.file("BUILD.bazel", """\
exports_files(
    ["make"],
    visibility = ["//visibility:public"],
)
""")

gnumake = repository_rule(
    implementation = _gnumake_impl,
    doc = "Downloads Zig {zv} and hermetically bootstraps GNU Make {mv} from source.".format(
        zv = _ZIG_VERSION,
        mv = _MAKE_VERSION,
    ),
)
