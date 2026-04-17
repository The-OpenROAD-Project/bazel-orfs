#!/bin/bash
# Test that lint=True excludes heavy dependencies from runfiles.
# The test's own runfiles (which include the lint flow target as data)
# should NOT contain klayout or opensta.
set -euo pipefail

# The test runfiles directory contains symlinks to the lint flow target's deps
runfiles_dir="${TEST_SRCDIR:-$0.runfiles}"

# List all files in the runfiles tree
manifest_content=$(find "$runfiles_dir" -type f -o -type l 2>/dev/null || true)

HEAVY_DEPS=(
  "klayout"
  "opensta"
)

errors=0
for dep in "${HEAVY_DEPS[@]}"; do
  if echo "$manifest_content" | grep -qi "$dep"; then
    echo "FAIL: Found heavy dependency '$dep' in lint flow runfiles:"
    echo "$manifest_content" | grep -i "$dep" | head -3
    errors=$((errors + 1))
  fi
done

if [[ $errors -gt 0 ]]; then
  echo "FAIL: $errors heavy dependencies found in lint flow runfiles"
  exit 1
fi

echo "PASS: No heavy dependencies found in lint flow runfiles"
