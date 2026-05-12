#!/bin/bash
# Mock simulator. Writes its argv into the path named by
# --trace-saif-file=<path>, so the wiring test can inspect what the
# genrule actually passed.
set -euo pipefail

saif_path=""
for arg in "$@"; do
    case "$arg" in
        --trace-saif-file=*)
            saif_path="${arg#--trace-saif-file=}"
            ;;
    esac
done

if [ -z "$saif_path" ]; then
    echo "mock_verilator: missing --trace-saif-file=<path>" >&2
    exit 1
fi

# Record full argv, one per line, for the test to grep.
{
    for arg in "$@"; do
        printf '%s\n' "$arg"
    done
} > "$saif_path"
