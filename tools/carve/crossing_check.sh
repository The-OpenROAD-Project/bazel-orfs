#!/bin/sh
# The crossing method's check: the sets' reports, merged, hold the paths
# the same design timed whole reports, each needing the same time
# (crossing_report.py --whole). Usage:
#   crossing_check.sh <crossing_report> <budget_ps> <whole.txt> <sets' reports dir>
set -e
out="${TEST_TMPDIR:-$(mktemp -d)}/crossings"
"$1" --whole "$3" "$out" "$2" "$4"
