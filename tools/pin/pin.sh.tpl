#!/usr/bin/env sh
set -e

export RUNFILES="$0.runfiles/_main"

python3 "${RUNFILES}/${PINNER}" --bucket "${BUCKET}" --lock "${LOCK}" --package "${PACKAGE}" "$@"

cd $BUILD_WORKSPACE_DIRECTORY
bazelisk mod tidy
git diff --color=always MODULE.bazel | cat
