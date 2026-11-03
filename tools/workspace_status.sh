#!/bin/sh
# Bazel's workspace status (.bazelrc, --workspace_status_command): the
# commit, its date and the day of the build, for the few targets that
# stamp (stamp = 1), such as the XSTile kit's README.pdf. The day is a
# stable key: Bazel's own BUILD_TIMESTAMP does not reach a stamped
# genrule as the build's time, and a stable key re-runs a stamped action
# once a day at most. Nothing else is printed: a stamped output
# names the source it was made from and nothing about the machine. Outside
# a git checkout it prints nothing, and a stamped target says unstamped.
commit=$(git rev-parse --short=12 HEAD 2>/dev/null) || exit 0
date=$(git log -1 --format=%cs HEAD 2>/dev/null)
if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then
  commit="$commit-dirty"
fi
echo "STABLE_GIT_COMMIT $commit"
echo "STABLE_GIT_DATE $date"
echo "STABLE_BUILD_DATE $(date -u +%Y-%m-%d)"
