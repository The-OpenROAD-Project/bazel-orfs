#!/bin/sh
# The launch-side bound's check on a small design (crossing_launch_check.py).
# Usage: crossing_launch_check.sh <check> <launch dir> <crossing_time dir>
set -e
exec "$1" "$2" "$3"
