"""What ORFS's design population actually exercises, and what it does not.

The study's first claim is that the regime it measures -- congested,
routing the top of the metal stack, wire-delay dominated -- is not
represented by any design ORFS ships, so a timing-policy default tuned
against that population was tuned outside the regime where it matters.

That claim is only worth making if it is derived rather than asserted, and
if it re-derives itself when ORFS moves. So every number here comes out of
ORFS's own files at build time:

  * the design table from the parsed DESIGNS dict, the same one the
    config.mk DSL builds flow targets from;
  * the platform defaults from flow/platforms/<pdk>/config.mk, so
    "the design does not override this" is measured against the value
    that actually applies;
  * the layer resistance spread from flow/platforms/<pdk>/setRC.tcl;
  * the flow-wide default of a policy variable from ORFS's own parsed
    variables.yaml -- the same @orfs_variable_metadata dict the stage
    argument tables are built from, so "the default is 100" is the value
    bazel-orfs itself validates against -- and its call sites from the
    stage scripts that read it.

Nothing is hardcoded that ORFS states somewhere.
"""

import argparse
import json
import os
import re
from pathlib import Path

# Timing/repair policy variables. A design setting one of these is
# carrying per-design timing lore; the point of the table is how few
# derive it and how many restate the default.
POLICY_VARS = [
    "TNS_END_PERCENT",
    "SETUP_SLACK_MARGIN",
    "HOLD_SLACK_MARGIN",
    "SETUP_MOVE_SEQUENCE",
    "ENABLE_PLACE_REPAIR_TIMING",
    "SKIP_CTS_REPAIR_TIMING",
    "SKIP_INCREMENTAL_REPAIR",
    "SKIP_LAST_GASP",
    "SKIP_GATE_CLONING",
    "SKIP_PIN_SWAP",
    "SKIP_BUFFER_REMOVAL",
    "SKIP_VT_SWAP",
    "OPT_POST_GRT_WNS",
    "RECOVER_POWER",
    "MATCH_CELL_FOOTPRINT",
    "REMOVE_ABC_BUFFERS",
]

# Variables that decide whether a design can reach the top of the stack
# at all, and how hard routing has to work to get there.
ROUTING_VARS = [
    "MIN_ROUTING_LAYER",
    "MAX_ROUTING_LAYER",
    "MIN_CLK_ROUTING_LAYER",
    "ROUTING_LAYER_ADJUSTMENT",
    "ENABLE_RESISTANCE_AWARE",
]

# Shape, for reading the design table: is this a big design or a toy?
SHAPE_VARS = [
    "CORE_UTILIZATION",
    "CORE_AREA",
    "DIE_AREA",
    "PLACE_DENSITY",
    "PLACE_DENSITY_LB_ADDON",
    "CORE_MARGIN",
]

_EXPORT_RE = re.compile(
    r"^\s*export\s+([A-Z0-9_]+)\s*(\?=|=|\+=)\s*(.*?)\s*$",
)

_SET_WIRE_RC_RE = re.compile(r"set_wire_rc\s+(.*)$")


def _tcl_flags(args):
    """`-flag value` pairs out of a Tcl command's argument text.

    Order-independent on purpose. A regex pinning `-layer` immediately
    before `-resistance` matches asap7's setRC.tcl and silently matches
    nothing on a platform that writes the same flags in another order --
    which yields a complete, plausible, empty layer table rather than an
    error. Every caller here treats an empty parse as a failure.
    """
    toks = args.split()
    out = {}
    i = 0
    while i < len(toks):
        if toks[i].startswith("-"):
            name = toks[i].lstrip("-")
            if i + 1 < len(toks) and not toks[i + 1].startswith("-"):
                out[name] = toks[i + 1]
                i += 2
                continue
            out[name] = True
        i += 1
    return out


def parse_makefile_exports(path):
    """Every `export VAR = value` in a config.mk, last assignment winning.

    `?=` and `=` are both recorded as the effective default, since a
    platform config.mk is included before any design override and a
    design that does not set the variable gets this value either way.
    The distinction is kept so the table can say which are overridable.
    """
    out = {}
    for line in Path(path).read_text().splitlines():
        m = _EXPORT_RE.match(line)
        if not m:
            continue
        name, op, value = m.group(1), m.group(2), m.group(3)
        # Strip a trailing comment, but not a '#' inside a $(...) call.
        if "#" in value and "$(" not in value.split("#", 1)[0]:
            value = value.split("#", 1)[0].strip()
        out[name] = {"value": value, "op": op}
    return out


def parse_set_layer_rc(path):
    """Per-layer resistance and capacitance from a platform setRC.tcl.

    Returns the routing layers only (via rows carry -via, not -layer),
    in file order, which is bottom-to-top for every platform in tree.
    """
    layers = []
    wire_rc = []
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("set_layer_rc"):
            flags = _tcl_flags(stripped[len("set_layer_rc"):])
            # Via rows carry -via, not -layer, and are not routing layers.
            if "layer" in flags and "via" not in flags:
                layers.append(
                    {
                        "layer": flags["layer"],
                        "resistance": float(flags["resistance"])
                        if "resistance" in flags
                        else None,
                        "capacitance": float(flags["capacitance"])
                        if "capacitance" in flags
                        else None,
                    }
                )
            continue
        m = _SET_WIRE_RC_RE.search(stripped)
        if m:
            wire_rc.append(_parse_wire_rc(m.group(1)))
    return layers, wire_rc


def _parse_wire_rc(args):
    """How a platform prices "an average wire".

    Two spellings exist in tree and the difference is the whole point of
    the RC arm of the study: `-layer <name>` names a layer and inherits
    its RC, while `-resistance/-capacitance` pins an absolute constant
    that no longer tracks the stack it was derived from.
    """
    flags = _tcl_flags(args)
    out = {
        "signal": flags.get("signal") is True,
        "clock": flags.get("clock") is True,
        "kind": "layer" if "layer" in flags else "absolute",
    }
    for key in ("layer", "resistance", "capacitance"):
        if key in flags:
            out[key] = flags[key]
    return out


def resistance_spread(layers):
    """The M1-to-top resistance ratio: the "8x" the study leans on."""
    if not layers:
        return None
    rs = [layer["resistance"] for layer in layers if layer["resistance"]]
    if not rs:
        return None
    return {
        "bottom": layers[0]["layer"],
        "bottom_resistance": rs[0],
        "top": layers[-1]["layer"],
        "top_resistance": rs[-1],
        "min_resistance": min(rs),
        "max_resistance": max(rs),
        "ratio": max(rs) / min(rs),
    }


def routable_window(layers, min_layer, max_layer):
    """The layers a signal net is actually allowed to use.

    The full-stack spread is the wrong number twice over. It includes
    layers routing never reaches -- asap7 caps signals at M7 of nine --
    and on sky130hd it is dominated by `li1`, a local interconnect whose
    resistance is three orders above met5 and which no global net routes
    on. The spread that bears on a pre-route timing estimate is the one
    across the window the router may choose from.
    """
    names = [layer["layer"] for layer in layers]
    lo = names.index(min_layer) if min_layer in names else 0
    hi = names.index(max_layer) if max_layer in names else len(names) - 1
    if hi < lo:
        return []
    return layers[lo:hi + 1]


def wire_rc_mispricing(layers, wire_rc, window):
    """How far an absolute `set_wire_rc` sits from the layers in use.

    This is the study's mechanism, available without running anything: a
    pre-route estimate prices every net at one resistance, and a net that
    routes high is charged the constant instead of its own layer. The
    ratio is how many times too resistive that makes the cheapest layer
    the router could have given it -- i.e. how pessimistic the estimate
    is on exactly the nets that matter, the long ones that go up.
    """
    if not window:
        return None
    rs = [layer["resistance"] for layer in window if layer["resistance"]]
    if not rs:
        return None
    out = []
    for entry in wire_rc:
        if entry["kind"] != "absolute" or "resistance" not in entry:
            # A platform naming a layer inherits that layer's RC and has
            # nothing to misprice; sky130hd does this and asap7 does not.
            out.append(dict(entry, mispricing=None))
            continue
        r = float(entry["resistance"])
        out.append(
            dict(
                entry,
                mispricing={
                    "wire_rc_resistance": r,
                    "least_resistive_routable_layer": min(
                        window, key=lambda layer: layer["resistance"] or float("inf")
                    )["layer"],
                    "times_more_resistive_than_least": r / min(rs),
                    "times_less_resistive_than_most": max(rs) / r,
                },
            )
        )
    return out


def wire_rc_layer_equivalent(layers, wire_rc):
    """Which layer an absolute `set_wire_rc` is actually pricing.

    An absolute resistance is only readable next to the stack: the
    question a reviewer asks is "that constant corresponds to which
    layer?", and the answer is the bracketing pair. Returns None for a
    platform that names a layer, because there is nothing to infer.
    """
    out = []
    for entry in wire_rc:
        if entry["kind"] != "absolute" or "resistance" not in entry:
            out.append(dict(entry, equivalent=None))
            continue
        r = float(entry["resistance"])
        below = [layer for layer in layers if layer["resistance"] >= r]
        above = [layer for layer in layers if layer["resistance"] <= r]
        out.append(
            dict(
                entry,
                equivalent={
                    "at_or_below": below[-1]["layer"] if below else None,
                    "at_or_above": above[0]["layer"] if above else None,
                },
            )
        )
    return out


# The stage scripts that can repair timing, in flow order. Only
# Only `scripts/flow.tcl` is exported as an individual label by ORFS;
# the rest arrive through the //flow:makefile filegroup, so they are
# found beside flow.tcl in the runfiles tree rather than named as
# labels. A script missing from the tree is reported
# rather than skipped, because a silently empty call-site table would
# read exactly like "this knob has no call sites".
REPAIR_SCRIPTS = [
    "floorplan.tcl",
    "resize.tcl",
    "cts.tcl",
    "global_route.tcl",
    "final_report.tcl",
    "util.tcl",
]


def call_sites(scripts_dir, needle):
    """Every line of the stage scripts that mentions a policy knob.

    The study's claim about `TNS_END_PERCENT` is that one number reaches
    four stages of very different information quality, and that the one
    stage with route-aware timing bypasses it. That is a statement about
    call sites, so the call sites are extracted rather than described.
    """
    hits = []
    missing = []
    for name in REPAIR_SCRIPTS:
        path = Path(scripts_dir) / name
        if not path.exists():
            missing.append(name)
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if needle in line:
                hits.append(
                    {
                        "file": name,
                        "line": lineno,
                        "text": line.strip(),
                        "commented": line.strip().startswith("#"),
                    }
                )
    return {"hits": hits, "missing_scripts": missing}


def kv_list(values):
    """`name=value` pairs for the argparse-repeated platform options."""
    out = {}
    for item in values:
        if "=" not in item:
            raise SystemExit("expected <platform>=<path>, got %r" % item)
        name, path = item.split("=", 1)
        out[name] = path
    return out


def build_inventory(args):
    corpus = json.loads(Path(args.corpus).read_text())
    designs = corpus["designs"]
    platform_cfg = {
        name: parse_makefile_exports(path)
        for name, path in kv_list(args.platform_config).items()
    }
    setrc = {}
    for name, path in kv_list(args.setrc).items():
        layers, wire_rc = parse_set_layer_rc(path)
        # An empty layer table is the parser's own failure mode, and it
        # looks exactly like a platform with no RC data. Neither exists.
        if not layers:
            raise SystemExit(
                "%s: parsed no set_layer_rc routing layers out of %s"
                % (name, path)
            )
        if not wire_rc:
            raise SystemExit(
                "%s: parsed no set_wire_rc line out of %s" % (name, path)
            )
        cfg = platform_cfg.get(name, {})
        window = routable_window(
            layers,
            cfg.get("MIN_ROUTING_LAYER", {}).get("value"),
            cfg.get("MAX_ROUTING_LAYER", {}).get("value"),
        )
        setrc[name] = {
            "layers": layers,
            "wire_rc": wire_rc_mispricing(
                layers, wire_rc_layer_equivalent(layers, wire_rc), window
            ),
            "spread": resistance_spread(layers),
            "routable_window": [layer["layer"] for layer in window],
            "routable_spread": resistance_spread(window),
        }

    rows = []
    for key, design in sorted(designs.items()):
        platform = design.get("platform")
        if args.platform and platform not in args.platform:
            continue
        arguments = design.get("arguments", {})
        defaults = platform_cfg.get(platform, {})

        def effective(var):
            """What the design runs with, and where that value came from."""
            if var in arguments:
                return {"value": arguments[var], "source": "design"}
            if var in defaults:
                return {"value": defaults[var]["value"], "source": "platform"}
            return {"value": None, "source": "flow-default"}

        # The mispricing a *design* sees, not the platform default one.
        # A design that raises MAX_ROUTING_LAYER widens its own routable
        # window, so the constant it is charged sits further from the
        # layers it can actually use -- which is the whole reason a
        # top-metal design is where the pessimism shows up.
        rc = setrc.get(platform)
        design_rc = None
        if rc:
            window = routable_window(
                rc["layers"],
                effective("MIN_ROUTING_LAYER")["value"],
                effective("MAX_ROUTING_LAYER")["value"],
            )
            design_rc = {
                "routable_window": [layer["layer"] for layer in window],
                "routable_spread": resistance_spread(window),
                "wire_rc": wire_rc_mispricing(rc["layers"], rc["wire_rc"], window),
            }

        rows.append(
            {
                "key": key,
                "rc": design_rc,
                "platform": platform,
                "design": key.split("/", 1)[1] if "/" in key else key,
                "design_name": design.get("name"),
                "has_macros": bool(design.get("blocks"))
                or any(
                    k in arguments
                    for k in ("ADDITIONAL_LEFS", "ADDITIONAL_LIBS", "AUTO_MEMORIES")
                ),
                "routing": {var: effective(var) for var in ROUTING_VARS},
                "policy": {
                    var: effective(var)
                    for var in POLICY_VARS
                    # Only report a policy knob the design or its platform
                    # actually sets; a flow-default row for every variable
                    # on every design is noise, not inventory.
                    if var in arguments or var in defaults
                },
                "shape": {
                    var: arguments[var] for var in SHAPE_VARS if var in arguments
                },
            }
        )

    inventory = {
        "designs": rows,
        "platforms": {
            name: {
                "routing": {
                    var: cfg[var]["value"] for var in ROUTING_VARS if var in cfg
                },
                "policy": {
                    var: cfg[var]["value"] for var in POLICY_VARS if var in cfg
                },
                "place_density": cfg.get("PLACE_DENSITY", {}).get("value"),
                "rc": setrc.get(name),
            }
            for name, cfg in platform_cfg.items()
        },
    }

    metadata = corpus.get("variable_metadata", {})
    inventory["flow_defaults"] = {
        var: {
            key: value
            for key, value in metadata[var].items()
            # The description is prose and would dominate the file; the
            # study needs the default and where it is allowed to act.
            if key in ("default", "stages")
        }
        for var in POLICY_VARS
        if var in metadata
    }
    # A policy variable ORFS no longer declares is reported, not dropped:
    # a knob that vanished upstream is a finding about a study still
    # sweeping it.
    inventory["flow_defaults_missing"] = sorted(
        var for var in POLICY_VARS if var not in metadata
    )
    if args.scripts_dir:
        inventory["call_sites"] = {
            needle: call_sites(args.scripts_dir, needle)
            for needle in ("TNS_END_PERCENT", "repair_tns", "repair_timing")
        }
    return inventory


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--corpus",
        required=True,
        help="json.encode of DESIGNS plus ORFS's parsed variable metadata",
    )
    ap.add_argument(
        "--platform-config",
        action="append",
        default=[],
        metavar="PLATFORM=PATH",
        help="flow/platforms/<pdk>/config.mk",
    )
    ap.add_argument(
        "--setrc",
        action="append",
        default=[],
        metavar="PLATFORM=PATH",
        help="flow/platforms/<pdk>/setRC.tcl",
    )
    ap.add_argument(
        "--scripts-dir",
        help="flow/scripts/, or any file inside it (e.g. flow.tcl)",
    )
    ap.add_argument(
        "--platform",
        action="append",
        help="restrict the design table to these platforms",
    )
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args()
    if args.scripts_dir and not Path(args.scripts_dir).is_dir():
        # Given a file inside scripts/ -- the only individually-labelled
        # entry point ORFS exports -- use its directory.
        args.scripts_dir = str(Path(args.scripts_dir).parent)

    inventory = build_inventory(args)

    out = Path(args.out_json)
    if not out.is_absolute():
        # Under `bazelisk run` the working directory is the runfiles
        # tree, so a relative output would land in the sandbox and be
        # thrown away. Resolve against the workspace, which is where the
        # checked-in result belongs.
        workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
        if workspace:
            out = Path(workspace) / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
