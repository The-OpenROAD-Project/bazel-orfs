"""
verilog library support
"""

load("@rules_verilator//verilog:providers.bzl", "make_dag_entry", "make_verilog_info")

def _verilog_impl(ctx, split):
    if split:
        sv = ctx.actions.declare_directory(ctx.attr.name)
    else:
        sv = ctx.actions.declare_file(ctx.attr.name)

    args = ctx.actions.args()
    args.add("--format=mlir")
    if split:
        args.add("--split-verilog")

    args.add_all(ctx.attr.opts)
    args.add_all(ctx.files.srcs)
    args.add("-o", sv.path)

    ctx.actions.run(
        arguments = [args],
        executable = ctx.executable._firtool,
        inputs = ctx.files.srcs,
        outputs = [sv],
        mnemonic = "VerilogGeneration",
    )

    # TODO: Figure out how to get the directories w/o hardcoding
    verilog_info = make_verilog_info(
        new_entries = [
            make_dag_entry(
                srcs = [sv],
                hdrs = [],
                includes = [
                    sv.path,
                    sv.path + "/Simulation",
                    sv.path + "/verification",
                    sv.path + "/verification/assume",
                    sv.path + "/verification/cover",
                    sv.path + "/verification/assert",
                ],
                data = [],
                deps = [],
                label = ctx.label,
                tags = [],
            ),
        ],
        old_infos = [],
    )

    return [
        DefaultInfo(
            runfiles = ctx.runfiles(files = []),
            files = depset([sv]),
        ),
        verilog_info,
    ]

def verilog_attrs():
    return {
        "opts": attr.string_list(default = []),
        "srcs": attr.label_list(
            doc = "Cell library.",
            allow_files = True,
        ),
        "_firtool": attr.label(
            doc = "Firtool binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@circt//:bin/firtool"),
        ),
    }

verilog_directory = rule(
    implementation = lambda ctx: _verilog_impl(ctx, split = True),
    attrs = verilog_attrs(),
)

verilog_file = rule(
    implementation = lambda ctx: _verilog_impl(ctx, split = False),
    attrs = verilog_attrs(),
)

def _only_sv(f):
    """Filter for just SystemVerilog source"""

    # FIXME ideally we could use verilog_file directly on the fir target
    # https://github.com/llvm/circt/issues/9020
    if f.extension in ["v", "sv"]:
        return f.path
    return None

def _verilog_single_file_library(ctx):
    out = ctx.actions.declare_file(ctx.attr.name)

    args = ctx.actions.args()
    args.add_all(ctx.files.srcs, map_each = _only_sv)
    ctx.actions.run_shell(
        arguments = [args],
        command = "cat $@ > {}".format(out.path),
        inputs = ctx.files.srcs,
        outputs = [out],
        mnemonic = "Cat",
    )
    return [
        DefaultInfo(
            runfiles = ctx.runfiles(files = []),
            files = depset([out]),
        ),
    ]

verilog_single_file_library = rule(
    implementation = _verilog_single_file_library,
    attrs = {
        "srcs": attr.label_list(
            doc = "Verilog files.",
            allow_files = True,
        ),
    },
)
