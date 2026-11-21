"""analysistest: a parent's stages read the macro view of its tier, only.

The target under test is a parent's stage. Its actions' inputs must hold
`expected`'s liberty and none of the `forbidden` targets' liberty or LEF
(a LEF the expected view shares excepted): a tier above the chosen one is
not waited for. Compared by short path,
which a configuration change leaves alone.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//private:providers.bzl", "OrfsInfo")

def _impl(ctx):
    env = analysistest.begin(ctx)
    inputs = {}
    for action in analysistest.target_actions(env):
        for f in action.inputs.to_list():
            inputs[f.short_path] = True
    label = analysistest.target_under_test(env).label
    lib = ctx.attr.expected[OrfsInfo].lib
    lef = ctx.attr.expected[OrfsInfo].lef
    asserts.true(
        env,
        lib.short_path in inputs,
        "%s does not read %s" % (label, lib.short_path),
    )
    for target in ctx.attr.forbidden:
        info = target[OrfsInfo]
        for f in [info.lib, info.lef]:
            if f and not (lef and f.short_path == lef.short_path):
                asserts.false(
                    env,
                    f.short_path in inputs,
                    "%s reads %s, of %s" % (label, f.short_path, target.label),
                )
    return analysistest.end(env)

_ATTRS = {
    "expected": attr.label(mandatory = True, providers = [OrfsInfo]),
    "forbidden": attr.label_list(providers = [OrfsInfo]),
}

macro_view_test = analysistest.make(_impl, attrs = _ATTRS)

macro_view_flag_test = analysistest.make(
    _impl,
    attrs = _ATTRS,
    config_settings = {str(Label("//:macro_view")): "real"},
)
