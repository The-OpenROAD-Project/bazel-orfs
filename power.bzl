"""Bazel macros for the Verilator-SAIF -> OpenSTA `report_power` pipeline.

Three building blocks:

  verilator_saif       drive a SAIF-emitting Verilator simulator against
                       an ELF (or any binary) to produce a `.saif`.
  power_data           run `report_power -saif` whole-design, emitting
                       both a vectorless and a vector-driven JSON.
  power_per_module     run `report_power -saif -instances` per-module,
                       emitting one JSON keyed by an instance-list map.

All rules are tagged "manual" — the full SAIF->OpenSTA chain is
expensive (Verilator + OpenSTA) and is opt-in.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_run")
load("@bazel-orfs//:orfs_genrule.bzl", "orfs_genrule")

# ORFS stage stems used as POWER_STAGE by power.tcl / power_per_module.tcl.
_POWER_STAGE_STEM = {
    "floorplan": "2_floorplan",
    "place": "3_place",
    "cts": "4_cts",
    "grt": "6_final",
    "final": "6_final",
}

POWER_TYPES = [
    "vectorless",
    "vector-driven",
]

_POWER_BASE_TCL = "@bazel-orfs//:power_base.tcl"
_POWER_TCL = "@bazel-orfs//:power.tcl"
_POWER_PER_MODULE_TCL = "@bazel-orfs//:power_per_module.tcl"

def verilator_saif(
        name,
        saif_run,
        stimulus,
        out,
        extra_args = "",
        visibility = None):
    """Run a SAIF-tracing Verilator simulator and capture a .saif file.

    The `saif_run` target is a Verilator-built simulator binary that
    accepts:
        --trace-saif-file=<path>     (mandatory; this rule supplies it)
        <stimulus> [extra_args]      (positional, depends on harness)

    Args:
      name: target name.
      saif_run: label of the Verilator simulator binary.
      stimulus: label of the stimulus passed positionally to the binary
        (typically an ELF or trace file).
      out: filename for the emitted `.saif`.
      extra_args: string appended verbatim after the stimulus path. Use
        for harness-specific positional args (e.g. iteration counters,
        magic-memory protocol values).
      visibility: forwarded.
    """
    native.genrule(
        name = name,
        srcs = [stimulus],
        outs = [out],
        cmd = """
            $(execpath {saif_run}) \
                --trace-saif-file=$@ \
                $(location {stimulus}) \
                {extra_args}
        """.format(
            saif_run = saif_run,
            stimulus = stimulus,
            extra_args = extra_args,
        ),
        tags = ["manual"],
        tools = [saif_run],
        visibility = visibility,
    )

def power_data(
        name,
        flow_target,
        stage,
        saif,
        verilog,
        spef,
        saif_scope,
        out_template,
        spef_paths_tcl = None,
        visibility = None):
    """Run whole-design `report_power -saif` and emit one JSON per POWER_TYPES.

    Args:
      name: target name.
      flow_target: orfs_flow stage target supplying ODB / LIB_FILES /
        TECH_LEF / SC_LEF / SDC via OrfsInfo.
      stage: ORFS stage key ("floorplan" / "place" / "cts" / "grt" / "final").
      saif: label of a .saif (produced by verilator_saif()).
      verilog: gate-level netlist label.
      spef: parasitics SPEF label.
      saif_scope: OpenSTA hierarchy scope for read_saif — typically
        `TOP/<dut-instance>/<DESIGN_NAME>`, depending on how the
        Verilator harness wraps the DUT.
      out_template: filename pattern with a `{power}` placeholder. Expanded
        once per entry of POWER_TYPES, e.g. `"cts_{power}_power.json"`.
      spef_paths_tcl: optional label of a per-instance SPEF-scoping Tcl
        snippet; supersedes the default flat `read_spef` loop in
        power_base.tcl when a design has multiple SPEFs under different
        instance scopes.
      visibility: forwarded.
    """
    outs = [out_template.format(power = power) for power in POWER_TYPES]
    arguments = {
        "SAIF_STIMULI": "$(location {})".format(saif),
        "POWER_STAGE": _POWER_STAGE_STEM[stage],
        "POWER_BASE_TCL": "$(location {})".format(_POWER_BASE_TCL),
        "SAIF_SCOPE": saif_scope,
        "SPEFS_AND_NETLISTS": "$(location {verilog}) $(location {spef})".format(
            verilog = verilog,
            spef = spef,
        ),
    } | {
        "{}_POWER_JSON".format(power.upper()): "$(location {})".format(
            out_template.format(power = power),
        )
        for power in POWER_TYPES
    }
    data = [
        verilog,
        spef,
        saif,
        _POWER_BASE_TCL,
    ]
    if spef_paths_tcl != None:
        arguments["SPEF_PATHS_TCL"] = "$(location {})".format(spef_paths_tcl)
        data.append(spef_paths_tcl)
    orfs_run(
        name = name,
        src = flow_target,
        outs = outs,
        arguments = arguments,
        data = data,
        script = _POWER_TCL,
        tags = ["manual"],
        visibility = visibility,
    )

def power_per_module(
        name,
        flow_target,
        stage,
        saif,
        verilog,
        spef,
        saif_scope,
        module_instance_map_tcl,
        out,
        spef_paths_tcl = None,
        visibility = None):
    """Run per-module `report_power -saif -instances`; emit one JSON.

    Args:
      name: target name.
      flow_target: orfs_flow stage target.
      stage: ORFS stage key.
      saif: .saif label.
      verilog: gate-level netlist label.
      spef: SPEF label.
      saif_scope: OpenSTA hierarchy scope for read_saif.
      module_instance_map_tcl: label of a Tcl file containing a single
        dict literal whose values are instance-path lists per module.
      out: output JSON filename.
      spef_paths_tcl: optional per-instance SPEF-scoping Tcl (see power_data).
      visibility: forwarded.
    """
    arguments = {
        "SAIF_STIMULI": "$(location {})".format(saif),
        "POWER_STAGE": _POWER_STAGE_STEM[stage],
        "SAIF_SCOPE": saif_scope,
        "SPEFS_AND_NETLISTS": "$(location {verilog}) $(location {spef})".format(
            verilog = verilog,
            spef = spef,
        ),
        "OUT_JSON": "$(location {})".format(out),
        "MODULE_INSTANCE_MAP": "$(location {})".format(module_instance_map_tcl),
        "POWER_BASE_TCL": "$(location {})".format(_POWER_BASE_TCL),
    }
    data = [
        verilog,
        spef,
        module_instance_map_tcl,
        saif,
        _POWER_BASE_TCL,
    ]
    if spef_paths_tcl != None:
        arguments["SPEF_PATHS_TCL"] = "$(location {})".format(spef_paths_tcl)
        data.append(spef_paths_tcl)
    orfs_run(
        name = name,
        src = flow_target,
        outs = [out],
        arguments = arguments,
        data = data,
        script = _POWER_PER_MODULE_TCL,
        tags = ["manual"],
        visibility = visibility,
    )
