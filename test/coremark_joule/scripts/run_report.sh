#!/bin/sh
# sh_binary shim: hand the report binary the result files the BUILD file
# already knows by label, rather than making it re-derive runfiles paths.
set -eu
report="$1"
shift
exec "$report" "$@"
