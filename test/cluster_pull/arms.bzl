"""Arms of the cluster-pull study (issue #1263): ORFS designs to global
route with rtl_macro_placer's clusters kept (RTLMP_KEEP_CLUSTERING) and
global placement pulling them together (patch 0127)."""

load("@orfs_designs//:designs.bzl", "DESIGNS")
load("//:openroad.bzl", "orfs_flow")
load("//private:stages.bzl", "keep_modules")  # buildifier: disable=bzl-visibility

def _orfs(label):
    """ORFS's labels are relative to its own repository."""
    return "@orfs" + label if label.startswith("//") else label

def cluster_pull_arms(key, arms):
    """One flow per arm of an ORFS design, from ORFS's arguments and its
    BLOCKS' own abstracts, to global route. The first arm synthesizes;
    the others take its synthesis.

    Args:
      key: the DESIGNS key, e.g. "asap7/aes-block".
      arms: dict of arm name to GLOBAL_PLACEMENT_ARGS, None for an arm
        that keeps the clusters and does not pull them; or to a dict
        {"gpl": <the same>, "arguments": {...}} for an arm that also
        sets flow variables (the macro placer's clustering, say).
    """
    design = DESIGNS[key]
    name = design["name"]
    pkg = "@orfs//flow/designs/" + key
    sources = {
        var: [_orfs(label) for label in labels]
        for var, labels in design["sources"].items()
    }

    # As orfs_design() does: unresolved Make references are not files.
    verilog_files = [
        _orfs(f)
        for f in design["verilog_files"]
        if "$(" not in f and "${" not in f and "//." not in f and not f.endswith(":")
    ]

    macros = [
        "%s:%s_generate_abstract" % (pkg, DESIGNS["%s_%s" % (key, block)]["name"])
        for block in design.get("blocks", [])
    ]
    stock = design["arguments"].get("GLOBAL_PLACEMENT_ARGS", "")
    first = None
    for arm, spec in arms.items():
        extra = {}
        gpl_args = spec
        if type(spec) == "dict":
            gpl_args = spec.get("gpl")
            extra = spec.get("arguments", {})
        arguments = dict(design["arguments"]) | extra

        # The partition count orfs_design() gives ORFS's own flow, so the
        # first arm's synthesis is ORFS's.
        if arguments.get("SYNTH_HIERARCHICAL") == "1" and "SYNTH_NUM_PARTITIONS" not in arguments:
            kept = keep_modules(arguments)
            arguments["SYNTH_NUM_PARTITIONS"] = str(len(kept)) if kept else "32"
        arguments["RTLMP_KEEP_CLUSTERING"] = "1"
        if gpl_args:
            arguments["GLOBAL_PLACEMENT_ARGS"] = (stock + " " + gpl_args).strip()
        orfs_flow(
            name = name,
            arguments = arguments,
            last_stage = "grt",
            macros = macros,
            pdk = "@orfs//flow:" + design["platform"],
            previous_stage = {"floorplan": ":%s_%s_synth" % (name, first)} if first else {},
            sources = sources,
            tags = ["manual"],
            variant = arm,
            verilog_files = verilog_files,
        )
        first = first or arm

def fine_arms(arms, sizes):
    """"off" and "w4" again at explicit cluster sizes, as "<arm>_fine".

    Args:
      arms: the arm dict, for the "off" and "w4" GLOBAL_PLACEMENT_ARGS.
      sizes: (min_inst, max_inst) for the macro placer's std-cell clusters.

    Returns:
      dict of arm name to {"gpl": ..., "arguments": ...}.
    """
    return {
        arm + "_fine": {
            "arguments": {
                "RTLMP_MAX_INST": sizes[1],
                "RTLMP_MAX_MACRO": "4",
                "RTLMP_MIN_INST": sizes[0],
                "RTLMP_MIN_MACRO": "1",
            },
            "gpl": arms[arm],
        }
        for arm in ["off", "w4"]
    }
