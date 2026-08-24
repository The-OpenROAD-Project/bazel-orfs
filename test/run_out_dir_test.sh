#!/bin/sh
set -eu
dir="$1"
for name in alpha beta; do
    if ! grep -q "$name" "$dir/$name.txt"; then
        echo "FAIL: $dir/$name.txt missing or wrong content" >&2
        exit 1
    fi
done
echo "out_dir contents ok"
