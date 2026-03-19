#!/bin/bash
# Runs all linters/formatters on files changed since origin/main.
# Usage: bazelisk run //:fix_lint
set -e

cd "${BUILD_WORKSPACE_DIRECTORY:-.}"

MERGE_BASE=$(git merge-base origin/main HEAD 2>/dev/null || echo HEAD~1)

# Buildifier: format and lint Bazel files
BAZEL_FILES=$(git diff --name-only --diff-filter=d "$MERGE_BASE" -- \
    '*.bzl' '*.bazel' 'BUILD' 'MODULE.bazel' 'WORKSPACE' 2>/dev/null || true)
if [ -n "$BAZEL_FILES" ]; then
    echo "buildifier: $(echo "$BAZEL_FILES" | wc -w) file(s)"
    echo "$BAZEL_FILES" | xargs buildifier
    echo "$BAZEL_FILES" | xargs buildifier -lint warn
fi

# Black: format Python files
PY_FILES=$(git diff --name-only --diff-filter=d "$MERGE_BASE" -- '*.py' 2>/dev/null || true)
if [ -n "$PY_FILES" ] && command -v black >/dev/null 2>&1; then
    echo "black: $(echo "$PY_FILES" | wc -w) file(s)"
    echo "$PY_FILES" | xargs black --quiet
fi

echo "fix_lint: done"
