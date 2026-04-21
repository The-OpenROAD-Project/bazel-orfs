# libxml2 stub — boarding up a broken window

The pre-built LLVM toolchain (`ld.lld`) dynamically links `libxml2.so.2`,
but only uses it for **Windows manifest merging** (`lld/COFF/DriverUtils.cpp`).
On Linux it is never called, yet every link action prints:

```
ld.lld: /lib/x86_64-linux-gnu/libxml2.so.2: no version information available
```

This directory holds a stub `libxml2.so.2` with the correct versioned symbols
(all of which `abort()` if called). It is compiled into the LLVM archive's
`lib/` directory via `patch_cmds` on the `http_archive` that backs
`toolchains_llvm`'s `llvm.toolchain_root`, where `ld.lld`'s
`RUNPATH=$ORIGIN/../lib` picks it up before the system library.

## When to delete this

Remove this directory and the corresponding `http_archive` + `toolchain_root`
blocks in `//MODULE.bazel` and `//gallery/MODULE.bazel` as soon as **any** of
these land upstream:

- LLVM ships `ld.lld` statically linked on Linux (no libxml2 dep), or
- The BCR `toolchains_llvm` bundles a libxml2 stub itself, or
- The official LLVM release tarball carries one, or
- We switch to a toolchain that doesn't have this issue.

Check by bumping the toolchain, deleting this directory + the MODULE.bazel
blocks, and running `bazelisk build @openroad//:openroad`. If there is no
`libxml2.so.2: no version information available` warning and the link
succeeds on a host without `libxml2-dev`, you can delete the whole hack.

## Files

| File | Purpose |
|---|---|
| `libxml2_stub.c` | Canonical C source (documentation / maintenance copy) |
| `libxml2_stub.ver` | GNU linker version script with `LIBXML2_2.4.30` / `2.6.0` tags |
| `BUILD.llvm_repo` | Verbatim copy of `@toolchains_llvm//toolchain:BUILD.llvm_repo`, used as the `build_file` for our pre-patched `http_archive` |
| `BUILD.bazel` | `exports_files` so the gallery root module can reference `BUILD.llvm_repo` via `@bazel-orfs//tools/xml-hack:...` |

The actual compilation is inlined as a single-line heredoc in each
`MODULE.bazel`'s `patch_cmds` because `patch_cmds` cannot reference
workspace files. The canonical `.c` and `.ver` files here are the source
of truth — keep them and the MODULE.bazel heredocs in sync.

## Hermeticity

The stub is compiled with `./bin/clang -nostdlib -nostdinc -fuse-ld=lld`
using the Clang and LLD from the just-extracted LLVM archive. This ensures
the `.so` is byte-identical regardless of the host compiler, which is
critical for Bazel remote-cache hits — the stub lands in `linker_builtins`
and becomes an input to every link action.

## Where this should really be fixed

This is a workaround, not a solution. The real seams, most-to-least upstream:

1. **`llvm/llvm-project`** — `lld/COFF/DriverUtils.cpp` conditionally links
   libxml2; guarding the dep by target OS (or static-linking the tiny
   manifest-merger path on Linux releases) would delete this cost for
   every downstream consumer.
2. **`llvm/llvm-project` release build** — ship `ld.lld` statically linked
   on Linux release tarballs.
3. **`bazel-contrib/toolchains_llvm`** (BCR) — either bundle a libxml2
   stub in the distribution, or add a `patches=` / `patch_cmds=` attr on
   the `llvm.toolchain` extension so workarounds don't have to route
   through `toolchain_root`.

Please upstream the real fix if you're in a position to do so, then send
the revert of this directory.
