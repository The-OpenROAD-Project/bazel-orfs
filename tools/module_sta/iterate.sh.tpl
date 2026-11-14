#!/bin/bash
# One iteration of an AI loop on %%MODULE%%, in the context %%NAME%% was cut
# with (tools/module_sta, private/module_sta.bzl):
#
#   bazelisk run <this target> -- <new module name> <netlist.v>...
#
# the new module's netlist, its module renamed to <new module name>, and
# the netlists of the modules it instantiates, as they are. Writes
# %%NAME%%.ends (every endpoint the context times exactly, "<pin> <slack>")
# and %%NAME%%.json (worst slack, total negative slack, violating endpoints,
# seconds) to the working directory, and prints the summary.
set -euo pipefail
if [ $# -lt 2 ]; then
  echo "usage: bazelisk run <target> -- <new module name> <netlist.v>..." >&2
  exit 2
fi
here=$PWD
work=${BUILD_WORKING_DIRECTORY:-$PWD}
new=$1
shift
nets=""
for n in "$@"; do
  case "$n" in
  /*) nets="$nets $n" ;;
  *) nets="$nets $work/$n" ;;
  esac
done
PSTA_CLOCKS="%%CLOCKS%%" \
  PSTA_CONTEXT_DB="$here/%%CONTEXT%%" \
  PSTA_EXACT="$here/%%EXACT%%" \
  PSTA_M="%%MODULE%%" \
  PSTA_NEW="$nets" \
  PSTA_NEW_MODULE="$new" \
  PSTA_ENDPOINTS="$work/%%NAME%%.ends" \
  PSTA_STATS="$work/%%NAME%%.json" \
  PSTA_TMP="$work" \
  bash "$here/%%STA_SH%%" "$here/%%OPENROAD%%" "$here/%%SCRIPT%%" "$here/%%LIBS%%" |
  grep -E '^iterate:|ERROR'
