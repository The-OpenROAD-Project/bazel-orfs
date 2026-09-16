#!/bin/sh
# sh_test shim: run the CRC gate on a captured CoreMark stdout.
#
# A shim because sh_test passes its arguments through, while a py_test
# would have to re-derive the runfiles path of a file the BUILD file
# already knows by label.
set -eu
checker="$1"
report="$2"
exec "$checker" "$report"
