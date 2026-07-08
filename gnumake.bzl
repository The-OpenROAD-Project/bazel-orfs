"""Repository rule that builds GNU Make hermetically from source.

The host `cc` would produce a host-dependent make binary whose content hash
cascades into Bazel remote cache misses for every orfs_run / orfs_flow action
(make is the Makefile-wrapper entrypoint for every stage).

Instead, we download Zig and bootstrap with `zig cc`. On Linux we statically
link against musl so the output is byte-identical across machines regardless
of host glibc or host compiler version; on macOS we target the native libc
(Apple doesn't allow fully-static libc linking).

The repository rule only *downloads* Zig and the GNU Make source; the actual
`./configure` + bootstrap runs in the `//:make` genrule, i.e. as a normal
build action. That way the compiled binary is an ordinary build artifact and
is stored in / served from the Bazel remote cache, instead of being rebuilt
during the fetch phase in every fresh output base (repository-rule execution
is not covered by the remote or disk action cache). The downloads stay in the
fetch phase, where they are covered by --repository_cache and the remote
downloader (Remote Asset API).
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

# Bootstrap script run by the //:make genrule (i.e. as a build action, not in
# the fetch phase). Compiles make with `zig cc` and copies the result to the
# declared output. Kept verbatim (no .format templating) so shell $-expansions
# survive; the host-specific target/flags arrive as positional arguments.
_BUILD_MAKE_SH = """#!/bin/sh
# Args: zig_bin make_src_dir out target extra_flags
set -eu

zig_bin=$1
src_dir=$2
out=$3
target=$4
extra_flags=$5

root=$(pwd)
build_dir="$root/_gnumake_build"
rm -rf "$build_dir"
mkdir -p "$build_dir"

# configure/build.sh write into the source tree, but Bazel inputs are
# read-only symlinks; work on a private, writable copy.
cp -RL "$src_dir"/. "$build_dir"/

# cc wrapper: pin the zig target + reproducibility flags so the binary is
# byte-identical across machines (a prerequisite for sharing remote-cache
# hits):
#   -ffile-prefix-map=...   strip the build path from __FILE__ / debug info
#   -Wl,--build-id=none     suppress the randomly-generated ELF build-id
#   -Wl,--strip-all         drop .debug_* and .symtab from the final binary
# (-static, where applicable, arrives in extra_flags.)
cat > "$build_dir/cc-wrapper.sh" <<EOF
#!/bin/sh
exec "$root/$zig_bin" cc -target $target $extra_flags \\
    -ffile-prefix-map=$build_dir= \\
    -Wl,--build-id=none \\
    -Wl,--strip-all \\
    "\\$@"
EOF
chmod +x "$build_dir/cc-wrapper.sh"

# Keep zig's own build cache inside the action's scratch dir.
export CC="$build_dir/cc-wrapper.sh"
export ZIG_LOCAL_CACHE_DIR="$build_dir/zig-cache"
export ZIG_GLOBAL_CACHE_DIR="$build_dir/zig-cache"
# --incompatible_strict_action_env gives actions a minimal PATH; configure
# needs the standard POSIX tools.
export PATH="/usr/bin:/bin:${PATH:-}"

cd "$build_dir"
./configure --without-guile --disable-nls
# Bootstrap build — compiles make using only the C compiler, no pre-existing
# make binary required.
sh build.sh
cp "$build_dir/make" "$root/$out"
"""

# BUILD.bazel for the generated repo. The genrule runs _BUILD_MAKE_SH as a
# build action; {target}/{extra_flags} are the host-specific zig settings.
_BUILD_BAZEL = """\
filegroup(
    name = "zig_toolchain",
    srcs = glob(["zig/**"]),
)

filegroup(
    name = "make_src",
    srcs = glob(["make-src/**"]),
)

genrule(
    name = "make",
    srcs = [
        "build_make.sh",
        "zig/zig",
        "make-src/configure",
        ":zig_toolchain",
        ":make_src",
    ],
    outs = ["make"],
    cmd = "$(execpath build_make.sh) $(execpath zig/zig) " +
          "$$(dirname $(execpath make-src/configure)) $@ " +
          "'{target}' '{extra_flags}'",
    # Single executable output, so `attr.label(executable = True)` consumers
    # (private/attrs.bzl `_make`) can use it via ctx.executable._make.
    executable = True,
    visibility = ["//visibility:public"],
)
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

    # GNU Make source — unpacked under make-src/.
    repository_ctx.download_and_extract(
        url = [
            "https://ftp.gnu.org/gnu/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://ftpmirror.gnu.org/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://mirrors.kernel.org/gnu/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
            "https://mirror.freedif.org/GNU/make/make-{v}.tar.gz".format(v = _MAKE_VERSION),
        ],
        sha256 = _MAKE_SHA256,
        stripPrefix = "make-{v}".format(v = _MAKE_VERSION),
        output = "make-src",
    )

    repository_ctx.file("build_make.sh", _BUILD_MAKE_SH, executable = True)
    repository_ctx.file("BUILD.bazel", _BUILD_BAZEL.format(
        target = host.target,
        extra_flags = host.extra_flags,
    ))

gnumake = repository_rule(
    implementation = _gnumake_impl,
    doc = "Downloads Zig {zv} and hermetically bootstraps GNU Make {mv} from source.".format(
        zv = _ZIG_VERSION,
        mv = _MAKE_VERSION,
    ),
)
