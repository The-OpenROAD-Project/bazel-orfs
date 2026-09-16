"""The trial-route ladder, as a macro.

Part A asks two questions of every design, and both are answered by the
same probe run with different arguments:

  * A1, the information gap -- does `estimate_parasitics -global_routing`
    rank endpoints closer to the routed truth than
    `estimate_parasitics -placement` does? If it does not, no fork/join
    can help, because the repair would be handed the same list.
  * A2, the cost/information curve -- how cheap can the throwaway route
    be before the information stops being better? `-infinite_cap` is the
    cheapest possible route and also the one that cannot see a detour,
    and pre-route-pessimism found contention is the only thing that makes
    placement and global route disagree at all. So the cheapest rung may
    measure the same thing the placement estimate already measured, at
    the cost of a route.

Every rung is one `orfs_run` over the *same* CTS ODB, so the arms differ
in the route and in nothing else -- no re-placement, no re-synthesis, no
seed. The reference is the same probe on the final stage reading its
extracted SPEF.

Every target here is manual: each one loads a stage ODB and routes it.
"""

load("//:openroad.bzl", "orfs_run")

# The ladder, cheapest first. The arguments are passed to `global_route`
# verbatim.
#
# `-allow_congestion` is not a tuning choice on the cheap rungs, it is
# required: grt::have_routes -- the gate estimate_parasitics itself uses
# -- rejects a congested route without it, and the probe would fail with
# EST-5 as though no route had happened.
#
# `-congestion_iterations` is checked positive, so 1 is the floor, not 0.
# ORFS itself passes 30; the tool's default is 50.
TRIAL_ROUTE_RUNGS = {
    "cheapest": "-allow_congestion -congestion_iterations 1 -infinite_cap" +
                " -skip_large_fanout_nets 100",
    "no_overflow_loop": "-allow_congestion -congestion_iterations 1",
    "few": "-allow_congestion -congestion_iterations 5",
    "stock": "-congestion_iterations 30",
}

def orfs_relative(labels):
    """Re-root an ORFS design's own labels into @orfs.

    `@orfs_designs`' DESIGNS entries carry labels as ORFS writes them --
    `//flow/designs/asap7/gcd:constraint.sdc` -- because the design BUILD
    files that consume them live inside @orfs, where `//` means @orfs. A
    probe declared here is in bazel-orfs, where the same string names a
    package that does not exist, and the failure reads as "no such
    package 'flow/designs/asap7/gcd'" rather than as a repo mix-up.

    Starlark forbids recursion, so the shape is spelled out rather than
    walked: a sources dict is variable -> list of labels, and nothing
    deeper exists.

    Args:
        labels: a dict of variable -> label string or list of label
            strings, as a DESIGNS entry's `sources` carries them.

    Returns:
        The same shape, with bare `//` labels prefixed with `@orfs`.
    """
    out = {}
    for var, value in labels.items():
        if type(value) == "list":
            out[var] = [
                "@orfs" + label if label.startswith("//") else label
                for label in value
            ]
        elif value.startswith("//"):
            out[var] = "@orfs" + value
        else:
            out[var] = value
    return out

def ri_probe(
        name,
        design,
        src,
        parasitics,
        grt_args = None,
        arguments = {},
        user_arguments = {},
        sources = {},
        user_sources = {},
        visibility = None):
    """One instrument's opinion of one stage ODB.

    Args:
        name: target name; the JSON is `<name>.json`.
        design: the parsed DESIGNS entry, so a probe can never disagree
            with the design it measures.
        src: the flow stage target whose ODB is read.
        parasitics: placement, global_routing or spef.
        grt_args: `global_route` arguments, for the global_routing mode.
        arguments: ORFS variables, defaulting to the design's own.
        user_arguments: project-specific variables, exempt from the
            variables.yaml spell-check.
        sources: source-typed ORFS variables, defaulting to the design's.
        user_sources: source-typed project hooks; the staging preamble is
            added to these.
        visibility: forwarded.
    """
    out = name + ".json"
    probe_args = {
        "OUTPUT_JSON": "$(location {})".format(out),
        "RI_ARM": name,
        "RI_PARASITICS": parasitics,
    }
    if grt_args != None:
        probe_args["RI_GRT_ARGS"] = grt_args

    orfs_run(
        name = name,
        src = src,
        outs = [out],
        arguments = arguments or design["arguments"],
        script = "//test/repair_information:endpoint_slacks.tcl",
        sources = orfs_relative(sources or design["sources"]),
        tags = ["manual"],
        user_arguments = user_arguments | probe_args,
        user_sources = user_sources | {
            "STAGE_SRC_TCL": ["//test/pre_route_pessimism:stage_src.tcl"],
        },
        variant = name,
        visibility = visibility,
    )

def ri_ladder(
        name,
        design,
        design_dir,
        arguments = {},
        user_arguments = {},
        sources = {},
        user_sources = {},
        rungs = TRIAL_ROUTE_RUNGS):
    """The whole Part A ladder for one design.

    Produces `<name>_placement`, `<name>_gr_<rung>` for each rung -- all
    on the CTS ODB, which is where the flow's own pre-route repair last
    runs on a placement estimate -- and `<name>_spef` on the final ODB,
    which is the reference every other rung is scored against.

    The CTS stage rather than the place stage on purpose: the clock tree
    exists there, so the probe and the reference both read a propagated
    clock, and a rank difference between them is about the wires rather
    than about the clock.

    Args:
        name: prefix for every target.
        design: the parsed DESIGNS entry.
        design_dir: the design's directory under `@orfs//flow/designs/asap7`.
        arguments: override the design's ORFS variables.
        user_arguments: project-specific variables.
        sources: override the design's source-typed variables.
        user_sources: source-typed project hooks.
        rungs: rung name -> `global_route` arguments.
    """
    common = {
        "arguments": arguments,
        "design": design,
        "sources": sources,
        "user_arguments": user_arguments,
        "user_sources": user_sources,
    }
    top = design["name"]
    cts = "@orfs//flow/designs/asap7/{}:{}_cts".format(design_dir, top)
    final = "@orfs//flow/designs/asap7/{}:{}_final".format(design_dir, top)

    ri_probe(
        name = "{}_placement".format(name),
        parasitics = "placement",
        src = cts,
        **common
    )

    for rung, grt_args in rungs.items():
        ri_probe(
            name = "{}_gr_{}".format(name, rung),
            grt_args = grt_args,
            parasitics = "global_routing",
            src = cts,
            **common
        )

    ri_probe(
        name = "{}_spef".format(name),
        parasitics = "spef",
        src = final,
        **common
    )
