# FRC-6: source-file-missing

| Field | Value |
|-------|-------|
| **ID** | FRC-6 |
| **Name** | source-file-missing |
| **Severity** | Error |
| **Stage** | Any (TCL interpreter level) |

## What it checks

When a TCL script checks `file exists <path>` for a `.tcl` file and the
file does not exist, this rule emits a warning. This catches the common
ORFS pattern where `io.tcl` or `constraint.sdc` conditionally sources a
helper script via:

```tcl
if { [file exists $f] } { source $f }
```

If the file is missing in the Bazel sandbox, the source is silently
skipped, procs defined in the helper are never loaded, and downstream
commands fail with cryptic "invalid command name" errors.

## Why it matters

Silent source failures are the worst kind of bug: the flow proceeds
without error until a much later command crashes because a proc was
never defined. The error message gives no hint that a missing `source`
is the root cause.

In Make, hardcoded relative paths like `designs/src/mock-array/util.tcl`
work because the working directory is the ORFS root. In Bazel, files are
only available via declared dependencies and sandbox paths — a hardcoded
path silently resolves to nothing.

## Example

`flow/designs/asap7/mock-cpu/io.tcl` tried to source `util.tcl`:

```tcl
foreach prefix {"" flow/} {
  set f ${prefix}designs/src/mock-array/util.tcl
  if { [file exists $f] } { source $f }
}
```

Neither path existed in the sandbox. The `match_pins` proc was never
defined, and `floorplan.tcl` crashed at line 158.

## Fix

Use environment variable paths instead of hardcoded relative paths:

```tcl
source $::env(SDC_FILE_EXTRA)
```

The env var is set by bazel-orfs to the correct sandbox path of the
dependency. This is the same pattern used in patch 0021 to fix
`constraint.sdc`.

## Implementation

- **Check:** `gallery/lint/tcl/src/bin/tcl_interpreter.py`, `_cmd_file`
  method, `exists` subcommand
- **Tests:** `gallery/lint/tcl/src/bin/tcl_interpreter_test.py`, `TestFRC`
  class
