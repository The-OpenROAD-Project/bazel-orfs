"""Path helpers for `orfs_run_executable` shell wrappers.

The wrapper script runs under `bazel run` and resolves runfiles entries
relative to a `$RUNFILES` variable it computes from `$(pwd)/..`. To make
the env-var paths it injects into the orfs Makefile invariant to the
Makefile's `cd $(RESULTS_DIR)` step, every path must be absolute under
`$RUNFILES`.

Bazel 7+ exposes external repos in `.short_path` as `../<repo>/...`
(rather than the old `external/<repo>/...`); workspace-local files come
through as plain `path/to/file`. The two helpers below normalise both
forms to the on-disk runfiles layout that the wrapper sees at runtime.
"""

# Prefix that .short_path uses for external-repo files in Bazel 7+.
_EXTERNAL_SHORT_PATH_PREFIX = "../"

def runtime_path(short_path):
    """Convert a `.short_path` to its `external/<repo>/...` form for an
    external-repo file, or pass through unchanged for a workspace file.

    Combined with the `external -> $(pwd)/..` symlink the wrapper
    creates at runtime, this yields a cwd-invariant runfiles path.
    """
    if short_path.startswith(_EXTERNAL_SHORT_PATH_PREFIX):
        return "external/" + short_path[len(_EXTERNAL_SHORT_PATH_PREFIX):]
    return short_path

def absolute_runtime(short_path, runfiles_var):
    """Anchor a `.short_path` under the wrapper's `$RUNFILES` variable.

    External-repo files (`../<repo>/...`) live directly under
    `$RUNFILES/<repo>/...`; workspace-local files live under
    `$RUNFILES/_main/<path>` (where `_main` is the main workspace's
    runfiles repo dir).
    """
    if short_path.startswith(_EXTERNAL_SHORT_PATH_PREFIX):
        return "{}/{}".format(
            runfiles_var,
            short_path[len(_EXTERNAL_SHORT_PATH_PREFIX):],
        )
    return "{}/_main/{}".format(runfiles_var, short_path)
