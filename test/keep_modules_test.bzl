"""Unit tests for keep_modules() in private/stages.bzl.

SYNTH_KEEP_MODULES arrives from a config.mk where the list is spread over
backslash-continued lines, so the string reaches bazel with runs of
spaces. Its length sets SYNTH_NUM_PARTITIONS and its entries decide which
per-module re-canonicalization actions get declared, so a miscount is not
cosmetic: too few partitions under-parallelises, and a bare split() is
rejected outright by Starlark.

Before this helper the same string was parsed three different ways in
three places -- correctly once, miscounted once, and with a separator-less
split() once. These tests pin the one behaviour.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:stages.bzl", "keep_modules")

def _absent_is_empty_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(env, [], keep_modules({}))
    asserts.equals(env, [], keep_modules({"SYNTH_KEEP_MODULES": ""}))
    return unittest.end(env)

def _single_module_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(env, ["dbg"], keep_modules({"SYNTH_KEEP_MODULES": "dbg"}))
    return unittest.end(env)

def _runs_of_spaces_do_not_inflate_the_count_test(ctx):
    env = unittest.begin(ctx)

    # What a backslash-continued config.mk list actually looks like once
    # make has joined it: single names separated by runs of whitespace.
    # A plain split(" ") yields empty fields here and overcounts.
    value = "  exu   dec_ib_ctl    lsu_stbuf  "
    asserts.equals(
        env,
        ["exu", "dec_ib_ctl", "lsu_stbuf"],
        keep_modules({"SYNTH_KEEP_MODULES": value}),
    )
    asserts.equals(env, 3, len(keep_modules({"SYNTH_KEEP_MODULES": value})))
    return unittest.end(env)

def _order_is_preserved_test(ctx):
    env = unittest.begin(ctx)

    # Partition assignment is positional, so the caller's order must
    # survive: this helper must not sort.
    asserts.equals(
        env,
        ["b", "a", "c"],
        keep_modules({"SYNTH_KEEP_MODULES": "b a c"}),
    )
    return unittest.end(env)

def _generated_names_survive_test(ctx):
    env = unittest.begin(ctx)

    # Chisel/yosys-generated module names carry characters the partition
    # filename sanitiser rewrites; the list itself must keep them intact.
    names = "Queue_41 data_arrays_0_ext DCacheModuleanon2 ram_2048x39"
    asserts.equals(
        env,
        ["Queue_41", "data_arrays_0_ext", "DCacheModuleanon2", "ram_2048x39"],
        keep_modules({"SYNTH_KEEP_MODULES": names}),
    )
    return unittest.end(env)

def _other_arguments_are_ignored_test(ctx):
    env = unittest.begin(ctx)
    arguments = {
        "SYNTH_HIERARCHICAL": "1",
        "SYNTH_KEEP_MODULES": "exu dbg",
        "CORE_UTILIZATION": "30",
    }
    asserts.equals(env, ["exu", "dbg"], keep_modules(arguments))
    return unittest.end(env)

absent_is_empty_test = unittest.make(_absent_is_empty_test)
single_module_test = unittest.make(_single_module_test)
runs_of_spaces_do_not_inflate_the_count_test = unittest.make(
    _runs_of_spaces_do_not_inflate_the_count_test,
)
order_is_preserved_test = unittest.make(_order_is_preserved_test)
generated_names_survive_test = unittest.make(_generated_names_survive_test)
other_arguments_are_ignored_test = unittest.make(_other_arguments_are_ignored_test)

def keep_modules_test_suite(name):
    unittest.suite(
        name,
        absent_is_empty_test,
        single_module_test,
        runs_of_spaces_do_not_inflate_the_count_test,
        order_is_preserved_test,
        generated_names_survive_test,
        other_arguments_are_ignored_test,
    )
