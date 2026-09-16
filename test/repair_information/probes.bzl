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

load("//:openroad.bzl", "orfs_flow", "orfs_run")

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
        probe_env = {},
        arguments = {},
        user_arguments = {},
        sources = {},
        qualify_sources = True,
        extra_sources = {},
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
        probe_env: extra RI_* variables read only by the probe script --
            the contention knobs, which ORFS has never heard of and
            which therefore take the user_arguments hatch.
        arguments: ORFS variables, defaulting to the design's own.
        user_arguments: project-specific variables, exempt from the
            variables.yaml spell-check.
        sources: source-typed ORFS variables, defaulting to the
            design's. Re-rooted into @orfs, since that is how a DESIGNS
            entry spells them.
        qualify_sources: whether `sources` needs re-rooting into @orfs.
        extra_sources: source-typed ORFS variables owned by *this*
            package, merged after that re-rooting -- a label of ours put
            through it would come back pointing at a package inside
            @orfs that does not exist.
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
    probe_args.update(probe_env)

    orfs_run(
        name = name,
        src = src,
        outs = [out],
        arguments = arguments or design["arguments"],
        script = "//test/repair_information:endpoint_slacks.tcl",
        sources = (
            orfs_relative(sources or design["sources"]) if qualify_sources else (sources or design["sources"])
        ) | extra_sources,
        tags = ["manual"],
        user_arguments = user_arguments | probe_args,
        user_sources = user_sources | {
            "STAGE_SRC_TCL": ["//test/pre_route_pessimism:stage_src.tcl"],
        },
        variant = name,
        visibility = visibility,
    )

# The contention axis. asap7's platform default is 0.25, so the sweep
# straddles it: 0.0 is every track the stack has, 0.95 leaves the router
# almost nothing.
#
# Why this is the right knob. `estimate_parasitics -placement` prices
# every net from the one resistance and capacitance `set_wire_rc`
# installed -- on asap7 an absolute constant standing in for a
# lower-middle layer -- so the placement estimate can only be wrong to
# the extent that routing lands on layers whose real RC is not that
# constant. Scarcity is what pushes it there: with room to route, global
# route takes the direct path on the layer the constant describes and
# confirms what placement already said, which is the 2.7-3.6% agreement
# the uncontended designs measured. Nothing about the netlist has to
# change to open the gap -- only the supply.
LAYER_ADJUSTMENTS = [
    "0.0",
    "0.25",
    "0.5",
    "0.7",
    "0.8",
    "0.9",
    "0.95",
]

def ri_contention(
        name,
        design,
        design_dir = None,
        src = None,
        qualify_sources = True,
        adjustments = LAYER_ADJUSTMENTS,
        max_layers = [],
        arguments = {},
        user_arguments = {},
        sources = {},
        user_sources = {},
        visibility = None):
    """Sweep routing supply on one CTS ODB, with the route as the only variable.

    The placement rung of `ri_ladder` is the control and does not need
    repeating: `estimate_parasitics -placement` never looks at routing
    supply, so its period is flat across this whole sweep by
    construction. That flatness is the plot's baseline, and it is the
    reason the sweep costs a route each and nothing else.

    `-allow_congestion` is mandatory here rather than merely advisable:
    at a 0.9 derate the route certainly overflows, and without the flag
    grt::have_routes rejects it and the probe dies at EST-5 having
    measured nothing.

    Args:
        name: prefix for every target.
        design: the parsed DESIGNS entry.
        design_dir: the design's directory under
            `@orfs//flow/designs/asap7`, used to derive the CTS label.
        src: the CTS stage target, overriding `design_dir`.
        qualify_sources: re-root the design's source labels into @orfs.
        adjustments: ROUTING_LAYER_ADJUSTMENT values to sweep.
        max_layers: MAX_ROUTING_LAYER values to sweep, at the platform's
            own derate -- the other way to force the mix, by taking the
            fast top layers away rather than making every layer scarce.
        arguments: override the design's ORFS variables.
        user_arguments: project-specific variables.
        sources: override the design's source-typed variables.
        user_sources: source-typed project hooks.
        visibility: forwarded.
    """
    common = {
        "arguments": arguments,
        "design": design,
        "grt_args": "-allow_congestion -congestion_iterations 30",
        "parasitics": "global_routing",
        "qualify_sources": qualify_sources,
        "sources": sources,
        "src": src if src != None else "@orfs//flow/designs/asap7/{}:{}_cts".format(
            design_dir,
            design["name"],
        ),
        "user_arguments": user_arguments,
        "user_sources": user_sources,
        "visibility": visibility,
    }

    for adj in adjustments:
        ri_probe(
            name = "{}_adj{}".format(name, adj.replace(".", "")),
            probe_env = {"RI_LAYER_ADJUSTMENT": adj},
            **common
        )

    for layer in max_layers:
        ri_probe(
            name = "{}_max{}".format(name, layer),
            probe_env = {"RI_MAX_ROUTING_LAYER": layer},
            **common
        )

def ri_ladder(
        name,
        design,
        design_dir = None,
        cts = None,
        final = None,
        qualify_sources = True,
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
        design_dir: the design's directory under
            `@orfs//flow/designs/asap7`, from which the stage labels are
            derived. Omit it and pass `cts`/`final` instead for a design
            that lives somewhere else.
        cts: the CTS stage target, overriding `design_dir`.
        final: the final stage target, overriding `design_dir`.
        qualify_sources: whether the design's source labels need
            re-rooting into @orfs. True for an ORFS design, False for one
            declared in this repo, whose labels are already correct.
        arguments: override the design's ORFS variables.
        user_arguments: project-specific variables.
        sources: override the design's source-typed variables.
        user_sources: source-typed project hooks.
        rungs: rung name -> `global_route` arguments.
    """
    top = design["name"]
    common = {
        "arguments": arguments,
        "design": design,
        "qualify_sources": qualify_sources,
        "sources": sources,
        "user_arguments": user_arguments,
        "user_sources": user_sources,
    }
    if cts == None:
        cts = "@orfs//flow/designs/asap7/{}:{}_cts".format(design_dir, top)
    if final == None:
        final = "@orfs//flow/designs/asap7/{}:{}_final".format(design_dir, top)

    ri_probe(
        name = "{}_placement".format(name),
        parasitics = "placement",
        src = cts,
        **common
    )

    # The ceiling. Same ODB, same placement estimate, no wire RC at all,
    # so the difference from the rung above is the whole wire-delay
    # contribution to the achieved period -- and therefore the most any
    # parasitics model can be wrong by. A design whose gap here is 1% is
    # a design where this study has nothing to find, whatever the
    # congestion does.
    ri_probe(
        name = "{}_zero_rc".format(name),
        parasitics = "placement",
        src = cts,
        extra_sources = {
            "LAYER_PARASITICS_FILE": ["//test/repair_information:zero_rc.tcl"],
        },
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

# Utilization values for the wire-share sweep. The platform's own value
# for a design is typically 40-70; below that the core grows and the nets
# with it.
#
# Why utilization and not congestion. The zero-RC rung showed signal wire
# delay is 2-12% of the achieved period on the stock small designs, and
# that share is a ceiling: no parasitics model can be wrong by more than
# the delay it models, so a design at 2% cannot show this effect however
# scarce its routing supply is made -- which is exactly what the flat gcd
# contention sweep measured. The two knobs also fight: scarcer supply
# forces detours, but a denser core shortens every net, and wire share
# falls with it.
#
# A large core at low utilization buys the length directly. It is not a
# realistic floorplan, and it is not meant to be -- it is the regime
# where the question has an answer, reached on a design small enough to
# re-run in a minute.
WIRE_SHARE_UTILIZATIONS = [
    "40",
    "20",
    "10",
    "5",
    "2",
]

def ri_stretch(
        name,
        design,
        design_dir,
        utilizations = WIRE_SHARE_UTILIZATIONS,
        adjustments = ["0.25"],
        arguments = {},
        user_arguments = {},
        sources = {},
        user_sources = {},
        verilog_files = None,
        visibility = None):
    """Re-floorplan one design at a ladder of utilizations, and probe each.

    Each rung synthesizes for itself. Sharing one synth through
    `previous_stage` looks obviously right and does not compose with a
    per-rung `variant`: RESULTS_DIR is
    results/<platform>/<top>/<variant>, the donor's 1_synth.odb lands in
    *its* variant directory, and the rung's floorplan then fails with
    "ORD-0007 .../u20/1_synth.odb does not exist". The variant cannot be
    dropped either -- without it every rung writes the same
    2_floorplan.odb and bazel rejects the package outright. So the ladder
    pays for a synth per rung, which on a small design is seconds, and
    the netlists are identical regardless because nothing in synthesis
    reads CORE_UTILIZATION.

    Each rung gets the three instruments that bound the question: the
    no-wire floor, the placement estimate, and a stock-effort global
    route. The SPEF reference is deliberately absent -- these floorplans
    are not designs anyone would route, and the question here is only
    where the placement estimate and global route part company.

    Args:
        name: prefix for every target.
        design: the parsed DESIGNS entry.
        design_dir: unused; kept so the ladder reads like its siblings.
        utilizations: CORE_UTILIZATION values, as strings.
        adjustments: ROUTING_LAYER_ADJUSTMENT values to cross with them.
        arguments: override the design's ORFS variables.
        user_arguments: project-specific variables.
        sources: override the design's source-typed variables.
        user_sources: source-typed project hooks.
        verilog_files: forwarded; defaults to the design's own.
        visibility: forwarded.
    """
    top = design["name"]
    design_args = arguments or design["arguments"]
    design_sources = orfs_relative(sources or design["sources"])

    for util in utilizations:
        variant = "u{}".format(util)
        flow = "{}_{}".format(name, variant)

        # CORE_UTILIZATION and CORE_ASPECT_RATIO/CORE_MARGIN are the
        # floorplan's shape. A design that names a DIE_AREA or CORE_AREA
        # instead would ignore utilization entirely, and the rung would
        # silently be a duplicate of its neighbour -- hence the ladder is
        # only applied to designs whose config sets utilization.
        # The variant, not just the target name, has to differ per rung:
        # RESULTS_DIR is results/<platform>/<top>/<variant>, so five
        # rungs sharing the default "base" all write the same
        # 2_floorplan.json and bazel rejects the package with
        # "generated by these conflicting actions". The variant is also
        # what puts the utilization into the target name.
        orfs_flow(
            name = name,
            variant = variant,
            arguments = design_args | {"CORE_UTILIZATION": util},
            last_stage = "cts",
            sources = design_sources,
            tags = ["manual"],
            top = top,
            user_arguments = user_arguments,
            verilog_files = verilog_files if verilog_files != None else orfs_relative(
                {"v": design["verilog_files"]},
            )["v"],
            visibility = visibility,
        )

        probe_common = {
            "arguments": design_args | {"CORE_UTILIZATION": util},
            "design": design,
            "sources": design_sources,
            "src": ":{}_cts".format(flow),
            "user_arguments": user_arguments,
            "user_sources": user_sources,
            "visibility": visibility,
        }

        ri_probe(
            name = "{}_placement".format(flow),
            parasitics = "placement",
            **probe_common
        )
        ri_probe(
            name = "{}_zero_rc".format(flow),
            extra_sources = {
                "LAYER_PARASITICS_FILE": ["//test/repair_information:zero_rc.tcl"],
            },
            parasitics = "placement",
            **probe_common
        )
        for adj in adjustments:
            ri_probe(
                name = "{}_gr_adj{}".format(flow, adj.replace(".", "")),
                grt_args = "-allow_congestion -congestion_iterations 30",
                parasitics = "global_routing",
                probe_env = {"RI_LAYER_ADJUSTMENT": adj},
                **probe_common
            )

# The shape recipe, taken from pre-route-pessimism's own arms rather than
# re-derived. Three knobs that only work together:
#
#   * CORE_UTILIZATION buys die area, but PLACE_DENSITY has to follow it
#     down or global placement packs every cell into a corner of the
#     larger die and hands back short wires. The gcd ladder in this study
#     made exactly that mistake -- a 20x core for 28% more wire.
#   * ROUTING_LAYER_ADJUSTMENT buys back the contention that spreading
#     costs: routing demand grows as the square root of die area while
#     track supply grows linearly, so a design spread out for long wires
#     is *less* contended, not more.
#   * WIREBOUND_GROUPS sets the netlist size, and therefore how long the
#     scattered inter-group nets are in absolute microns. Break-even for
#     climbing off M2 is ~8um of net, and wirebound at its default size
#     routes 11.6um nets with zero demand on M8/M9 -- so size is the
#     knob that decides whether the top of the stack is worth reaching
#     at all.
WIREBOUND_SHAPES = {
    "u55": {
        "CORE_UTILIZATION": "55",
        "PLACE_DENSITY": "0.60",
    },
    "u25": {
        "CORE_UTILIZATION": "25",
        "PLACE_DENSITY": "0.30",
    },
    "u12": {
        "CORE_UTILIZATION": "12",
        "PLACE_DENSITY": "0.16",
    },
    "u12_tight": {
        "CORE_UTILIZATION": "12",
        "PLACE_DENSITY": "0.16",
        "ROUTING_LAYER_ADJUSTMENT": "0.50",
    },
    "u55_derated": {
        "CORE_UTILIZATION": "55",
        "PLACE_DENSITY": "0.60",
        "ROUTING_LAYER_ADJUSTMENT": "0.65",
    },
    "u80_dense": {
        "CORE_UTILIZATION": "80",
        "PLACE_DENSITY": "0.85",
    },
}

# The derate arms, at flow level so placement and CTS see the congestion
# too. The probe-level sweep on the u55 ODB peaked at 17.8% of min_period
# with a 0.75 derate and *fell* to 7.5% by 0.90 while top-metal demand
# kept rising to 11% -- the single set_wire_rc constant fails hardest on
# a mixed stack, not a top-heavy one, because a uniformly high mix is
# merely a miscalibrated constant rather than an unrepresentative one.
#
# Flow level roughly doubles the effect at the same derate (0.65 gives
# 13.2% here against 6.7% at probe level), because a congestion-aware
# global placement spreads the cells the router is about to struggle
# with, and the placement estimate then prices a different design.
WIREBOUND_DERATED_SHAPES = {
    "u55_d75": {
        "CORE_UTILIZATION": "55",
        "PLACE_DENSITY": "0.60",
        "ROUTING_LAYER_ADJUSTMENT": "0.75",
    },
    "u55_d85": {
        "CORE_UTILIZATION": "55",
        "PLACE_DENSITY": "0.60",
        "ROUTING_LAYER_ADJUSTMENT": "0.85",
    },
    "u80_d65": {
        "CORE_UTILIZATION": "80",
        "PLACE_DENSITY": "0.85",
        "ROUTING_LAYER_ADJUSTMENT": "0.65",
    },
    "u80_d75": {
        "CORE_UTILIZATION": "80",
        "PLACE_DENSITY": "0.85",
        "ROUTING_LAYER_ADJUSTMENT": "0.75",
    },
}

def ri_shapes(
        name,
        design,
        shapes,
        groups,
        last_stage = "cts",
        rc_cal = False,
        defines_var = "VERILOG_DEFINES",
        define_name = "WIREBOUND_GROUPS",
        arguments = {},
        user_arguments = {},
        sources = {},
        user_sources = {},
        verilog_files = None,
        qualify_sources = True,
        visibility = None):
    """One flow per (shape, size), each probed by the three instruments.

    Each arm gets its own `variant`, which is what keeps five floorplans
    from writing the same 2_floorplan.odb, and therefore synthesizes for
    itself -- a shared `previous_stage` resolves against the donor's
    variant directory and fails with ORD-0007. Since the size knob
    changes the netlist anyway, most arms could not share a synth even
    in principle.

    Args:
        name: prefix for every target.
        design: the parsed DESIGNS entry.
        shapes: shape name -> ORFS argument overrides.
        groups: sizes to cross with the shapes.
        rc_cal: also declare the calibrated-estimate probe, which needs
            a checked-in rc_cal_<shape>.tcl produced by rc_calibrate.py.
        last_stage: how far each arm's flow runs. "final" also declares
            the SPEF probe, which is the only instrument that can say
            which of the other two was right -- and the only one that
            costs a detailed route.
        defines_var: the ORFS variable carrying Verilog defines.
        define_name: the define that sets the design's size.
        arguments: the design's ORFS variables.
        user_arguments: project-specific variables.
        sources: source-typed ORFS variables.
        user_sources: source-typed project hooks.
        verilog_files: forwarded.
        qualify_sources: re-root source labels into @orfs.
        visibility: forwarded.
    """
    design_sources = orfs_relative(sources or design["sources"]) if qualify_sources else (sources or design["sources"])

    for shape_name, shape in shapes.items():
        for size in groups:
            variant = "{}_g{}".format(shape_name, size)
            flow = "{}_{}".format(name, variant)
            args = (arguments or design["arguments"]) | shape | {
                defines_var: "-D {}={}".format(define_name, size),
            }

            orfs_flow(
                name = name,
                variant = variant,
                arguments = args,
                last_stage = last_stage,
                sources = design_sources,
                tags = ["manual"],
                top = design["name"],
                user_arguments = user_arguments,
                verilog_files = verilog_files if verilog_files != None else design["verilog_files"],
                visibility = visibility,
            )

            probe_common = {
                "arguments": args,
                "design": design,
                "qualify_sources": False,
                "sources": design_sources,
                "src": ":{}_cts".format(flow),
                "user_arguments": user_arguments,
                "user_sources": user_sources,
                "visibility": visibility,
            }

            ri_probe(
                name = "{}_placement".format(flow),
                parasitics = "placement",
                **probe_common
            )
            ri_probe(
                name = "{}_rc_cal".format(flow),
                extra_sources = {
                    "LAYER_PARASITICS_FILE": [
                        "//test/repair_information:rc_cal_{}.tcl".format(shape_name),
                    ],
                } if rc_cal else {},
                parasitics = "placement",
                **probe_common
            ) if rc_cal else None

            ri_probe(
                name = "{}_zero_rc".format(flow),
                extra_sources = {
                    "LAYER_PARASITICS_FILE": ["//test/repair_information:zero_rc.tcl"],
                },
                parasitics = "placement",
                **probe_common
            )
            ri_probe(
                name = "{}_gr".format(flow),
                grt_args = "-allow_congestion -congestion_iterations 30",
                parasitics = "global_routing",
                **probe_common
            )

            if last_stage == "final":
                ri_probe(
                    name = "{}_spef".format(flow),
                    parasitics = "spef",
                    **(probe_common | {"src": ":{}_final".format(flow)})
                )

def ri_qor(
        name,
        design,
        shapes,
        arms,
        seeds,
        arm_sources = {},
        groups = "32",
        arguments = {},
        user_arguments = {},
        sources = {},
        user_sources = {},
        verilog_files = None,
        qualify_sources = True,
        visibility = None):
    """Flows to 6_final for a QoR comparison, with a seed ensemble.

    Every earlier arm in this study is a single deterministic run, which
    is honest for comparing two instruments on one ODB -- the answer is
    exact for that ODB -- and not honest for comparing QoR between arms,
    where the flow's own spread is the thing a difference has to clear.
    pre-route-pessimism measured 2 sigma of 47.5 ps for min_period at
    global route on a contended design, which is larger than several
    effects this study has been quoting, so a QoR arm without repeats
    cannot resolve anything.

    Hence GPL_RANDOM_SEED in the variant: seeds are arms, not noise to be
    averaged away silently. The report shows the individual values.

    Args:
        name: prefix for every target.
        design: the parsed DESIGNS entry.
        shapes: shape name -> ORFS argument overrides.
        arms: arm name -> ORFS argument overrides (the thing under test).
        arm_sources: arm name -> source-typed ORFS variables owned by
            this package, for an arm whose change is a flow hook rather
            than a variable. Merged after the design's own sources, so a
            label of ours is never re-rooted into @orfs.
        seeds: GPL_RANDOM_SEED values, as strings.
        groups: the design size, as a string.
        arguments: the design's ORFS variables.
        user_arguments: project-specific variables.
        sources: source-typed ORFS variables.
        user_sources: source-typed project hooks.
        verilog_files: forwarded.
        qualify_sources: re-root source labels into @orfs.
        visibility: forwarded.
    """
    design_sources = orfs_relative(sources or design["sources"]) if qualify_sources else (sources or design["sources"])

    for shape_name, shape in shapes.items():
        for arm_name, arm in arms.items():
            for seed in seeds:
                variant = "{}_{}_s{}".format(shape_name, arm_name, seed)
                flow = "{}_{}".format(name, variant)
                args = (arguments or design["arguments"]) | shape | arm | {
                    "GPL_RANDOM_SEED": seed,
                    "VERILOG_DEFINES": "-D WIREBOUND_GROUPS={}".format(groups),
                }

                orfs_flow(
                    name = name,
                    variant = variant,
                    arguments = args,
                    last_stage = "final",
                    sources = design_sources | arm_sources.get(arm_name, {}),
                    tags = ["manual"],
                    top = design["name"],
                    user_arguments = user_arguments,
                    verilog_files = verilog_files if verilog_files != None else design["verilog_files"],
                    visibility = visibility,
                )

                ri_probe(
                    name = "{}_spef".format(flow),
                    arguments = args,
                    design = design,
                    parasitics = "spef",
                    qualify_sources = False,
                    sources = design_sources,
                    src = ":{}_final".format(flow),
                    user_arguments = user_arguments,
                    user_sources = user_sources,
                    visibility = visibility,
                )
