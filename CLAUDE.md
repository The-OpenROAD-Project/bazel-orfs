# Claude Code Instructions

## Commits

Always use `git commit -s` to include a `Signed-off-by` trailer.

## Formatting

After editing any `.bzl`, `BUILD`, `BUILD.bazel`, `MODULE.bazel`, or `WORKSPACE` file, run `buildifier` on the changed files before committing.

## MODULE.bazel.lock

CI runs `bazel mod tidy && git diff --exit-code` to verify the lockfile is up to date. CI uses `.github/ci.bazelrc` which overrides module resolution (e.g. `--override_module=kepler-formal=...`), so the lockfile generated locally may differ from what CI expects.

After changing `MODULE.bazel`, regenerate the lockfile with the CI config applied:

```sh
echo 'import %workspace%/.github/ci.bazelrc' >> user.bazelrc
bazelisk mod tidy
git checkout user.bazelrc
```

This ensures the lockfile matches CI's module resolution. Without this, the "Generate configs" CI job will fail with a lockfile diff.
