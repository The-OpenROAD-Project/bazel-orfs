"""One rung of the density ladder: a place stage at a chosen density.

The question is where the density threshold actually sits -- the lowest
density at which global placement still reaches its overflow target -- so
an arm has to be a real place stage, not a probe over a finished one.

A rung is expressed in ORFS's own currency. `place_density_with_lb_addon`
in ORFS's util.tcl already computes

    density = uniform + (1 - uniform) * PLACE_DENSITY_LB_ADDON + 0.01

which is exactly "a fraction of the way from this design's uniform density
to 1.0". So a rung is a PLACE_DENSITY_LB_ADDON value on the grid i/32, and
every arm is a stock flow run with one stock variable set: nothing in the
harness computes a density, which is what keeps the ladder comparable to
what a design would actually ship.

All rungs of a design share that design's floorplan through
`previous_stage`, so the only thing that differs between two rungs is the
variable. Every target is manual: an arm is a flow run.
"""

load("//:openroad.bzl", "orfs_flow")

# i/32, i in [0, 31]. The top of the range is left out because
# `place_density_with_lb_addon` adds 0.01 on top and ORFS errors out
# (FLW 24) when the result exceeds 1.0 -- a rung that cannot exist for a
# dense design is better left undeclared than declared and always broken.
RUNG_COUNT = 32

def rung_fraction(index):
    """The PLACE_DENSITY_LB_ADDON value of rung `index`."""
    return float(index) / float(RUNG_COUNT)

def rung_variant(index, prefix = ""):
    """FLOW_VARIANT of rung `index` -- also the name of its results dir."""
    return "{}t{}{}".format(prefix, "0" if index < 10 else "", index)

def rung_name(design_name, index, prefix = ""):
    """Target prefix of rung `index` for `design_name`."""
    return "{}_{}".format(design_name, rung_variant(index, prefix))

# Where @orfs's files land in a sandbox declared from this repository.
# ORFS's config.mk writes repo-relative paths -- jpeg's
# VERILOG_INCLUDE_DIRS is "flow/designs/src/jpeg/include" -- and inside
# @orfs's own packages that resolves. Here it does not, and the failure
# arrives as a synthesis error about a missing `include file rather than
# as anything about paths, which is why this is done once and by rule
# rather than per design.
ORFS_ROOT = Label("@orfs//flow:BUILD").workspace_root

def _orfs_path(value):
    """Re-root an ORFS repo-relative path onto @orfs's sandbox root."""
    if value.startswith("flow/"):
        return ORFS_ROOT + "/" + value
    return value

def _include_data(arguments):
    """The files behind VERILOG_INCLUDE_DIRS, as synth-stage data.

    `VERILOG_INCLUDE_DIRS` names a directory, so nothing in `sources`
    stages it and the design's Verilog fails to elaborate on an
    `include` (jpeg's dctu.v wants include/dct_cos_table.v). ORFS's own
    design DSL solves this by depending on the `:include` filegroup each
    directory's package exports; from here the same filegroup is reached
    through @orfs, and scoped to synth, which is the only stage that
    reads Verilog.
    """
    data = []
    for directory in arguments.get("VERILOG_INCLUDE_DIRS", "").split(" "):
        directory = directory.strip().rstrip("/")
        if not directory:
            continue
        if directory.startswith(ORFS_ROOT + "/"):
            directory = directory[len(ORFS_ROOT) + 1:]
        data.append("@orfs//" + directory + ":include")
    return data

def _orfs_label(label):
    """Re-root a DESIGNS label onto @orfs.

    The parsed config.mk stores labels the way the design's own BUILD
    file would write them -- `//flow/designs/src/gcd:verilog` -- because
    that is where the DSL normally expands them. Read from here they
    would resolve against this repository, whose flow/designs tree holds
    test fixtures and nothing else, so every design file has to be
    re-rooted explicitly.
    """
    if label.startswith("//"):
        return "@orfs" + label
    return label


def density_rungs(
        name,
        design,
        top,
        indices = range(RUNG_COUNT),
        probe = True,
        base_flow = None,
        variant_prefix = "",
        user_vars = [],
        user_source_vars = []):
    """Declare the ladder for one design.

    Args:
        name: design key used in target names (the ORFS design directory).
        design: the parsed DESIGNS entry, so an arm cannot disagree with
            the design it measures.
        top: Verilog top of the design.
        indices: which rungs to declare. The campaign walks a coarse
            ladder first and bisects, so most of these are never built --
            declaring them all is what lets a refinement be a build rather
            than an edit.
        variant_prefix: prepended to each rung's FLOW_VARIANT. The
            results path is keyed on the design and the variant, not on
            the target name, so a second ladder over the same design
            needs a prefix of its own or it would write where the first
            one writes.
        base_flow: reuse another design's synth+floorplan flow instead of
            declaring one. The probe control passes the probed design's
            own base here, so the two arms differ in the probe and in
            nothing else -- including the floorplan bytes.
        probe: attach the estimate probe as PRE_GLOBAL_PLACE_TCL. The one
            arm that leaves it off is the control that shows whether
            asking for an estimate changes the placement that follows.
        user_vars: the design's own variables, which ORFS has never heard
            of (mock-alu's MOCK_ALU_WIDTH and the like). They take the
            hatch past the variables.yaml spell-check rather than being
            dropped, because dropping one would change the design.
        user_source_vars: the same, for its path hooks (mock-cpu's
            SDC_FILE_EXTRA).
    """
    arguments = {
        key: _orfs_path(value)
        for key, value in design["arguments"].items()
        if key not in user_vars
    }
    user_arguments = {
        key: value
        for key, value in design["arguments"].items()
        if key in user_vars
    }
    sources = {
        key: [_orfs_label(label) for label in value]
        for key, value in design["sources"].items()
        if key not in user_source_vars
    }
    user_sources = {
        key: [_orfs_label(label) for label in value]
        for key, value in design["sources"].items()
        if key in user_source_vars
    }
    verilog_files = [_orfs_label(label) for label in design["verilog_files"]]
    include_data = _include_data(arguments)
    stage_data = {"synth": include_data} if include_data else {}

    # Synthesis and floorplan, once, shared by every rung through
    # previous_stage: what a rung varies is a place-stage variable, so
    # re-running either per rung would spend hours proving that the same
    # inputs still produce the same netlist. It has to be declared here
    # rather than borrowed from the design's own package: ORFS derives
    # RESULTS_DIR from the package that declares the run, so a place
    # stage declared here looks for its 2_floorplan.odb here
    # (ORD-0007 otherwise, which reads as a missing file rather than as
    # the misconfiguration it is).
    base = base_flow or (name + "_base")
    if base_flow == None:
        orfs_flow(
            name = base,
            arguments = arguments,
            last_stage = "floorplan",
            sources = sources,
            stage_data = stage_data,
            tags = ["manual"],
            top = top,
            user_arguments = user_arguments,
            user_sources = user_sources,
            verilog_files = verilog_files,
        )

    if probe:
        sources = sources | {"PRE_GLOBAL_PLACE_TCL": ["estimate_probe.tcl"]}

        # Two arms that are not rungs, because the question they answer is
        # not "where is the threshold" but "is this command usable":
        #
        #   ship -- the design exactly as it ships, probe attached. The
        #           density is the one its config.mk chose, and the log
        #           carries the estimate beside it.
        #   est  -- the same design with the estimate driving the density
        #           (ESTIMATE_DRIVES_DENSITY). Its first iteration's
        #           overflow is the sharpest test there is of the
        #           estimate's own arithmetic: the command claims that
        #           density produces overflow 0.1 on this placement, and
        #           gpl then reports what the overflow actually is.
        for arm, drive in [("ship", "0"), ("est", "1")]:
            orfs_flow(
                name = name,
                arguments = arguments,
                last_stage = "place",
                previous_stage = {"place": ":" + base + "_floorplan"},
                sources = sources,
                tags = ["manual"],
                top = top,
                user_arguments = user_arguments | {
                    "ESTIMATE_DRIVES_DENSITY": drive,
                },
                user_sources = user_sources,
                variant = variant_prefix + arm,
                verilog_files = verilog_files,
            )

    for index in indices:
        # The rung's identity has to live in `variant`, not only in the
        # target name: ORFS's results path is
        # results/<platform>/<design>/<variant>/, so two rungs sharing a
        # variant would declare the same 3_place.odb. Bazel would reject
        # building both, and -- worse -- a campaign that built them one at
        # a time would read whichever log was written last while every
        # path still looked right.
        orfs_flow(
            name = name,
            variant = rung_variant(index, variant_prefix),
            arguments = arguments | {
                "PLACE_DENSITY_LB_ADDON": str(rung_fraction(index)),
            },
            last_stage = "place",
            previous_stage = {"place": ":" + base + "_floorplan"},
            sources = sources,
            tags = ["manual"],
            top = top,
            user_arguments = user_arguments,
            user_sources = user_sources,
            verilog_files = verilog_files,
        )
