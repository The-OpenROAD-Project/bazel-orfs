"""Skylib unittest coverage for //private:runfiles_paths.bzl.

Both helpers operate on plain strings, so no analysis-phase scaffolding
is needed beyond skylib's `unittest.make`.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:runfiles_paths.bzl", "absolute_runtime", "runtime_path")

def _runtime_path_external_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        "external/orfs+/flow/Makefile",
        runtime_path("../orfs+/flow/Makefile"),
    )
    return unittest.end(env)

_runtime_path_external_test = unittest.make(_runtime_path_external_test_impl)

def _runtime_path_workspace_test_impl(ctx):
    env = unittest.begin(ctx)
    # A workspace-local short_path has no `../<repo>/` prefix, so it
    # passes through untouched.
    asserts.equals(
        env,
        "private/rules.bzl",
        runtime_path("private/rules.bzl"),
    )
    return unittest.end(env)

_runtime_path_workspace_test = unittest.make(_runtime_path_workspace_test_impl)

def _runtime_path_handles_repo_with_plus_test_impl(ctx):
    env = unittest.begin(ctx)
    # bzlmod repos like `openroad+` and `bazel-orfs++orfs_repositories+...`
    # carry '+' in their names; the prefix check must not depend on the
    # repo name shape, only on the leading "../".
    asserts.equals(
        env,
        "external/bazel-orfs++orfs_repositories+mock_klayout/klayout.sh",
        runtime_path(
            "../bazel-orfs++orfs_repositories+mock_klayout/klayout.sh",
        ),
    )
    return unittest.end(env)

_runtime_path_handles_repo_with_plus_test = unittest.make(
    _runtime_path_handles_repo_with_plus_test_impl,
)

def _absolute_runtime_external_test_impl(ctx):
    env = unittest.begin(ctx)
    # External-repo files are anchored directly under $RUNFILES — no
    # `_main/` segment (that's only for workspace files).
    asserts.equals(
        env,
        "$RUNFILES/orfs+/flow/Makefile",
        absolute_runtime("../orfs+/flow/Makefile", "$RUNFILES"),
    )
    return unittest.end(env)

_absolute_runtime_external_test = unittest.make(
    _absolute_runtime_external_test_impl,
)

def _absolute_runtime_workspace_test_impl(ctx):
    env = unittest.begin(ctx)
    # Workspace-local files live under $RUNFILES/_main/<short_path>.
    asserts.equals(
        env,
        "$RUNFILES/_main/private/rules.bzl",
        absolute_runtime("private/rules.bzl", "$RUNFILES"),
    )
    return unittest.end(env)

_absolute_runtime_workspace_test = unittest.make(
    _absolute_runtime_workspace_test_impl,
)

def _absolute_runtime_respects_runfiles_var_test_impl(ctx):
    env = unittest.begin(ctx)
    # The caller controls the variable name; we just splice it in.
    asserts.equals(
        env,
        "${MY_RUNFILES}/orfs+/x",
        absolute_runtime("../orfs+/x", "${MY_RUNFILES}"),
    )
    return unittest.end(env)

_absolute_runtime_respects_runfiles_var_test = unittest.make(
    _absolute_runtime_respects_runfiles_var_test_impl,
)

def _absolute_runtime_main_workspace_handles_nested_path_test_impl(ctx):
    env = unittest.begin(ctx)
    # Multi-segment workspace paths must keep their structure intact —
    # we only prepend `$RUNFILES/_main/`, never split or rewrite.
    asserts.equals(
        env,
        "$R/_main/private/runfiles_paths.bzl",
        absolute_runtime("private/runfiles_paths.bzl", "$R"),
    )
    return unittest.end(env)

_absolute_runtime_main_workspace_handles_nested_path_test = unittest.make(
    _absolute_runtime_main_workspace_handles_nested_path_test_impl,
)

def runfiles_paths_test_suite(name):
    """Register all runfiles_paths unit tests under `name`."""
    unittest.suite(
        name,
        _runtime_path_external_test,
        _runtime_path_workspace_test,
        _runtime_path_handles_repo_with_plus_test,
        _absolute_runtime_external_test,
        _absolute_runtime_workspace_test,
        _absolute_runtime_respects_runfiles_var_test,
        _absolute_runtime_main_workspace_handles_nested_path_test,
    )
