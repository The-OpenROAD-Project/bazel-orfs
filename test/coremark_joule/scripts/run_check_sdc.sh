#!/bin/sh
# Runs check_sdc over the constraint files named after it.
#
# A shell wrapper because sh_test passes the binary and its inputs as
# runfiles paths, and the first argument is the checker itself.
set -eu
checker="$1"
shift
exec "$checker" "$@"
