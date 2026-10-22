"""A proposed configuration change for a design the sweep flagged: the
design as ORFS has it, with its SDC edited, through global route, read
the way the sweep reads it. The verdict compares the two reads: the
pathology gone, and the reg2reg period where it was."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@orfs_designs//:designs.bzl", "DESIGNS")

def _orfs(labels):
    """DESIGNS' labels are ORFS's own, relative to its repository."""
    return ["@orfs" + x if x.startswith("//") else x for x in labels]

def fix_arm(name, key, sdc_edits):
    """<top>_<name>_grt with the edited SDC, and <name>, its read.

    Args:
      name: the arm, also its flow variant.
      key: the DESIGNS key of the design as ORFS has it.
      sdc_edits: sed expressions on the design's SDC, which must change
        it; none is the control, the SDC as it is, whose read must equal
        the sweep's: the arm then differs from @orfs's flow in nothing.

    Synthesised with slang, as @orfs's own flow of the design is: the
    sweep's read and the arm's differ in the SDC alone.
    """
    d = DESIGNS[key]
    top = d["name"]
    sources = {k: _orfs(v) for k, v in d["sources"].items()}
    native.genrule(
        name = name + "_sdc",
        srcs = sources["SDC_FILE"],
        outs = [name + ".sdc"],
        cmd = "sed " + " ".join(["-e '%s'" % e.replace("$", "$$") for e in sdc_edits]) + " $< > $@ && ! cmp -s $< $@" if sdc_edits else "cp $< $@",
        tags = ["manual"],
    )
    orfs_flow(
        name = top,
        arguments = d["arguments"],
        last_stage = "grt",
        pdk = "@orfs//flow:" + d["platform"],
        sources = sources | {"SDC_FILE": [":%s_sdc" % name]},
        tags = ["manual"],
        variant = name,
        verilog_files = _orfs([f for f in d["verilog_files"] if "$(" not in f]),
    )
    orfs_run(
        name = name,
        src = ":%s_%s_grt" % (top, name),
        outs = [name + ".tsv"],
        script = ":read.tcl",
        tags = ["manual"],
        user_arguments = {"OUT": "$(location %s.tsv)" % name},
        user_sources = {"FLOOR_TCL": ["//tools/headroom:report_floor_cycles.tcl"]},
        variant = name,
    )
