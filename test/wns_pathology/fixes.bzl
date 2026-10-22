"""A proposed configuration change for a design the sweep flagged: the
design as ORFS has it, with its SDC edited, through global route, read
the way the sweep reads it. The verdict compares the two reads: the
pathology gone, and the reg2reg period where it was."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@orfs_designs//:designs.bzl", "DESIGNS")
load("//private:stages.bzl", "keep_modules")

def _orfs(labels):
    """DESIGNS' labels are ORFS's own, relative to its repository."""
    return ["@orfs" + x if x.startswith("//") else x for x in labels]

def _verilog(files):
    """The Verilog the DSL keeps (private/orfs_design.bzl)."""
    return _orfs([
        f
        for f in files
        if not ("$(" in f or "${" in f or "*" in f or "))" in f or "//." in f or f.endswith(":")) and
           not (f.endswith(":include") or "/include" in f.split(":")[-1])
    ])

def fix_arm(name, key, sdc_edits, user_arguments = [], user_sources = []):
    """<top>_<name>_grt with the edited SDC, and <name>, its read.

    Args:
      name: the arm, also its flow variant.
      key: the DESIGNS key of the design as ORFS has it.
      sdc_edits: sed expressions on the design's SDC, which must change
        it; none is the control, the SDC as it is, whose read must equal
        the sweep's: the arm then differs from @orfs's flow in nothing.
      user_arguments: what the design's own BUILD routes past the
        variables.yaml check, as the DSL does.
      user_sources: likewise for source-typed variables.

    Synthesised with slang, as @orfs's own flow of the design is: the
    sweep's read and the arm's differ in the SDC alone.
    """
    d = DESIGNS[key]
    top = d["name"]
    sources = {
        k: _orfs([x for x in v if not ("$(" in x or "${" in x or "//." in x or "*" in x or "))" in x or x.endswith(":"))])
        for k, v in d["sources"].items()
    }
    sources = {k: v for k, v in sources.items() if v}
    arguments = dict(d["arguments"])
    user_args = {v: arguments.pop(v) for v in user_arguments if v in arguments}
    user_srcs = {v: sources.pop(v) for v in user_sources if v in sources}
    if arguments.get("SYNTH_HIERARCHICAL") == "1" and "SYNTH_NUM_PARTITIONS" not in arguments:
        kept = keep_modules(arguments)
        arguments["SYNTH_NUM_PARTITIONS"] = str(len(kept)) if kept else "32"
    include = [
        "@orfs//" + i.strip().rstrip("/") + ":include"
        for i in arguments.get("VERILOG_INCLUDE_DIRS", "").replace("\t", " ").split(" ")
        if i.strip() and not i.strip().startswith("external/")
    ]
    native.genrule(
        name = name + "_sdc",
        srcs = sources["SDC_FILE"],
        outs = [name + ".sdc"],
        cmd = "sed " + " ".join(["-e '%s'" % e.replace("$", "$$") for e in sdc_edits]) + " $< > $@ && ! cmp -s $< $@" if sdc_edits else "cp $< $@",
        tags = ["manual"],
    )
    orfs_flow(
        name = top,
        arguments = arguments,
        last_stage = "grt",
        pdk = "@orfs//flow:" + d["platform"],
        sources = sources | {"SDC_FILE": [":%s_sdc" % name]},
        stage_data = {"synth": include} if include else {},
        tags = ["manual"],
        user_arguments = user_args,
        user_sources = user_srcs,
        variant = name,
        verilog_files = _verilog(d["verilog_files"]),
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
