#!/bin/bash
# Test that lint=True excludes heavy dependencies from runfiles, and that
# stage runfiles contain the files that config.mk `include`s at runtime.
#
# `bazel run <stage>` uses the stage exe's DefaultInfo.runfiles. Any file
# referenced by `<stage>.short.mk` (deployed as config.mk) must be present
# there, otherwise make fails parsing config.mk before doing any work.
# Historically args.mk was in the deps tarball but not the bazel-run
# runfiles, so `bazel run <stage> -- gui_cts` broke with
# "No such file or directory: .../4_cts.args.mk" — tarball-based tests
# can't catch that.
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

# For every *.short.mk in the runfiles, verify every `include <path>`
# resolves to an existing file at the expected short_path location.
while IFS= read -r short_mk; do
  [ -n "$short_mk" ] || continue
  # Deploy copies config_short to $dst_main/config.mk, then `cd`s into
  # _main before running make. Resolve includes relative to the _main/
  # prefix of the short.mk's own path — use `%` (shortest match from
  # the right) so we stop at the innermost `/_main/`, i.e. the runfiles
  # root, not the execroot `/_main/` that's farther up the path.
  main_prefix="${short_mk%/_main/*}/_main"
  [ -d "$main_prefix" ] || main_prefix="$(dirname "$short_mk")"
  while IFS= read -r inc; do
    inc_path="$main_prefix/$inc"
    if [ ! -e "$inc_path" ]; then
      echo "FAIL: $short_mk includes '$inc' but $inc_path is missing"
      errors=$((errors + 1))
    fi
  done < <(grep -E '^include ' "$short_mk" | awk '{print $2}')
done < <(echo "$manifest_content" | grep -E '\.short\.mk$' || true)

if [[ $errors -gt 0 ]]; then
  echo "FAIL: $errors problem(s) found in lint flow runfiles"
  exit 1
fi

echo "PASS: Lint flow runfiles exclude heavy deps and satisfy short.mk includes"
