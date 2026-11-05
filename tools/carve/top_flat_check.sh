#!/bin/sh
# The flattened top level's check on a small design (top_flat_check.py).
# Usage: top_flat_check.sh <check> <period_ps> <whole.txt> <whole_flat.txt>
set -e
exec "$1" "$2" "$3" "$4"
