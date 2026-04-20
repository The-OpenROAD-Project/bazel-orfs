#!/bin/bash
# Opens an HTML file passed as a rootpath-relative argument in the default
# browser. Invoked via `bazel run` on the sh_binary wrapper emitted by
# orfs_flow(html=True).
set -e
if [ -n "${RUNFILES_DIR}" ] && [ -f "${RUNFILES_DIR}/_main/$1" ]; then
  html="${RUNFILES_DIR}/_main/$1"
elif [ -f "$0.runfiles/_main/$1" ]; then
  html="$0.runfiles/_main/$1"
else
  html="$1"
fi
exec xdg-open "$html"
