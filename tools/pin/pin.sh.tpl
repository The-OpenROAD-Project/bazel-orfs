#!/usr/bin/env sh

export RUNFILES="$0.runfiles/_main"

exec python3 "${RUNFILES}/${PINNER}" --bucket "${BUCKET}" --lock "${LOCK}" --package "${PACKAGE}" "$@"
