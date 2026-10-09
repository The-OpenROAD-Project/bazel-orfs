"""regfile_sim_test: a spec's generated netlist simulated beside its reference.

generate_regfile builds the spec into a structural netlist of asap7
cells; gen_tb.py writes a testbench that drives it and the reference
(the RTL module the spec replaces, or a behavioural memory built from
the spec when there is none) with the same random reads, writes and resets, and
the test fails on the first differing read.
"""

load("@rules_cc//cc:defs.bzl", "cc_test")
load("@rules_verilator//verilator:defs.bzl", "verilator_cc_library")
load("@rules_verilog//verilog:defs.bzl", "verilog_library")

_TECH_LEF = "@orfs//flow:platforms/asap7/lef/asap7_tech_1x_201209.lef"
_CELL_LEF = "@orfs//flow:platforms/asap7/lef/asap7sc7p5t_28_R_1x_220121a.lef"

def regfile_sim_test(
        name,
        spec,
        module,
        rtl = [],
        rtl_module = None,
        ties = {},
        expect_mismatch = False,
        stdcells = ":asap7_stdcell"):
    """Simulates generate_regfile's netlist for `spec` against a reference.

    Args:
      name: the test.
      spec: the .regfile spec.
      module: the spec's `module`, the generated netlist's name.
      rtl: RTL sources holding rtl_module, for a module spec.
      rtl_module: the RTL module the spec replaces; None to be
        compared against a behavioural memory built from the spec.
      ties: RTL-only inputs and the constant each is tied to.
      expect_mismatch: a negative control, a spec known to be wrong: the
        test passes only if some read differs.
      stdcells: the stdcell_verilog target.
    """
    check = ""
    if rtl_module:
        check = "-check_ports " + " ".join(["$(location %s)" % r for r in rtl])
    native.genrule(
        name = name + "_gen_v",
        srcs = [spec, _TECH_LEF, _CELL_LEF] + rtl,
        outs = [name + "_gen.v"],
        cmd = """
grep -v '^[[:space:]]*memory[[:space:]]' $(location {spec}) > $(@D)/{name}.regfile
cat > $(@D)/{name}.tcl <<TCL
read_lef $(location {tech})
read_lef $(location {cell})
generate_regfile -spec $(@D)/{name}.regfile {check} -verilog $(@D)/{name}.raw.v
TCL
$(location @openroad//:openroad) -exit -no_init -no_splash $(@D)/{name}.tcl > $(@D)/{name}.log 2>&1 || {{ cat $(@D)/{name}.log; exit 1; }}
sed 's/^module {module}(/module {module}_gen(/' $(@D)/{name}.raw.v > $@
grep -q '^module {module}_gen(' $@ || {{ echo 'no module {module} in the netlist'; exit 1; }}
""".format(
            name = name,
            tech = _TECH_LEF,
            cell = _CELL_LEF,
            spec = spec,
            check = check,
            module = module,
        ),
        tools = ["@openroad"],
    )
    tie_args = " ".join(["--tie %s=%s" % (k, v) for k, v in ties.items()])
    native.genrule(
        name = name + "_tb",
        srcs = [spec],
        outs = [name + "_tb_top.v", name + "_config.cc"],
        cmd = " ".join([
            "$(execpath :gen_tb)",
            "--spec $(location %s)" % spec,
            "--gen-module %s_gen" % module,
            ("--rtl-module " + rtl_module) if rtl_module else "",
            tie_args,
            "--expect-mismatch" if expect_mismatch else "",
            "--tb $(location %s_tb_top.v)" % name,
            "--config $(location %s_config.cc)" % name,
        ]),
        tools = [":gen_tb"],
    )
    verilog_library(
        name = name + "_rtl",
        srcs = [
            name + "_tb_top.v",
            name + "_gen.v",
            stdcells + ".v",
            stdcells + "_empty.v",
        ] + rtl,
    )
    verilator_cc_library(
        name = name + "_vtb",
        module = name + "_rtl",
        module_top = "tb_top",
        trace_mode = "none",
        vopts = [
            "-Wno-fatal",
            "--x-initial",
            "0",
        ],
    )
    cc_test(
        name = name,
        size = "small",
        srcs = ["tb_main.cc", name + "_config.cc"],
        deps = [":" + name + "_vtb"],
    )
