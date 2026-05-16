"""Skylib unittest coverage for //private:blender.bzl's blender_supports_pdk.

`blender_supports_pdk` is a pure-Starlark predicate, so no analysis-phase
scaffolding is needed beyond skylib's `unittest.make`.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:blender.bzl", "blender_supports_pdk")

def _short_name_sky130hd_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.true(env, blender_supports_pdk("sky130hd"))
    return unittest.end(env)

_short_name_sky130hd_test = unittest.make(_short_name_sky130hd_test_impl)

def _short_name_sky130hs_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.true(env, blender_supports_pdk("sky130hs"))
    return unittest.end(env)

_short_name_sky130hs_test = unittest.make(_short_name_sky130hs_test_impl)

def _short_name_gf180_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.true(env, blender_supports_pdk("gf180"))
    return unittest.end(env)

_short_name_gf180_test = unittest.make(_short_name_gf180_test_impl)

def _short_name_ihp_sg13g2_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.true(env, blender_supports_pdk("ihp-sg13g2"))
    return unittest.end(env)

_short_name_ihp_sg13g2_test = unittest.make(_short_name_ihp_sg13g2_test_impl)

def _label_form_test_impl(ctx):
    env = unittest.begin(ctx)

    # Callers in orfs_design.bzl pass `"//flow:" + platform`; the
    # predicate must strip the package + colon and consult the same
    # short-name table that orfs_blender() uses.
    asserts.true(env, blender_supports_pdk("//flow:sky130hd"))
    return unittest.end(env)

_label_form_test = unittest.make(_label_form_test_impl)

def _unsupported_pdk_test_impl(ctx):
    env = unittest.begin(ctx)

    # asap7 is a real PDK in this repo but has no BlenderGDS stackup;
    # the predicate is exactly what gates `orfs_design(blender = True)`
    # so it must return False rather than fail loudly.
    asserts.false(env, blender_supports_pdk("asap7"))
    return unittest.end(env)

_unsupported_pdk_test = unittest.make(_unsupported_pdk_test_impl)

def _nonsense_pdk_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.false(env, blender_supports_pdk("nonsense"))
    return unittest.end(env)

_nonsense_pdk_test = unittest.make(_nonsense_pdk_test_impl)

def _none_pdk_test_impl(ctx):
    env = unittest.begin(ctx)
    asserts.false(env, blender_supports_pdk(None))
    return unittest.end(env)

_none_pdk_test = unittest.make(_none_pdk_test_impl)

def blender_supports_pdk_test_suite(name):
    """Register all blender_supports_pdk unit tests under `name`."""
    unittest.suite(
        name,
        _short_name_sky130hd_test,
        _short_name_sky130hs_test,
        _short_name_gf180_test,
        _short_name_ihp_sg13g2_test,
        _label_form_test,
        _unsupported_pdk_test,
        _nonsense_pdk_test,
        _none_pdk_test,
    )
