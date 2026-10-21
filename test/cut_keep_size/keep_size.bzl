"""A design as ORFS has it, against the keep list its size rule decides
once a macro costs nothing towards its parent's size (keep_probe.py).

Both through global route at a clock repair cannot meet, read as
test/cut_riscv32i reads riscv32i: every reg2reg endpoint's period, each
group's worst path and the hold buffers.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@orfs_designs//:designs.bzl", "DESIGNS")

def _orfs(labels):
    """DESIGNS' labels are ORFS's own, relative to its repository."""
    return ["@orfs" + x if x.startswith("//") else x for x in labels]

# keep lists replace the size rule: only the named modules are kept
ONLY = {"SYNTH_MINIMUM_KEEP_SIZE": "1000000000"}

def keep_size_arms(name, key, top, zero, sdc_edits, frontend = ""):
    """<name>_today and <name>_zero, each to global route, and their reports.

    Args:
      name: the arms' variant prefix.
      key: the DESIGNS key of the design as ORFS has it.
      top: its top module, the flow's name.
      zero: the modules the size rule keeps with macros at cost 0.
      sdc_edits: sed expressions that set the clock, each checked to apply.
      frontend: the design's own SYNTH_HDL_FRONTEND, "" for yosys's own.
    """
    d = DESIGNS[key]
    sources = {k: _orfs(v) for k, v in d["sources"].items()}
    native.genrule(
        name = name + "_sdc",
        srcs = sources["SDC_FILE"],
        outs = [name + ".sdc"],
        cmd = "sed " + " ".join(["-e '%s'" % e.replace("$", "$$") for e in sdc_edits]) + " $< > $@ && ! cmp -s $< $@",
        tags = ["manual"],
    )
    base = d["arguments"] | {"SYNTH_HDL_FRONTEND": frontend}
    for arm, extra in [
        ("today", {}),
        ("zero", ONLY | {"SYNTH_KEEP_MODULES": " ".join(zero)}),
    ]:
        variant = "%s_%s" % (name, arm)
        orfs_flow(
            name = top,
            arguments = base | extra,
            last_stage = "grt",
            pdk = "@orfs//flow:" + d["platform"],
            sources = sources | {"SDC_FILE": [":%s_sdc" % name]},
            tags = ["manual"],
            variant = variant,
            verilog_files = _orfs([f for f in d["verilog_files"] if "$(" not in f]),
            yosys_frontend_reason = None if frontend == "slang" else "measured as ORFS runs %s, with yosys's own frontend" % key,
        )
        for what, script, out, var in [
            ("endpoints", "//test/cut_riscv32i:endpoints.tcl", "tsv", "ENDPOINTS_OUT"),
            ("report", "//test/cut_riscv32i:groups.tcl", "txt", "REPORT_OUT"),
        ]:
            orfs_run(
                name = "%s_%s_%s" % (top, variant, what),
                src = ":%s_%s_grt" % (top, variant),
                outs = ["%s_%s.%s" % (variant, what, out)],
                script = script,
                tags = ["manual"],
                user_arguments = {var: "$(location %s_%s.%s)" % (variant, what, out)},
                variant = variant,
            )
