"""Turning a placed-and-routed stage into an energy number.

The chain, and why each link is where it is:

  grt_netlist     the stage's ODB written out as Verilog, because the
                  gate-level simulation needs a netlist and the flow
                  writes only an ODB at a stage boundary.

  stage_power     report_power against that stage, twice -- once
                  vectorless and once driven by the SAIF -- so a SAIF
                  that failed to bind is visible as two identical
                  reports rather than as a quiet fallback to default
                  activity.

The netlist must come from the same stage the power is reported on. A
SAIF captured against one stage's netlist and applied to another leaves
nets unmatched, and OpenSTA falls back to default activity for them
rather than failing -- so the error shows up as a plausible number.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_run")

# ORFS stage stems, as private/stages.bzl spells them. The netlist and
# the power report have to name the same one.
STAGE_STEM = {
    "synth": "1_synth",
    "cts": "4_1_cts",
    "grt": "5_1_grt",
    "route": "5_route",
    "final": "6_final",
}

def grt_netlist(name, src, stage = "grt", out = None, tags = ["manual"], visibility = None):
    """Write a stage's gate-level netlist from its ODB.

    Args:
      name: target name.
      src: the flow stage target whose ODB is read.
      stage: which stage's files to load; must match `src`.
      out: output filename; defaults to `<name>.v`.
      tags: forwarded; manual, since this needs the flow to have run.
      visibility: forwarded.
    """
    out = out or (name + ".v")
    orfs_run(
        name = name,
        src = src,
        outs = [out],
        script = "//test/coremark_joule/flow:write_netlist.tcl",
        user_arguments = {
            "OUTPUT": "$(location {})".format(out),
            "STAGE_STEM": STAGE_STEM[stage],
        },
        tags = tags,
        visibility = visibility,
    )

def stage_power(
        name,
        src,
        saif,
        saif_scope,
        stage = "grt",
        tags = ["manual"],
        visibility = None):
    """Report power at a stage, vectorless and SAIF-driven.

    Args:
      name: target name; outputs `<name>_vectorless.json` and
        `<name>_vector_driven.json`.
      src: the flow stage target whose ODB is read.
      saif: the .saif label.
      saif_scope: hierarchy in the SAIF corresponding to the design root.
        The simulator wraps the design in a testbench, so this names the
        instance inside it -- e.g. `TOP/cm_soc/cpu`.
      stage: which stage; must match `src`.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    vectorless = name + "_vectorless.json"
    vector_driven = name + "_vector_driven.json"
    orfs_run(
        name = name,
        src = src,
        outs = [
            vectorless,
            vector_driven,
        ],
        script = "//test/coremark_joule/flow:power_grt.tcl",
        data = [saif],
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "SAIF_STIMULI": "$(location {})".format(saif),
            "SAIF_SCOPE": saif_scope,
            "VECTORLESS_POWER_JSON": "$(location {})".format(vectorless),
            "VECTOR_DRIVEN_POWER_JSON": "$(location {})".format(vector_driven),
        },
        tags = tags,
        visibility = visibility,
    )

def stage_power_units(
        name,
        src,
        saif,
        saif_scope,
        stage = "grt",
        tags = ["manual"],
        visibility = None):
    """Report power per module instance at a stage.

    The whole-design number says how much; this says where. The instance
    paths are discovered from the ODB rather than declared, so they
    cannot drift from the netlist.
    """
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".json"],
        script = "//test/coremark_joule/flow:power_units_grt.tcl",
        data = [saif],
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "SAIF_STIMULI": "$(location {})".format(saif),
            "SAIF_SCOPE": saif_scope,
            "OUT_JSON": "$(location {}.json)".format(name),
        },
        tags = tags,
        visibility = visibility,
    )

# The sweep points, in toggles per clock period. 0.0 is "an unannotated
# root never toggles"; 2.0 is "it toggles as often as the clock"; 0.1 is
# OpenSTA's own default, and is in the list so the default case is a
# measured point rather than the unstated middle of a range.
ACTIVITY_SWEEP = [
    "0.0",
    "0.1",
    "1.0",
    "2.0",
]

def _activity_slug(activity):
    return activity.replace(".", "p")

def stage_activity_audit(
        name,
        src,
        saif,
        saif_scope,
        policy = "pin_policy.json",
        stage = "grt",
        tags = ["manual"],
        visibility = None):
    """Enumerate every pin and where its switching activity came from.

    Emits facts, not verdicts: `<name>_pins.tsv` is the ODB's view of
    every pin, `<name>_annotation.txt` is OpenSTA's annotated and
    unannotated listings, and `<name>_design.json` carries the clock and
    the liberty corner. The classification and its policy live in
    scripts/classify_pins.py, where they are unit-tested.

    Args:
      name: target name.
      src: the flow stage target whose ODB is read; must match `stage`.
      saif: the .saif label -- the same one the power report uses.
      saif_scope: hierarchy in the SAIF corresponding to the design root.
      policy: the design's pin_policy.json -- its budget for unannotated
        internal pins, and its waivers, each with a written reason.
      stage: which stage; must match `src`.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    pins = name + "_pins.tsv"
    annotation = name + "_annotation.txt"
    design = name + "_design.json"
    orfs_run(
        name = name,
        src = src,
        outs = [
            pins,
            annotation,
            design,
        ],
        script = "//test/coremark_joule/flow:activity_audit.tcl",
        data = [saif],
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "SAIF_STIMULI": "$(location {})".format(saif),
            "SAIF_SCOPE": saif_scope,
            "PINS_TSV": "$(location {})".format(pins),
            "ANNOTATION_TXT": "$(location {})".format(annotation),
            "DESIGN_JSON": "$(location {})".format(design),
        },
        tags = tags,
        visibility = visibility,
    )

    # The verdict, from the facts. Separate target because the
    # classification and its policy are unit-tested Python, and because
    # re-deciding what counts as benign must not cost an OpenROAD run.
    native.genrule(
        name = name + "_audit",
        srcs = [
            pins,
            annotation,
            design,
            policy,
        ],
        outs = [name + "_audit.json"],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:classify_pins)",
            "--pins $(location {})".format(pins),
            "--annotation $(location {})".format(annotation),
            "--design $(location {})".format(design),
            "--policy $(location {})".format(policy),
            "--out $@",
        ]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:classify_pins"],
        visibility = visibility,
    )

def stage_activity_sweep(
        name,
        src,
        saif,
        saif_scope,
        stage = "grt",
        activities = ACTIVITY_SWEEP,
        epsilon = "0.005",
        min_control_spread = "0.05",
        tags = ["manual"],
        visibility = None):
    """Sweep the default activity OpenSTA seeds unannotated roots with.

    The audit says how many pins were annotated; this says whether that
    mattered. Each arm reports power once per activity, and the caller
    spells out both the point and the file it lands in, so the two
    cannot drift apart.

    Args:
      name: target name; outputs `<name>_<arm>_a<activity>.json`.
      src: the flow stage target whose ODB is read; must match `stage`.
      saif: the .saif label -- the same one the power report uses.
      saif_scope: hierarchy in the SAIF corresponding to the design root.
      stage: which stage; must match `src`.
      activities: sweep points, in toggles per clock period.
      epsilon: how far the SAIF-driven total may move across the whole
        sweep, as a fraction of its mean.
      min_control_spread: how far the vectorless total must move for the
        sweep to count as a working positive control.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    outs = []
    points = []
    for arm in ["vectorless", "saif"]:
        for activity in activities:
            out = "{}_{}_a{}.json".format(name, arm, _activity_slug(activity))
            outs.append(out)
            points.append("{}|{}|$(location {})".format(arm, activity, out))
    orfs_run(
        name = name,
        src = src,
        outs = outs,
        script = "//test/coremark_joule/flow:activity_sweep.tcl",
        data = [saif],
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "SAIF_STIMULI": "$(location {})".format(saif),
            "SAIF_SCOPE": saif_scope,
            "SWEEP_POINTS": " ".join(points),
        },
        tags = tags,
        visibility = visibility,
    )

    native.genrule(
        name = name + "_check",
        srcs = outs,
        outs = [name + "_check.json"],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:check_activity_sweep)",
        ] + [
            "--point {}".format(point.replace("|", ":"))
            for point in points
        ] + [
            "--epsilon {}".format(epsilon),
            "--min-control-spread {}".format(min_control_spread),
            "--out $@",
        ]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:check_activity_sweep"],
        visibility = visibility,
    )

def hier_probe(name, src, stage, tags = ["manual"], visibility = None):
    """Report how much module hierarchy a stage's ODB still carries."""
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".txt"],
        script = "//test/coremark_joule/flow:hier_probe.tcl",
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "OUT": "$(location {}.txt)".format(name),
        },
        tags = tags,
        visibility = visibility,
    )
