#!/bin/bash
set -euo pipefail

SAIF_FILE="$1"

if [ ! -s "$SAIF_FILE" ]; then
    echo "FAIL: $SAIF_FILE is empty or missing" >&2
    exit 1
fi

# verilator_saif() must pass --trace-saif-file=<path> to the simulator,
# pointing at the genrule's $@.
if ! grep -q "^--trace-saif-file=" "$SAIF_FILE"; then
    echo "FAIL: --trace-saif-file=... not in argv" >&2
    cat "$SAIF_FILE" >&2
    exit 1
fi

# The stimulus path must appear as a positional argument after the
# --trace-saif-file flag. Resolved bazel-out path, so just match the
# basename.
if ! grep -q "mock_stimulus.bin" "$SAIF_FILE"; then
    echo "FAIL: stimulus path not in argv" >&2
    cat "$SAIF_FILE" >&2
    exit 1
fi

# Each of the three extra_args items must appear verbatim, in argv-
# order, after the stimulus. Use grep with -F to avoid interpreting the
# hex literal as a regex.
for tok in "extra-arg-one" "extra-arg-two" "0x42"; do
    if ! grep -Fq "$tok" "$SAIF_FILE"; then
        echo "FAIL: extra_args token '$tok' missing from argv" >&2
        cat "$SAIF_FILE" >&2
        exit 1
    fi
done

echo "PASS: verilator_saif_argv_test"
