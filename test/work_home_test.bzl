"""Unit tests for work_home_relative() in private/environment.bzl.

WORK_HOME tells ORFS's Makefile where RESULTS_DIR, LOG_DIR and
OBJECTS_DIR live. It used to be built as `"./" + ctx.label.package`,
which is right only for a design in the main repository. An external
repository's files sit under `external/<repo>/` in the exec root, in
bazel's runfiles layout, and in the tree deploy.tpl lays out for
`bazelisk run` -- so for @orfs//flow/designs/asap7/gcd the unprefixed
path pointed at a directory holding none of that design's results.

The failure is quiet and confusing, because ORFS derives its interactive
targets from a wildcard:

    RESULTS_ODB = $(notdir $(sort $(wildcard $(RESULTS_DIR)/*.odb)))

With WORK_HOME wrong the wildcard matches nothing, so `open_%`/`gui_%`
are never even declared and make reports a missing *prerequisite*
rather than a missing directory:

    make: *** No rule to make target 'open_1_synth.odb',
          needed by 'open_synth'.  Stop.

Two other call sites already prefixed WORK_HOME by hand; these tests pin
the one shared behaviour so the three cannot drift apart again.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:environment.bzl", "work_home_relative")

def _ctx(workspace_name, package):
    """A stand-in for a rule ctx: work_home_relative reads only the label."""
    return struct(label = struct(
        workspace_name = workspace_name,
        package = package,
    ))

def _main_repo_is_unprefixed_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        "test",
        work_home_relative(_ctx("", "test")),
    )
    return unittest.end(env)

def _external_repo_is_prefixed_test(ctx):
    env = unittest.begin(ctx)

    # The case that motivated this: building an ORFS design from a
    # bazel-orfs workspace.
    asserts.equals(
        env,
        "external/orfs+/flow/designs/asap7/gcd",
        work_home_relative(_ctx("orfs+", "flow/designs/asap7/gcd")),
    )
    return unittest.end(env)

def _no_trailing_slash_when_package_is_empty_test(ctx):
    env = unittest.begin(ctx)

    # A design at the root of an external repo must not yield
    # "external/orfs+/", which make would join into a doubled slash.
    asserts.equals(env, "external/orfs+", work_home_relative(_ctx("orfs+", "")))
    asserts.equals(env, "", work_home_relative(_ctx("", "")))
    return unittest.end(env)

def _canonical_repo_names_survive_test(ctx):
    env = unittest.begin(ctx)

    # bzlmod canonical names carry '+' (and '~' on older bazel); the
    # prefix has to reproduce them verbatim, since that is the directory
    # name bazel actually creates.
    asserts.equals(
        env,
        "external/rules_foo+1.2.3/pkg",
        work_home_relative(_ctx("rules_foo+1.2.3", "pkg")),
    )
    return unittest.end(env)

main_repo_is_unprefixed_test = unittest.make(_main_repo_is_unprefixed_test)
external_repo_is_prefixed_test = unittest.make(_external_repo_is_prefixed_test)
no_trailing_slash_when_package_is_empty_test = unittest.make(
    _no_trailing_slash_when_package_is_empty_test,
)
canonical_repo_names_survive_test = unittest.make(
    _canonical_repo_names_survive_test,
)

def work_home_test_suite(name):
    unittest.suite(
        name,
        main_repo_is_unprefixed_test,
        external_repo_is_prefixed_test,
        no_trailing_slash_when_package_is_empty_test,
        canonical_repo_names_survive_test,
    )
