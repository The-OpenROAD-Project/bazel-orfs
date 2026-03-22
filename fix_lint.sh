#!/bin/bash
# Runs all linters/formatters on files changed since origin/main.
# Usage: bazelisk run //:fix_lint
set -e

cd "${BUILD_WORKSPACE_DIRECTORY:-.}"

# Resolve buildifier from Bazel runfiles (provided by @buildifier_prebuilt)
RUNFILES="${RUNFILES_DIR:-${BASH_SOURCE[0]}.runfiles}"
BUILDIFIER="$RUNFILES/buildifier_prebuilt+/buildifier/buildifier"
if [ ! -x "$BUILDIFIER" ]; then
    echo "error: buildifier not found in runfiles; run via 'bazelisk run //:fix_lint'" >&2
    exit 1
fi

MERGE_BASE=$(git merge-base origin/main HEAD 2>/dev/null || echo HEAD~1)

# Buildifier: format and lint Bazel files
BAZEL_FILES=$(git diff --name-only --diff-filter=d "$MERGE_BASE" -- \
    '*.bzl' '*.bazel' 'BUILD' '**/BUILD' 'MODULE.bazel' '**/MODULE.bazel' \
    'WORKSPACE' '**/WORKSPACE' 2>/dev/null || true)
if [ -n "$BAZEL_FILES" ]; then
    echo "buildifier: $(echo "$BAZEL_FILES" | wc -w) file(s)"
    echo "$BAZEL_FILES" | xargs "$BUILDIFIER"
    echo "$BAZEL_FILES" | xargs "$BUILDIFIER" -lint warn
fi

# MODULE.bazel.lock: regenerate with CI config if MODULE.bazel changed
if git diff --name-only --diff-filter=d "$MERGE_BASE" -- MODULE.bazel | grep -q .; then
    echo "mod tidy: regenerating MODULE.bazel.lock with CI config"
    echo 'import %workspace%/.github/ci.bazelrc' >> user.bazelrc
    bazelisk mod tidy
    rm user.bazelrc
fi

# Black: format Python files
PY_FILES=$(git diff --name-only --diff-filter=d "$MERGE_BASE" -- '*.py' 2>/dev/null || true)
if [ -n "$PY_FILES" ] && command -v black >/dev/null 2>&1; then
    echo "black: $(echo "$PY_FILES" | wc -w) file(s)"
    echo "$PY_FILES" | xargs black --quiet
fi

echo "fix_lint: done"
