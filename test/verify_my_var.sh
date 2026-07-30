#!/bin/bash
set -euo pipefail

output_file="$1"

if grep -q "MY_CUSTOM_VAR is 42" "$output_file"; then
    echo "PASS: Found expected variable value in $output_file"
    exit 0
else
    echo "FAIL: Did not find expected variable value in $output_file"
    cat "$output_file"
    exit 1
fi
