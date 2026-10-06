"""A structured_gen register file against yosys's synthesis of the RTL it replaces."""

load("//test/lec:lec.bzl", "lec_test")

ASAP7_LEFS = [
    "@orfs//flow:platforms/asap7/lef/asap7_tech_1x_201209.lef",
    "@orfs//flow:platforms/asap7/lef/asap7sc7p5t_28_R_1x_220121a.lef",
]

LIBERTY = [
    "@orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_SEQ_RVT_FF_nldm_220123.lib",
    ":asap7_simple.lib",
    ":asap7_ao.lib",
    ":asap7_invbuf.lib",
]

# rename -wire before mapping names each flop after the register bit it
# drives (mem_3[1]$_DFFE_PP_); the sed drops yosys's type suffix.
_YOSYS_SCRIPT = """read_verilog -sv {sv}
hierarchy -top {module}
synth -flatten -top {module}
rename -wire t:$$_DFF*
dfflibmap -liberty {seq}
abc -liberty {simple} -liberty {ao} -liberty {invbuf}
opt_clean -purge
write_verilog -noattr {raw}
"""

def regfile_lec(name, module, args, expect_equivalent = True, spec_args = ""):
    """The fixture, its gold and gate netlists, and a manual lec_test.

    Args:
        name: the test; <name>_rtl, _gold and _gate are its steps.
        module: the RTL module's name.
        args: lec_fixture.py's shape and size arguments.
        expect_equivalent: False for a case that must be caught.
        spec_args: extra lec_fixture.py arguments for the spec alone.
    """
    native.genrule(
        name = name + "_rtl",
        outs = [name + ".sv", name + ".spec"],
        cmd = "$(location :lec_fixture) --out $(RULEDIR)/{n} --module {m} {a} {s}".format(
            n = name,
            m = module,
            a = args,
            s = spec_args,
        ),
        tools = [":lec_fixture"],
    )

    # The RTL mapped to the cells the generator uses, every flop named
    # after the RTL register bit it holds: kepler-formal pairs sequential
    # instances by name.
    script = _YOSYS_SCRIPT.format(
        sv = "$(location {}.sv)".format(name),
        module = module,
        seq = "$(location {})".format(LIBERTY[0]),
        simple = "$(location :asap7_simple.lib)",
        ao = "$(location :asap7_ao.lib)",
        invbuf = "$(location :asap7_invbuf.lib)",
        raw = "$(RULEDIR)/{}_raw.v".format(name),
    )
    native.genrule(
        name = name + "_gold",
        srcs = [name + ".sv"] + LIBERTY,
        outs = [name + "_gold.v"],
        cmd = " && ".join([
            "printf '%s' '{}' > $(RULEDIR)/{}.ys".format(script, name),
            "$(location @yosys//:yosys) -q -s $(RULEDIR)/{}.ys".format(name),
            "sed -E 's/[$$]_[A-Z0-9_]+_ +[(]/ (/' $(RULEDIR)/{}_raw.v > $@".format(name),
        ]),
        tools = ["@yosys//:yosys"],
    )
    native.genrule(
        name = name + "_gate",
        srcs = [name + ".spec"] + ASAP7_LEFS,
        outs = [name + "_gate.v"],
        cmd = "$(location //tools/structured_gen:structured_gen) --spec $(location {n}.spec) --lef $(location {t}) --lef $(location {c}) --verilog $@ > /dev/null".format(
            n = name,
            t = ASAP7_LEFS[0],
            c = ASAP7_LEFS[1],
        ),
        tools = ["//tools/structured_gen:structured_gen"],
    )
    lec_test(
        name = name,
        size = "small",
        allow_boundary_mismatch = not expect_equivalent,
        expect_equivalent = expect_equivalent,
        expect_problem_size = expect_equivalent,
        gate_verilog_files = [name + "_gate.v"],
        gold_verilog_files = [name + "_gold.v"],
        liberty_files = LIBERTY,
    )
