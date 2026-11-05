#!/bin/sh
# The headroom's check on a small design (crossing_headroom_check.py).
# Usage: crossing_headroom_check.sh <check> <headroom dir> <crossing_time dir>
set -e
exec "$1" "$2" "$3"
