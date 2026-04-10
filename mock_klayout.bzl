"""Repository rule that generates a mock klayout binary.

Creates dummy GDS files when invoked, allowing the ORFS flow to
complete through GDS generation without a real KLayout installation.
Used as the default klayout when no real klayout is provided.
"""

_KLAYOUT_PY = '''\
#!/usr/bin/env python3
"""Mock klayout — creates dummy GDS files."""

import os
import sys

# Minimal GDS II file: HEADER(v7) + BGNLIB + ENDLIB
GDS_HEADER = (
    b"\\x00\\x06\\x00\\x02\\x00\\x07"  # HEADER record, version 7
    b"\\x00\\x1c\\x01\\x02"  # BGNLIB record
    b"\\x00\\x01\\x00\\x01\\x00\\x01\\x00\\x01\\x00\\x00"  # mod time
    b"\\x00\\x01\\x00\\x01\\x00\\x01\\x00\\x01\\x00\\x00"  # access time
    b"\\x00\\x04\\x04\\x00"  # ENDLIB record
)

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "-v":
        print("KLayout 0.0.0 (mock)")
        return 0

    rd_args = {}
    i = 0
    while i < len(argv):
        if argv[i] == "-rd" and i + 1 < len(argv):
            i += 1
            if "=" in argv[i]:
                key, value = argv[i].split("=", 1)
                rd_args[key] = value
        i += 1

    for key in ("out", "out_file"):
        if key in rd_args:
            os.makedirs(os.path.dirname(rd_args[key]) or ".", exist_ok=True)
            with open(rd_args[key], "wb") as f:
                f.write(GDS_HEADER)

    print("mock klayout (CI stub)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

_KLAYOUT_SH = '''\
#!/bin/sh
dir="$(cd "$(dirname "$0")" && pwd)"
for py in \\
    "$dir/klayout.py" \\
    "$dir/klayout.runfiles/_main/klayout.py" \\
; do
    [ -f "$py" ] && exec python3 "$py" "$@"
done
echo "error: cannot find klayout.py" >&2
exit 1
'''

_BUILD = '''\
sh_binary(
    name = "klayout",
    srcs = ["klayout.sh"],
    data = ["klayout.py"],
    visibility = ["//visibility:public"],
)

exports_files(
    ["klayout.py"],
    visibility = ["//visibility:public"],
)
'''

def _mock_klayout_impl(repository_ctx):
    repository_ctx.file("BUILD.bazel", _BUILD)
    repository_ctx.file("klayout.py", _KLAYOUT_PY, executable = True)
    repository_ctx.file("klayout.sh", _KLAYOUT_SH, executable = True)

mock_klayout = repository_rule(
    implementation = _mock_klayout_impl,
    doc = "Creates a mock klayout repo that produces dummy GDS files.",
)
