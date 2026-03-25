# Claude Code Instructions

## Commits

Always use `git commit -s` to include a `Signed-off-by` trailer.

## Formatting

Before committing, run `bazelisk run //:fix_lint` to format and lint all changed files. This is the single source of truth — do NOT run `buildifier`, `bazelisk mod tidy`, or `black` individually, as `fix_lint` handles all of them with the correct CI-compatible configuration:

- `buildifier` on changed `.bzl`/`BUILD`/`MODULE.bazel` files (respects `.bazelignore`)
- `bazelisk mod tidy` with CI config when `MODULE.bazel` changed (ensures lockfile matches CI)
- `black` on changed `.py` files

Before running `fix_lint`, set up the CI config:

```sh
echo 'import %workspace%/.github/ci.bazelrc' >> user.bazelrc
bazelisk run //:fix_lint
rm -f user.bazelrc
```

This matches exactly what CI does. Without this, the "Lint and lockfile check" CI job will fail.
