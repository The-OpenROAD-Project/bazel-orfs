"""Each ORFS design as flip-flops and as each register-file shape."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@orfs_designs//:designs.bzl", "DESIGNS")

# a spec's lines for each shape, added to the design's own spec
SHAPES = {
    "inline": "",
    # a macro until macro placement, then its cells: two folds keep a 32-bit
    # word's macro narrow enough to fit a small core
    "netlist": "mode netlist\nbit_folds 2\n",
    "verilog": "periphery verilog\n",
    "mux": "write_style mux\n",
}

def _orfs(labels):
    """DESIGNS' labels are ORFS's own, relative to its repository."""
    return ["@orfs" + x if x.startswith("//") else x for x in labels]

# ORFS's paths are relative to its root; from this package they need its
# repository's root in front
ORFS_ROOT = Label("@orfs//flow:BUILD").workspace_root

def _rooted(arguments):
    dirs = arguments.get("VERILOG_INCLUDE_DIRS")
    if not dirs:
        return arguments
    return arguments | {"VERILOG_INCLUDE_DIRS": " ".join([
        d if d.startswith("external/") else ORFS_ROOT + "/" + d
        for d in dirs.replace("\t", " ").split(" ")
        if d.strip()
    ])}

def _design(key):
    d = DESIGNS[key]
    return (
        _rooted(d["arguments"]),
        {k: _orfs(v) for k, v in d["sources"].items()},
        # a make variable is no file: CLKGATE_MAP_FILE, the one ORFS's
        # designs list, synthesis reads by itself
        _orfs([f for f in d["verilog_files"] if "$(" not in f]),
    )

def _include_data(arguments):
    """VERILOG_INCLUDE_DIRS' files, as orfs_design passes them to synthesis."""
    data = []
    for d in arguments.get("VERILOG_INCLUDE_DIRS", "").replace("\t", " ").split(" "):
        d = d.strip().rstrip("/")
        if d.startswith(ORFS_ROOT + "/"):
            data.append("@orfs//" + d[len(ORFS_ROOT) + 1:] + ":include")
    return {"synth": data} if data else {}

def _sdc(name, sources, period):
    native.genrule(
        name = name,
        srcs = sources["SDC_FILE"],
        outs = [name + ".sdc"],
        cmd = "$(execpath :sdc_period) --period {} $< $@".format(period),
        tools = [":sdc_period"],
        tags = ["manual"],
    )
    return sources | {"SDC_FILE": [":" + name]}

STAGES = ["synth", "floorplan", "place", "cts", "grt", "route"]

def _measure(top, arm):
    """measure.tcl on an arm's routed design: <arm>.json and <arm>_power.json."""
    orfs_run(
        name = arm + "_measure",
        src = ":%s_%s_route" % (top, arm),
        outs = [arm + ".json", arm + "_power.json"],
        script = ":measure.tcl",
        tags = ["manual"],
        user_arguments = {
            "OUTPUT_JSON": "$(location %s.json)" % arm,
            "POWER_JSON": "$(location %s_power.json)" % arm,
        },
    )
    native.filegroup(
        name = arm + "_logs",
        srcs = [":%s_%s_%s" % (top, arm, stage) for stage in STAGES],
        output_group = "logs",
        tags = ["manual"],
    )
    return [arm]

def design_arms(name, top, flops, regfile, module, periods, spec = None, shapes = SHAPES, extra = {}):
    """`name`'s arms: flip-flops and each register-file shape, at each period.

    Args:
      name: the design, as the arms' variant prefix.
      top: the design's top module, the flow's name.
      flops: the DESIGNS key of the design as ORFS has it.
      regfile: the DESIGNS key of its register-file variant, or None to
        add AUTO_MEMORIES and the spec to the flip-flop design.
      module: the spec's module, for AUTO_MEMORIES_MACRO_PLACE.
      periods: {arm: [ps, ...]}, the clock periods each arm runs at; an
        arm is "flops" or a shape's name.
      shapes: {shape: spec lines added to `spec`}; None runs the
        variant as ORFS has it, its specs unchanged.
      spec: the register-file spec every shape's starts from; the
        variant's own AUTO_MEMORIES_REGFILES when None.
      extra: {shape: arguments added to that shape's flow}.

    Returns:
      The arms' names, <name>_<shape or flops>_<period>.
    """
    f_args, f_sources, f_verilog = _design(flops)

    # orfs_flow's default is asap7; another platform is named, and asap7
    # left to the default so its arms keep their cache keys
    platform = DESIGNS[flops]["platform"]
    pdk = {} if platform == "asap7" else {"pdk": "@orfs//flow:" + platform}
    r_args, r_sources, r_verilog = _design(regfile) if regfile else (
        f_args | {"AUTO_MEMORIES": "1"},
        f_sources,
        f_verilog,
    )
    as_is = [shape for shape, lines in shapes.items() if lines == None]
    arms = []
    if spec == None and len(as_is) < len(shapes):
        specs = r_sources.get("AUTO_MEMORIES_REGFILES", [])
        if len(specs) != 1:
            fail("%s: %s has %d register-file specs, not one" % (name, regfile, len(specs)))
        spec = specs[0]
    for period in periods.get("flops", []):
        arm = "%s_flops_%d" % (name, period)
        orfs_flow(
            name = top,
            arguments = f_args,
            last_stage = "route",
            stage_data = _include_data(f_args),
            sources = _sdc(arm + "_sdc", f_sources, period),
            tags = ["manual"],
            variant = arm,
            verilog_files = f_verilog,
            **pdk
        )
        arms += _measure(top, arm)
    for shape, lines in shapes.items():
        if not periods.get(shape):
            continue
        if lines == None:
            # the variant as ORFS has it, every spec its own
            for period in periods[shape]:
                arm = "%s_%s_%d" % (name, shape, period)
                orfs_flow(
                    name = top,
                    arguments = r_args | extra.get(shape, {}),
                    last_stage = "route",
                    stage_data = _include_data(r_args),
                    sources = _sdc(arm + "_sdc", r_sources, period),
                    tags = ["manual"],
                    variant = arm,
                    verilog_files = r_verilog,
                    **pdk
                )
                arms += _measure(top, arm)
            continue
        native.genrule(
            name = "%s_%s_spec" % (name, shape),
            srcs = [spec],
            outs = ["%s_%s.regfile" % (name, shape)],
            cmd = "cat $< > $@ && printf '%s' >> $@" % lines.replace("\n", "\\n"),
            tags = ["manual"],
        )
        args = r_args | extra.get(shape, {})
        if lines.startswith("mode netlist"):
            # a small core around a register-file macro: ORFS's 20 um
            # default channel leaves no room to place it
            args = {"RTLMP_MIN_CHANNEL_SIZE": "2 2"} | args | {
                "AUTO_MEMORIES_MACRO_PLACE": module,
            } | extra.get(shape, {})
        for period in periods[shape]:
            arm = "%s_%s_%d" % (name, shape, period)
            orfs_flow(
                name = top,
                arguments = args,
                last_stage = "route",
                stage_data = _include_data(args),
                sources = _sdc(arm + "_sdc", r_sources, period) | {
                    "AUTO_MEMORIES_REGFILES": [":%s_%s_spec" % (name, shape)],
                },
                tags = ["manual"],
                variant = arm,
                verilog_files = r_verilog,
                **pdk
            )
            arms += _measure(top, arm)
    return arms
