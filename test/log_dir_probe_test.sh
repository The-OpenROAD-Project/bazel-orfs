#!/bin/sh
# Every stage of the src flow must have accumulated its log and metrics
# json in LOG_DIR: the whole set, not merely a non-empty directory.
set -eu
expected="$1"
shift
for out in "$@"; do
    if ! diff -u "$expected" "$out"; then
        echo "FAIL: $out is not the flow's accumulated stage logs" >&2
        exit 1
    fi
done
echo "LOG_DIR holds the flow's accumulated stage logs"
