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

# Build grep pattern from .bazelignore (skip comments and blank lines)
BAZELIGNORE_PATTERN=""
if [ -f .bazelignore ]; then
    BAZELIGNORE_PATTERN=$(grep -v '^#' .bazelignore | grep -v '^$' | sed 's|/$||' | paste -sd'|' | sed 's/|/\\|/g')
fi

filter_ignored() {
    if [ -n "$BAZELIGNORE_PATTERN" ]; then
        grep -v "^\\($BAZELIGNORE_PATTERN\\)/" || true
    else
        cat
    fi
}

# Buildifier: format and lint Bazel files
BAZEL_FILES=$(git diff --name-only --diff-filter=d "$MERGE_BASE" -- \
    '*.bzl' '*.bazel' 'BUILD' '**/BUILD' 'MODULE.bazel' '**/MODULE.bazel' \
    'WORKSPACE' '**/WORKSPACE' 2>/dev/null | filter_ignored || true)
if [ -n "$BAZEL_FILES" ]; then
    echo "buildifier: $(echo "$BAZEL_FILES" | wc -w) file(s)"
    echo "$BAZEL_FILES" | xargs "$BUILDIFIER"
    echo "$BAZEL_FILES" | xargs "$BUILDIFIER" -lint warn
fi

# MODULE.bazel.lock: regenerate for any changed MODULE.bazel (root + sub-modules)
MODULE_FILES=$(git diff --name-only --diff-filter=d "$MERGE_BASE" -- '**/MODULE.bazel' 'MODULE.bazel' 2>/dev/null || true)
for mf in $MODULE_FILES; do
    dir=$(dirname "$mf")
    # Only tidy if the module has a lockfile to update
    [ -f "$dir/MODULE.bazel.lock" ] || continue
    if [ "$dir" = "." ]; then
        echo "mod tidy: root (with CI config)"
        bazelisk --bazelrc=.github/ci.bazelrc mod tidy
    else
        echo "mod tidy: $dir"
        (cd "$dir" && bazelisk mod tidy)
    fi
done

# Black: format Python files
PY_FILES=$(git diff --name-only --diff-filter=d "$MERGE_BASE" -- '*.py' 2>/dev/null | filter_ignored || true)
if [ -n "$PY_FILES" ] && command -v black >/dev/null 2>&1; then
    echo "black: $(echo "$PY_FILES" | wc -w) file(s)"
    echo "$PY_FILES" | xargs black --quiet
fi

echo "fix_lint: done"
