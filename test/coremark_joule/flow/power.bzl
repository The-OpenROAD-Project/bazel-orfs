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
load("@rules_cc//cc:defs.bzl", "cc_binary")
load("@rules_verilator//verilator:defs.bzl", "verilator_cc_library")
load("@rules_verilog//verilog:defs.bzl", "verilog_library")

# ORFS stage stems, as private/stages.bzl spells them. The netlist and
# the power report have to name the same one.
STAGE_STEM = {
    "synth": "1_synth",
    "floorplan": "2_floorplan",
    "place": "3_place",
    "cts": "4_1_cts",
    "grt": "5_1_grt",
    "route": "5_route",
    "final": "6_final",
}

def grt_netlist(
        name,
        src,
        stage = "grt",
        out = None,
        max_renames = 0,
        saif_names = False,
        tags = ["manual"],
        visibility = None):
    """Write a stage's gate-level netlist from its ODB.

    Two steps, because `write_verilog` can emit two different instances
    under one name in the same module. On VeeR EH1 it does it once, in a
    netlist of a million lines. The result is not valid Verilog;
    Verilator rejects it, which is the good case -- a tool that accepted
    it would silently keep one of the two and simulate a design the power
    was not reported on.

    So the raw output goes to `<name>_raw.v` and
    scripts/uniquify_netlist.py produces `<name>.v` from it. With
    `max_renames = 0` that second step is an assertion that the netlist
    has no collisions, which is what it is for every core but VeeR.

    Args:
      name: target name; the usable netlist is `<name>.v`.
      src: the flow stage target whose ODB is read.
      stage: which stage's files to load; must match `src`.
      out: output filename; defaults to `<name>.v`.
      max_renames: how many duplicate instance names this design is known
        to have. Zero asserts there are none.
      saif_names: spell `/` inside escaped names as scripts/slash_names.py
        does, so the SAIF of a simulation of this netlist can carry them:
        a flattened name, every cell of a flat ODB of a hierarchically
        synthesised unit, a cell below a module that was not kept in a
        hierarchical one. For every unit of a stage_power_shards(), whose
        shards rename the ODB's instances to match. Off, the netlist keeps
        the ODB's names.
      tags: forwarded; manual, since this needs the flow to have run.
      visibility: forwarded.
    """
    out = out or (name + ".v")
    raw = name + "_raw.v"
    orfs_run(
        name = name + "_raw",
        src = src,
        outs = [raw],
        script = "//test/coremark_joule/flow:write_netlist.tcl",
        user_arguments = {
            "OUTPUT": "$(location {})".format(raw),
            "STAGE_STEM": STAGE_STEM[stage],
        },
        tags = tags,
        visibility = visibility,
    )

    # `/` spelled first, so uniquify_netlist, whose instance pattern has
    # no `/`, checks the flattened names too
    spelled = raw
    if saif_names:
        spelled = name + "_spelled.v"
        native.genrule(
            name = name + "_spelled",
            srcs = [raw],
            outs = [spelled],
            cmd = "$(execpath //test/coremark_joule/scripts:slash_names) $< $@",
            tags = tags,
            tools = ["//test/coremark_joule/scripts:slash_names"],
        )
    native.genrule(
        name = name,
        srcs = [spelled],
        outs = [out],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:uniquify_netlist)",
            "$(location {})".format(spelled),
            "$@",
            "--max-renames {}".format(max_renames),
        ]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:uniquify_netlist"],
        visibility = visibility,
    )

def stage_sdf(name, src, stage = "grt", tags = ["manual"], visibility = None):
    """Write a stage's SDF: the per-instance delays, from its own ODB.

    The netlist, the delays and the power report all have to come from
    one ODB or they describe different designs. grt_netlist() takes the
    netlist from the stage's ODB for exactly that reason; this takes the
    delays from the same place.

    Args:
      name: target name; the SDF is `<name>.sdf`.
      src: the flow stage target whose ODB is read.
      stage: which stage; must match `src`.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    out = name + ".sdf"
    orfs_run(
        name = name,
        src = src,
        outs = [out],
        script = "//test/coremark_joule/flow:write_sdf.tcl",
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "OUTPUT": "$(location {})".format(out),
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
        spef = None,
        clock_transition_ps = None,
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
      spef: a .spef to read instead of estimating parasitics. Only a
        post-route stage has one. Giving it turns this target into the
        calibration of the estimate rather than another instance of it:
        point it and an estimating target at the same ODB and the same
        SAIF, and the difference between them is the parasitics model
        and nothing else (5.3).
      clock_transition_ps: synth only. An ideal-clock transition applied
        at power time, standing in for the clock tree a synthesis netlist
        does not have; see power_synth.tcl for why the number matters.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    vectorless = name + "_vectorless.json"
    vector_driven = name + "_vector_driven.json"
    arguments = {
        "STAGE_STEM": STAGE_STEM[stage],
        "SAIF_STIMULI": "$(location {})".format(saif),
        "SAIF_SCOPE": saif_scope,
        "VECTORLESS_POWER_JSON": "$(location {})".format(vectorless),
        "VECTOR_DRIVEN_POWER_JSON": "$(location {})".format(vector_driven),
    }
    if spef:
        arguments["POWER_SPEF"] = spef
    if clock_transition_ps:
        arguments["CLOCK_TRANSITION_PS"] = str(clock_transition_ps)
    orfs_run(
        name = name,
        src = src,
        outs = [
            vectorless,
            vector_driven,
        ],
        # At synthesis there is no placement to estimate wires from, so the
        # report runs on cell capacitances alone (§4.8's cross-check wants
        # exactly that); every later stage estimates from global routing.
        script = "//test/coremark_joule/flow:power_synth.tcl" if stage == "synth" else "//test/coremark_joule/flow:power_grt.tcl",
        data = [saif],
        user_arguments = arguments,
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

def power_shard(
        name,
        src,
        saif,
        saif_scope,
        unit = "",
        children = [],
        stage = "grt",
        parasitics = "global_routing",
        units = False,
        tags = ["manual"],
        visibility = None):
    """One unit's shard of a hierarchical design's power: `<name>.json`.

    report_power on the unit's own ODB, vectorless and SAIF-driven, and
    the power of `children`, the unit's instances that are shards of
    their own, for the merge to subtract (power_shard_grt.tcl says which
    part and why). stage_power_shards() makes one per unit; on its own,
    it is the negative control's shard: a scope the SAIF has no
    instance at.

    Args:
      name: target name.
      src: the unit's own flow stage target.
      saif: the .saif label.
      saif_scope: the unit's scope in the SAIF.
      unit: the unit's instance path from the design root; empty for the
        parent.
      children: instance paths, relative to the unit, of its children
        that are shards.
      stage: which stage; must match `src`.
      parasitics: estimate_parasitics' source, global_routing as
        stage_power's; placement only for the toy's proof.
      units: also `<name>_units.json`, the SAIF-driven power of every
        module instance the unit's ODB keeps (power_shard_grt.tcl).
      tags: forwarded; manual.
      visibility: forwarded.
    """
    extra = {"SHARD_UNITS_JSON": "$(location {}_units.json)".format(name)} if units else {}
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".json"] + ([name + "_units.json"] if units else []),
        script = "//test/coremark_joule/flow:power_shard_grt.tcl",
        data = [saif],
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "SAIF_STIMULI": "$(location {})".format(saif),
            "SAIF_SCOPE": saif_scope,
            "SHARD_UNIT": unit,
            "SHARD_CHILDREN": " ".join(children),
            "SHARD_JSON": "$(location {}.json)".format(name),
            "POWER_PARASITICS": parasitics,
        } | extra,
        tags = tags,
        visibility = visibility,
    )

def _shard_slug(path):
    return "".join([c if c.isalnum() or c == "_" else "_" for c in path.elems()])

def _shard_parent(path, paths):
    """The nearest unit above `path`: the longest other path it is under, or the root."""
    best = ""
    for p in paths:
        if p != path and path.startswith(p + "/") and len(p) > len(best):
            best = p
    return best

def _shard_scope(saif_scope, unit, paths, scopes):
    """A unit's scope in the SAIF: its parent unit's, then its path in it,
    unless `scopes` says otherwise."""
    parts = []
    for _ in range(len(paths) + 1):
        if unit == "":
            return "/".join([saif_scope] + parts)
        if unit in scopes:
            return "/".join([scopes[unit]] + parts)
        up = _shard_parent(unit, paths)
        parts.insert(0, unit[len(up) + 1:] if up else unit)
        unit = up
    fail("unreachable")

def shard_saif_merge(
        name,
        parent_saif,
        units,
        saif_scope,
        scopes = {},
        sources = {},
        clocks = ["clock"],
        tags = ["manual"],
        visibility = None):
    """The power shards' one SAIF, from one simulation per shard.

    The parent's simulation (its netlist as gates, every hardened unit as
    RTL) and each unit's (the SoC's RTL with that unit alone as its own
    netlist, its scope alone traced) are merged by scripts/saif_merge.py:
    each unit's RTL subtree replaced by its gates. Each unit goes where
    the netlist holding it has it, the scope its shard reads
    (stage_power_shards with the same saif_scope and scopes); it is taken
    from its own simulation at its RTL instance path, `saif_scope/<path>`.

    Args:
      name: target name; the SAIF is `<name>.saif`.
      parent_saif: the parent's simulation's SAIF.
      units: {instance path from the parent's root: the unit's SAIF}, the
        paths stage_power_shards' `shards` has.
      saif_scope: the parent's scope in every SAIF.
      scopes: as stage_power_shards'.
      sources: {path: the unit's scope in its own SAIF} where it is not
        `saif_scope/<path>`: a replay's (shard_replay), its `dut`.
      clocks: the port names the SDCs put the design's one clock on; the
        merge refuses files whose clock differs.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    paths = sorted(units.keys())
    native.genrule(
        name = name,
        srcs = [parent_saif] + [units[p] for p in paths],
        outs = [name + ".saif"],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:saif_merge)",
            "--parent $(location {})".format(parent_saif),
            "--out $@",
        ] + [
            "--unit {}=$(location {}):{}".format(
                _shard_scope(saif_scope, p, paths, scopes),
                units[p],
                sources.get(p, saif_scope + "/" + p),
            )
            for p in paths
        ] + ["--clock " + c for c in clocks]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:saif_merge"],
        visibility = visibility,
    )

def shard_replay(
        name,
        top,
        netlist,
        rtl,
        capture,
        capture_scope,
        window_start,
        clk_period,
        children = {},
        path = "",
        window_end = "0",
        window_file = None,
        trace = "saif",
        trace_scopes = [],
        stubs = False,
        stub_map = None,
        count_outputs = False,
        compare_from_reset = False,
        clock_nets = ["clknet_*"],
        clock_ports = ["clock"],
        cells = "//test/coremark_joule/rtl:asap7_stdcells",
        copts = ["-O2"],
        vopts = [],
        tags = ["manual"],
        visibility = None):
    """A power shard's SAIF from its own netlist alone, replayed from a capture.

    scripts/replay_gen.py writes a top `<name>` with the unit's netlist as
    `dut`, each child that is a shard of its own a stub driven from its
    capture, and the harness that drives it all from `capture` (a VCD of
    the RTL simulation's unit wrappers, scripts/capture_wrap.py), checks
    every output of the unit and every pin into a child against it, and
    fails on the first difference, naming signal, cycle and phase.
    gate_stitch.py fills in from `rtl` what the netlist instantiates and
    does not define (SRAMs, ClockGate). The model traces `dut` alone.

    Outputs `<name>.saif`, its scope TOP/<name>/dut, from `window_start`
    on, `<name>_report.json`, and `<name>_stubs.json`, the stubs' map
    (replay_gen.py says what a two-level replay is).

    Args:
      name: target name, and the replay top's module name.
      top: the unit's module.
      netlist: the unit's netlist, grt_netlist(saif_names = True)'s.
      rtl: one file of every RTL module, the capture simulation's,
        unwrapped: the units' ports and the SRAM models come from it.
      capture: the capture VCD.
      capture_scope: the unit's wrapper scope in it, dotted.
      window_start: the capture time the SAIF starts at.
      clk_period: the clock period in capture time units, or the label of
        the design's constraints.sdc (any label ending in .sdc), read at
        build time as the capture reads it, so a new SDC period reaches
        the replays with no edit here.
      children: {instance path below the shard: its wrapper scope in the
        capture}, the children simulated as shards of their own (a
        unit's hardened children, the kept modules cut out of it).
      path: the instance path below `top` of the module this replays, a
        simulation shard cut out of the unit; empty: the unit whole.
      window_end: the capture time the SAIF ends at; 0: its end.
      window_file: a file of "<start> <end>" instead of the two
        (saif_window.py --window-out).
      clock_nets: patterns of the clock tree's leaf nets, which a kept
        module's netlist has a port for each of where its RTL has one
        clock port (OpenROAD's CTS names them clknet_*): the one clock.
      trace: "saif", the shard's SAIF, or "vcd": a replay of RTL that is
        itself a capture, `<name>.vcd`, of `trace_scopes` (dotted, below
        `<name>`, each traced one level deep: the wrappers of the units
        below), every time, absolute.
      stubs: level 1 of a two-level replay: the harness also writes
        `<name>_stubs.vcd`, every port of every child stub at every time,
        the punched ones under the aliases `<name>_stubs.json` maps,
        each stub at TOP.<name>.dut.<path, dotted>. Written by the same
        harness run as the SAIF: no second model. And
        `<name>_stub_inputs.json`: the pins the unit drives into its stubs
        that differ from the RTL, a diagnostic (replay_gen.py's harness;
        each piece's outputs, checked in level 2, are what must match).
      stub_map: level 2: the level-1 replay's `_stubs.json`; `capture` is
        then its `_stubs.vcd`, `capture_scope` the stub's scope there,
        and `path` the stub's path.
      count_outputs: level 2, a piece whose outputs differ from the RTL
        and whose SAIF is taken as produced: a differing output is counted,
        not fatal, and the counts written to `<name>_outputs.json`
        (replay_gen.py --count-outputs). Every other replay's generated
        files are as they were without it.
      compare_from_reset: level 2, a piece whose outputs are compared only
        from the cycle after the captured `reset` input first falls:
        before it, they are the simulators' initial values, not the
        design's (replay_gen.py --compare-from-reset); the cycle is
        written to `<name>_from_reset.json`.
      clock_ports: the ports the SDCs put the one clock on.
      cells: the standard-cell models.
      copts: the harness's C++ options.
      vopts: Verilator's options.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    native.genrule(
        name = name + "_gen",
        srcs = [netlist, rtl] + ([stub_map] if stub_map else []),
        outs = [
            name + "_top.sv",
            name + ".cc",
            name + "_dut.v",
            name + "_report.json",
            name + "_stubs.json",
        ],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:replay_gen)",
            "--name " + name,
            "--top " + top,
            "--netlist $(location {})".format(netlist),
            "--rtl $(location {})".format(rtl),
            "--capture-scope " + capture_scope,
        ] + (["--path " + path] if path else []) + [
            "--child {}={}".format(m, sc)
            for m, sc in sorted(children.items())
        ] + [
            "--clock-port " + c
            for c in clock_ports
        ] + [
            "--clock-net '%s'" % c
            for c in clock_nets
        ] + [
            "--out-sv $(location {}_top.sv)".format(name),
            "--out-cc $(location {}.cc)".format(name),
            "--out-netlist $(location {}_dut.v)".format(name),
            "--report $(location {}_report.json)".format(name),
            "--out-stubs $(location {}_stubs.json)".format(name),
        ] + (["--stub-map $(location {})".format(stub_map)] if stub_map else []) + (["--record-stubs"] if stubs else []) + (["--count-outputs"] if count_outputs else []) + (["--compare-from-reset"] if compare_from_reset else [])),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:replay_gen"],
    )
    native.genrule(
        name = name + "_stitch",
        srcs = [
            name + "_top.sv",
            name + "_dut.v",
            rtl,
        ],
        outs = [name + "_stitched.sv"],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:gate_stitch)",
            "--netlist $(location {}_top.sv)".format(name),
            "--gate-netlist $(location {}_dut.v)".format(name),
            "--rtl-file $(location {})".format(rtl),
            "--top " + name,
            "--cell-suffix _ASAP7_",
            "--out $@",
        ]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:gate_stitch"],
    )
    on = ["tracing_on -scope \\\"%s.dut*\\\"" % name]
    if trace == "vcd":
        on = ["tracing_on -scope \\\"%s.%s\\\" -levels 1" % (name, sc) for sc in trace_scopes]
    native.genrule(
        name = name + "_trace",
        outs = [name + "_trace.v"],
        # a configuration in a .v file: verilog_library takes no .vlt
        cmd = "printf '`verilator_config\\ntracing_off -scope \"*\"\\n%s\\n' > $@" % "\\n".join(on),
        tags = tags,
    )
    verilog_library(
        name = name + "_v",
        srcs = [
            name + "_top.sv",
            name + "_stitched.sv",
            name + "_trace.v",
        ],
        tags = tags,
        deps = [cells],
    )
    verilator_cc_library(
        name = name + "_lib",
        copts = copts + ["-Wno-all"],
        module = ":%s_v" % name,
        module_top = name,
        tags = tags,
        trace_mode = trace,
        vopts = vopts,
    )
    cc_binary(
        name = name + "_bin",
        srcs = [name + ".cc"],
        copts = copts + ["-std=c++17"],
        tags = tags,
        deps = [":%s_lib" % name],
    )
    sdc = clk_period.endswith(".sdc")
    native.genrule(
        name = name,
        # the harness in srcs, not tools: as a tool it would be built in the
        # exec configuration, the flow behind its netlist a second time
        # (coremark_run says the same of a simulator)
        srcs = [
            capture,
            ":%s_bin" % name,
        ] + ([window_file] if window_file else []) + ([clk_period] if sdc else []),
        outs = [name + "." + trace] + ([
            name + "_stubs.vcd",
            name + "_stub_inputs.json",
        ] if stubs else []) + ([name + "_outputs.json"] if count_outputs else []) + ([name + "_from_reset.json"] if compare_from_reset else []),
        cmd = ("read s e < $(location {w}) && ".format(w = window_file) if window_file else "") +
              ("p=$$($(execpath //test/coremark_joule/scripts:saif_window) --print-period --clk-period-from-sdc $(location {})) && ".format(clk_period) if sdc else "") +
              "$(location :{n}_bin) $(location {c}) $(location {n}.{t}) {s} {p} {e}".format(
                  n = name,
                  c = capture,
                  t = trace,
                  s = "$$s" if window_file else window_start,
                  p = "$$p" if sdc else clk_period,
                  e = "$$e" if window_file else window_end,
              ) + (" --stubs-vcd=$(location {n}_stubs.vcd) --stub-inputs-json=$(location {n}_stub_inputs.json)".format(n = name) if stubs else "") +
              (" --outputs-json=$(location {}_outputs.json)".format(name) if count_outputs else "") +
              (" --from-reset-json=$(location {}_from_reset.json)".format(name) if compare_from_reset else ""),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:saif_window"] if sdc else [],
        visibility = visibility,
    )

def _capture_scope(root, path, owners):
    """Where a unit's wrapper is in the capture: below each enclosing
    wrapped unit's `rtl`, the RTL behind its wrapper."""
    scope = root
    done = ""
    for o in sorted([o for o in owners if path.startswith(o + "/")], key = len) + [path]:
        scope += ".rtl." + o[len(done):].lstrip("/").replace("/", ".")
        done = o
    return scope

def shard_replays(
        name,
        top,
        netlist,
        rtl,
        units,
        capture,
        capture_scope,
        clk_period,
        window_start = "0",
        window_file = None,
        cuts = {},
        two_level = False,
        count_outputs = [],
        compare_from_reset = [],
        scopes = {},
        power_srcs = {},
        clock_ports = ["clock"],
        cells = "//test/coremark_joule/rtl:asap7_stdcells",
        copts = ["-O2"],
        vopts = [],
        tags = ["manual"],
        visibility = None):
    """The power shards' one SAIF from replays of one RTL capture.

    One replay (shard_replay) per simulation shard, and their SAIFs
    merged (shard_saif_merge) into `<name>.saif`, the parent's replay's
    scope TOP/<name>_parent/dut the root that stage_power_shards' saif_scope
    names. A simulation shard is the parent, each hardened unit, or a
    module cut out of one to keep a simulation small: `cuts` lists, per
    unit, instance paths below it of kept modules (a module of its own in
    the unit's netlist and in the RTL, with the same ports); the unit is
    then replayed with them cut out, each of them on its own. The power
    shards stay one per unit; every simulation shard's subtree is grafted
    at its path, so each unit's shard reads its whole subtree.

    With `two_level`, each cut is replayed from its unit's replay instead
    of from the capture (scripts/replay_gen.py, "two-level replay"): the
    unit's replay, its SAIF as ever, also records every port of the cut's
    stub, `<name>_<unit>_stubs.vcd`, the inputs a hierarchical global
    route punched into the cut's netlist among them, and the cut is
    replayed from that. Its outputs are still checked against the
    capture's values, which its stub took from the capture; its punched
    inputs, which the capture has no value for, are the unit netlist's.

    The capture is the caller's: an RTL simulation of shard_capture_rtl()'s
    wrapped RTL with its trace configuration, a VCD.

    Args:
      name: target name.
      top: the parent's module.
      netlist: the parent's netlist.
      rtl: one file of every RTL module, unwrapped.
      units: {instance path below the parent: (module, netlist)}, the
        hardened units, nested ones included.
      capture: the capture VCD.
      capture_scope: the parent's wrapper scope in it, dotted.
      clk_period: the clock period in capture time units, or the
        design's constraints.sdc (shard_replay's).
      window_start: the capture time the SAIFs start at.
      window_file: a file of "<start> <end>" instead
        (saif_window.py --window-out).
      cuts: {unit path, "" for the parent: [instance paths below it]}.
        A cut may hold no hardened unit.
      two_level: replay the cuts from their units' replays (above):
        needed when a cut's netlist has punched ports, which the capture
        cannot drive and replay_gen refuses in a cut replayed from it.
      count_outputs: [cut paths from the parent], two_level only: cuts
        whose level 2 counts the outputs that differ from the RTL instead
        of failing on the first (shard_replay's count_outputs), their SAIF
        taken as produced; `<name>_<slug>_outputs.json` says how much
        differed.
      compare_from_reset: [cut paths from the parent], two_level only:
        cuts whose level 2 compares outputs from the cycle after the
        captured reset first falls (shard_replay's compare_from_reset).
      scopes: as stage_power_shards'.
      power_srcs: {unit path, "" for the parent: its flow stage target}:
        each such unit's power shard on its own replay's SAIF alone,
        `<name>_power_<slug>` with its per-module rows (power_shard's
        units), before the merged SAIF exists. Not for a unit with cuts,
        whose own replay holds the cut modules as stubs.
      clock_ports: the ports the SDCs put the one clock on.
      cells: the standard-cell models.
      copts: the harnesses' C++ options.
      vopts: Verilator's options.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    paths = sorted(units.keys())
    for u in power_srcs:
        if cuts.get(u):
            fail("shard_replays %s: %s has cuts; its own replay's SAIF is not its whole subtree" % (name, u or "the parent"))
    owners = [""] + paths
    for u, cs in cuts.items():
        if u not in owners:
            fail("shard_replays %s: cuts in %s, which is no unit" % (name, u))
        for c in cs:
            inside = [p for p in paths if p.startswith((u + "/" if u else "") + c + "/")]
            if inside:
                fail("shard_replays %s: the cut %s holds the units %s" % (name, c, inside))

    cut_paths = [(u + "/" if u else "") + c for u, cs in cuts.items() for c in cs]
    for what, listed in [
        ("count_outputs", count_outputs),
        ("compare_from_reset", compare_from_reset),
    ]:
        for p in listed:
            if not two_level or p not in cut_paths:
                fail("shard_replays %s: %s %s is no cut of a two-level replay" % (name, what, p))

    # path from the parent: (top, netlist, path in the unit, children,
    # the unit a cut is cut from or None)
    sims = {}
    all_paths = paths + [(u + "/" if u else "") + c for u, cs in cuts.items() for c in cs]
    for u in owners:
        module, net = (top, netlist) if u == "" else units[u]
        prefix = u + "/" if u else ""
        kids = [p for p in paths if p != u and _shard_parent(p, paths) == u]
        kids += [prefix + c for c in cuts.get(u, [])]
        sims[u] = (module, net, "", kids, None)
        for c in cuts.get(u, []):
            sims[prefix + c] = (module, net, c, [], u)
    targets = {}
    for full, (module, net, sub, kids, owner) in sims.items():
        slug = "parent" if full == "" else _shard_slug(full)
        replay = "%s_%s" % (name, slug)
        base = full + "/" if full else ""
        level2 = two_level and owner != None
        level1 = "%s_%s" % (name, "parent" if owner == "" else _shard_slug(owner or ""))
        shard_replay(
            name = replay,
            capture = ":%s_stubs.vcd" % level1 if level2 else capture,
            capture_scope = "TOP.%s.dut.%s" % (level1, sub.replace("/", ".")) if level2 else (_capture_scope(capture_scope, full, owners) if full else capture_scope),
            stub_map = ":%s_stubs.json" % level1 if level2 else None,
            stubs = two_level and sub == "" and bool(cuts.get(full)),
            count_outputs = full in count_outputs,
            compare_from_reset = full in compare_from_reset,
            cells = cells,
            children = {
                k[len(base):]: _capture_scope(capture_scope, k, owners)
                for k in kids
            },
            clk_period = clk_period,
            clock_ports = clock_ports,
            copts = copts,
            netlist = net,
            path = sub,
            rtl = rtl,
            tags = tags,
            top = module,
            vopts = vopts,
            window_file = window_file,
            window_start = window_start,
        )
        targets[full] = replay
        if sub == "" and full in power_srcs:
            power_shard(
                name = "%s_power_%s" % (name, slug),
                children = [k[len(base):] for k in kids if k in paths],
                saif = ":%s.saif" % replay,
                saif_scope = "TOP/%s/dut" % replay,
                src = power_srcs[full],
                tags = tags,
                unit = full,
                units = True,
            )
    shard_saif_merge(
        name = name,
        clocks = clock_ports,
        parent_saif = ":%s.saif" % targets[""],
        saif_scope = "TOP/%s_parent/dut" % name,
        scopes = scopes,
        sources = {p: "TOP/%s/dut" % targets[p] for p in all_paths},
        units = {p: ":%s.saif" % targets[p] for p in all_paths},
        tags = tags,
        visibility = visibility,
    )

def shard_capture_rtl(name, rtl, top, paths, scope, tags = ["manual"]):
    """The RTL of a shards' capture: every simulation shard behind a wrapper
    of its ports (scripts/capture_wrap.py), `<name>.sv`, and the trace
    configuration that records those wrappers' ports alone,
    `<name>_trace.v` (tracing_on -levels 1 on each wrapper's scope).

    Args:
      name: target name.
      rtl: one file of every RTL module.
      top: the parent's module, wrapped too.
      paths: every simulation shard's instance path below `top`: the
        units, nested ones included, and the cuts.
      scope: the parent's instance in the simulation, dotted below
        Verilator's root (mini_top, cm_soc.outer.soc.core_with_l2).
      tags: forwarded; manual.
    """
    native.genrule(
        name = name,
        srcs = [rtl],
        outs = [name + ".sv"],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:capture_wrap) $< $@",
            "--unit " + top,
            "--top " + top,
        ] + ["--path " + p for p in sorted(paths)]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:capture_wrap"],
    )
    owners = sorted(paths)
    scopes = [scope] + [_capture_scope(scope, p, owners) for p in owners]
    native.genrule(
        name = name + "_trace",
        outs = [name + "_trace.v"],
        # a configuration in a .v file: verilog_library takes no .vlt
        cmd = "printf '`verilator_config\\ntracing_off -scope \"*\"\\n%s' > $@" % "".join([
            "tracing_on -scope \"%s\" -levels 1\\n" % sc
            for sc in scopes
        ]),
        tags = tags,
    )

def stage_power_shards(
        name,
        parent,
        shards,
        saif,
        saif_scope,
        stage = "grt",
        parasitics = "global_routing",
        min_annotation = 0.9,
        scopes = {},
        units = False,
        tags = ["manual"],
        visibility = None):
    """A hierarchical design's power as the sum of one report per unit.

    In the parent's ODB a hardened block is its abstract: pin loads and
    declared leakage, no internal activity, so stage_power() on the
    parent leaves every block out, and one process holding every block
    would not fit memory on XiangShan anyway. Here each unit is reported
    on its own ODB, the SAIF read at its own scope, and the shards are
    summed (scripts/merge_power_shards.py): a block's register file is
    a unit of its own, inside the block's shard.

    Outputs, beside stage_power()'s so either feeds coremark_per_joule:
    `<name>_vectorless.json` and `<name>_vector_driven.json`, in
    report_power's JSON shape, and `<name>_shards.json`, each shard's
    totals and SAIF annotation rate. The vectorless sum is not a flat
    vectorless number: in a block's own shard every input port is a root
    of OpenSTA's activity propagation and gets its default activity. It
    is there for the binding check, shard by shard.

    Proven on a toy against a flat report of the same physical design
    (test/coremark_joule/power_shards): leakage equal, internal power
    within 0.06 %, switching on every net inside a unit equal; the nets
    that cross a block boundary are the residual (sum_test.py).

    The sum fails when any shard's SAIF-driven report equals its
    vectorless one, or the SAIF annotated less than `min_annotation` of
    its pins: the SAIF did not bind at that shard's scope.

    Args:
      name: target name.
      parent: the parent's flow stage target, e.g. ":XSTile_grt".
      shards: {instance path from the parent's root: the unit's own flow
        stage target}. A path under another is nested in it: a register
        file inside a block is `<block path>/<file path in the block>`.
        Every target, the parent's too, is a flow of the calling
        package: an orfs_run reads its results from there.
      saif: the .saif label in which every shard's subtree is its own
        gates: shard_saif_merge() of one simulation per shard, each
        unit's netlist written with grt_netlist(saif_names = True).
      saif_scope: the parent's scope in the SAIF; a unit's scope is its
        parent unit's, a `/` and its path there, unless `scopes` says
        otherwise.
      units: also `<name>_units.json`, the per-module breakdown across
        the shards: every module instance of every unit's ODB, at its
        path from the parent's root, and each unit's flat remainder
        (stage_power_units on a design too large for one ODB).
      scopes: {path: scope} where the SAIF has a unit elsewhere. A `/`
        the unit's parent unit flattened into one instance name is
        `__SL__` in the SAIF (grt_netlist(saif_names = True)): a parent
        unit's shard reports where its ODB has each child, and the sum
        fails naming the scope a child should have read.
      stage: which stage; must match every target.
      parasitics: estimate_parasitics' source, global_routing as
        stage_power's; placement only for the toy's proof.
      min_annotation: the least fraction of a shard's pins the SAIF must
        annotate. A scope that names the wrong instance still binds
        wherever a cell name there matches one here, and generated names
        (`_360_`) match across units: on the toy, BlockA's shard read at
        the parent's scope annotated 525 of its 2,309 pins, and its
        SAIF-driven report moved. Equal reports alone do not catch that.
      tags: forwarded; manual.
      visibility: forwarded.
    """
    paths = sorted(shards.keys())
    for p in paths:
        if not p or p.startswith("/") or p.endswith("/") or "//" in p:
            fail("stage_power_shards %s: '%s' is not an instance path" % (name, p))
    units = [""] + paths
    targets = []
    slugs = {}
    for unit in units:
        slug = "parent" if unit == "" else _shard_slug(unit)
        if slug in slugs:
            fail("stage_power_shards %s: '%s' and '%s' share the target name %s" % (name, slugs[slug], unit, slug))
        slugs[slug] = unit
        prefix = unit + "/" if unit else ""
        children = [
            p[len(prefix):]
            for p in paths
            if p != unit and _shard_parent(p, paths) == unit
        ]
        shard = "%s_%s" % (name, slug)
        power_shard(
            name = shard,
            src = parent if unit == "" else shards[unit],
            saif = saif,
            saif_scope = _shard_scope(saif_scope, unit, paths, scopes),
            unit = unit,
            children = children,
            stage = stage,
            parasitics = parasitics,
            units = units,
            tags = tags,
        )
        targets.append(":%s.json" % shard)

    vectorless = name + "_vectorless.json"
    vector_driven = name + "_vector_driven.json"
    report = name + "_shards.json"
    unit_targets = [t.removesuffix(".json") + "_units.json" for t in targets] if units else []
    native.genrule(
        name = name,
        srcs = targets + unit_targets,
        outs = [
            vectorless,
            vector_driven,
            report,
        ] + ([name + "_units.json"] if units else []),
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:merge_power_shards)",
            "--vectorless $(location {})".format(vectorless),
            "--vector-driven $(location {})".format(vector_driven),
            "--report $(location {})".format(report),
            "--min-annotation {}".format(min_annotation),
        ] + ["--units-out $(location {}_units.json)".format(name)] * (1 if units else 0) + [
            "--units $(location {})".format(t)
            for t in unit_targets
        ] + ["$(location {})".format(t) for t in targets]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:merge_power_shards"],
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

def dup_inst_probe(name, src, nets, stage = "grt", tags = ["manual"], visibility = None):
    """Where a duplicate instance name in a written netlist came from.

    odb refuses a duplicate dbInst name, so a netlist that has one was
    given it on the way out. This reports the ODB names and module
    assignments of the instances on the nets involved, so the claim is
    measured rather than inferred.
    """
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".txt"],
        script = "//test/coremark_joule/flow:dup_inst_probe.tcl",
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "NETS": " ".join(nets),
            "OUT": "$(location {}.txt)".format(name),
        },
        tags = tags,
        visibility = visibility,
    )

def period_probe(name, src, stage = "grt", tags = ["manual"], visibility = None):
    """The minimum clock period, from register-to-register paths only.

    §3.8: only reg2reg can fail timing closure, and every path touching a
    port is an optimisation target whose budget is this study's own
    assumption about a register outside the pin. A frequency derived
    from the overall WNS would be limited by that assumption rather than
    by the design, so the probe reports both and the study quotes the
    reg2reg one.
    """
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".txt"],
        script = "//test/coremark_joule/flow:period_probe.tcl",
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "OUT": "$(location {}.txt)".format(name),
        },
        tags = tags,
        visibility = visibility,
    )

def flop_power_probe(name, src, saif, saif_scope, stage = "synth", tags = ["manual"], visibility = None):
    """One flop's internal-power arithmetic, from OpenSTA's own debug lines.

    §4.8's cross-check found the Sequential group's internal power not
    scaling with frequency on a byte-identical netlist; this names the
    term. See flow/flop_power_probe.tcl.
    """
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".txt"],
        script = "//test/coremark_joule/flow:flop_power_probe.tcl",
        data = [saif],
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "SAIF_STIMULI": "$(location {})".format(saif),
            "SAIF_SCOPE": saif_scope,
            "OUT": "$(location {}.txt)".format(name),
        },
        tags = tags,
        visibility = visibility,
    )

def physical_probe(name, src, stage = "grt", ge_cell = "NAND2xp33_ASAP7_75t_R", tags = ["manual"], visibility = None):
    """The measured side of the literature table (§4.9).

    Standard-cell area, gate equivalents against `ge_cell`, flop and
    macro counts, die and core area, the SDC period and the reg2reg
    slack, all from one stage's ODB. Gate equivalents are the
    standard-cell area over the NAND2's; the cell is a parameter because
    the papers being compared against rarely say which NAND they meant,
    and its area is written into the output so the division can be
    redone against another.
    """
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".txt"],
        script = "//test/coremark_joule/flow:physical_probe.tcl",
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "GE_CELL": ge_cell,
            "OUT": "$(location {}.txt)".format(name),
        },
        tags = tags,
        visibility = visibility,
    )

def census_probe(name, src, stage = "synth", tags = ["manual"], visibility = None):
    """Leaf instances and area under every module instance in a stage's ODB.

    The first question of a hierarchical flow is what is big. A kept
    module that survives into the ODB can be hardened as a macro; one
    that does not has to be kept first. The probe walks the module tree
    the ODB has and reports each module's own leaf count and area and
    the total under it, so containers read as large as their children.
    """
    orfs_run(
        name = name,
        src = src,
        outs = [name + ".txt"],
        script = "//test/coremark_joule/flow:census_probe.tcl",
        user_arguments = {
            "STAGE_STEM": STAGE_STEM[stage],
            "OUT": "$(location {}.txt)".format(name),
        },
        tags = tags,
        visibility = visibility,
    )
