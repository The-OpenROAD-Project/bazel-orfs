#!/bin/sh
# sh_test shim for the AUTO_MEMORIES guard.
#
# blackboxes.txt lives inside the flow's `memories` directory output, so
# the path is built here rather than asking the BUILD file to name a file
# inside a directory artifact.
set -eu
checker="$1"
memories_dir="$2"
netlist="$3"
shift 3
exec "$checker" "$memories_dir/blackboxes.txt" "$netlist" --expect "$@"
