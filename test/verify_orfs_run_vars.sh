#!/bin/bash
set -euo pipefail

output_file="$1"

fail=0
for var in CORE_UTILIZATION CORE_MARGIN PLACE_DENSITY; do
    if ! grep -q "$var=" "$output_file"; then
        echo "FAIL: Missing $var in $output_file"
        fail=1
    elif grep -q "$var=MISSING" "$output_file"; then
        echo "FAIL: $var was MISSING in $output_file"
        fail=1
    fi
done

if [ $fail -eq 1 ]; then
    echo "Output contents:"
    cat "$output_file"
    exit 1
fi
echo "PASS: All required variables found."
exit 0
