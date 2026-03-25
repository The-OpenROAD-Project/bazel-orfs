# Wrapper Scripts for Relocatable Binaries

Binaries extracted from the ORFS image (OpenROAD, yosys, klayout, make, sta)
are wrapped with shell scripts so they can be invoked from any working directory.
This replaces the previous `patchelf --set-interpreter` approach.

## Why not patchelf?

The Linux kernel does **not** expand `$ORIGIN` in `PT_INTERP` (the ELF
interpreter field). `patchelf --set-interpreter` can only set a path that is
either absolute or relative to `getcwd()` — never relative to the binary itself.
This meant binaries only worked when invoked from Bazel's execution root.

## How it works

`patcher.py` runs after extracting the OCI image:

1. **RPATH reading**: `readelf` reads NEEDED/RPATH/RUNPATH from ELF binaries.
   Absolute library paths are converted to `$ORIGIN`-relative paths for use
   in the wrapper's `--library-path`.

2. **Wrapper generation**: For each ELF executable with `PT_INTERP`:
   - Move the binary from `bin/foo` to `libexec/bin/foo`
   - Create a bash wrapper at the original path:
     ```bash
     #!/usr/bin/env bash
     self="$(readlink -f "${BASH_SOURCE[0]}")"
     top_dir="$(cd "$(dirname "$self")/../../.." && pwd)"
     export TCL_LIBRARY="${TCL_LIBRARY:-$top_dir/usr/share/tcltk/tcl8.6}"
     exec "$top_dir/_lib/ld-linux-x86-64.so.2" \
       --inhibit-cache --inhibit-rpath "" \
       --library-path "$top_dir/..." \
       --argv0 "$self" \
       "$top_dir/libexec/bin/foo" "$@"
     ```
   - Skip `.so` files (shared libraries may have `PT_INTERP` if PIE, but
     must not be wrapped)

3. **Interpreter setup**: Copy `ld-linux-x86-64.so.2` to `_lib/` (a fresh
   directory) instead of using the existing `lib64/` or `lib/` paths.

4. **Share symlinks**: Create `{top}/share/yosys` -> actual yosys share dir.

5. **Sibling symlinks**: Create `_lib/yosys-abc` -> yosys-abc wrapper, etc.

## Gotchas

### `readlink -f` is essential for Bazel sandbox compatibility

The wrapper uses `readlink -f "${BASH_SOURCE[0]}"` to resolve through Bazel's
sandbox symlinks to the real file in the external repo cache. Without this,
`$top_dir` would point inside the sandbox where most shared libraries are absent.

### `/proc/self/exe` points to ld-linux, not the wrapped binary

When you `exec ld-linux ... /path/to/binary`, the kernel sets `/proc/self/exe`
to the ld-linux interpreter, not the binary. This affects:

- **yosys share directory**: yosys calls `readlink("/proc/self/exe")` and looks
  for `{exe_dir}/../share/yosys/`. Since `/proc/self/exe` is `_lib/ld-linux`,
  it checks `_lib/../share/yosys/` = `share/yosys/`. We create this symlink.

- **yosys-abc discovery**: yosys uses `proc_self_dirname() + "yosys-abc"` to
  find its ABC companion. Since `/proc/self/exe` is in `_lib/`, yosys looks for
  `_lib/yosys-abc`. We create symlinks in `_lib/` for all wrapped executables.

### Ubuntu usrmerge breaks naive `lib/` or `lib64/` usage

Ubuntu's usrmerge means `lib/` -> `usr/lib/`, `lib64/` -> `usr/lib64/`, etc.
If ld-linux is placed in `lib64/`, `readlink -f` resolves through the directory
symlink and `/proc/self/exe` ends up in `usr/lib64/`, breaking the
`{exe_dir}/../share/yosys/` path. The `_lib/` directory avoids this by being a
real directory that doesn't participate in usrmerge.

### `--argv0` is required for recursive make

Without `--argv0`, GNU make's `$(MAKE)` variable is set to the `libexec/` path
of the real binary (ld-linux passes the binary path as `argv[0]`). Recursive
make calls then invoke the raw ELF binary without the wrapper, failing because
`libc.so.6` isn't in the default search path. `--argv0 "$self"` ensures
`$(MAKE)` points back to the wrapper script.

### `--inhibit-rpath ""` provides complete host isolation

Combined with `--inhibit-cache` (bypass ld.so.cache), this ensures the bundled
libraries are always used, never the host's. The `--library-path` flag provides
the search paths, equivalent to `LD_LIBRARY_PATH`.

### TCL_LIBRARY must be set explicitly

OpenROAD and yosys embed a compiled-in TCL library path. The `--inhibit-cache`
flag isolates shared libraries but not TCL's `init.tcl` discovery. Without
`TCL_LIBRARY`, tools may find the host's TCL (version mismatch) or nothing.
The wrapper sets it with a fallback: `${TCL_LIBRARY:-$top_dir/usr/share/...}`.

## Directory layout after patching

```
{extraction_root}/
  _lib/
    ld-linux-x86-64.so.2    # real file (copied, not symlinked)
    openroad -> ../OpenROAD-flow-scripts/.../bin/openroad  # sibling symlink
    yosys -> ../OpenROAD-flow-scripts/.../bin/yosys
    yosys-abc -> ../OpenROAD-flow-scripts/.../bin/yosys-abc
    ...
  lib64/ -> usr/lib64/       # usrmerge symlink (untouched)
  libexec/                   # real ELF binaries
    OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad
    OpenROAD-flow-scripts/tools/install/yosys/bin/yosys
    usr/bin/make
    ...
  share/
    yosys -> ../OpenROAD-flow-scripts/.../share/yosys  # share symlink
    ...
  OpenROAD-flow-scripts/tools/install/OpenROAD/bin/
    openroad                 # wrapper script
  OpenROAD-flow-scripts/tools/install/yosys/bin/
    yosys                    # wrapper script
    yosys-abc                # wrapper script
  usr/bin/
    make                     # wrapper script
    klayout                  # wrapper script
```
