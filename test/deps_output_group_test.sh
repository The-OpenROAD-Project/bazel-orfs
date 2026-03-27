#!/bin/sh
# Verify that the deps deploy script was produced and looks correct.
# The deploy script is passed as a data dependency via a custom rule
# that extracts it from the target's OutputGroupInfo.deps.

set -e

DEPLOY_SCRIPT="$1"

if [ ! -f "$DEPLOY_SCRIPT" ]; then
    echo "FAIL: deps deploy script not found: $DEPLOY_SCRIPT"
    exit 1
fi

# Verify the deploy script is a shell script
if ! head -1 "$DEPLOY_SCRIPT" | grep -q '#!/usr/bin/env bash'; then
    echo "FAIL: deploy script missing shebang"
    exit 1
fi

# Verify it contains config.mk reference (from template expansion)
if ! grep -q "config.mk" "$DEPLOY_SCRIPT"; then
    echo "FAIL: deploy script missing config.mk reference"
    exit 1
fi

echo "PASS: deps output group deploy script is valid"
