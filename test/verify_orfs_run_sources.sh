#!/bin/bash
set -e
# The test takes the generated file path as the first argument
output_file=$1

content=$(cat "$output_file")
if [[ "$content" == *"test_source_content"* ]]; then
    echo "PASS: found 'test_source_content' in output."
else
    echo "FAIL: content mismatch in $output_file:"
    cat "$output_file"
    exit 1
fi

if [[ "$content" == *"second_source_content"* ]]; then
    echo "PASS: found 'second_source_content' in output."
else
    echo "FAIL: content mismatch in $output_file (second source missing):"
    cat "$output_file"
    exit 1
fi
