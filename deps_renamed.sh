#!/usr/bin/env bash
# //:deps is now //:dirty, the dirty lane. This stub names the new
# command and stops; it goes at a later bump.
echo "//:deps is now //:dirty (@bazel-orfs//:dirty from another workspace):" >&2
echo "  bazelisk run //:dirty -- $*" >&2
exit 1
