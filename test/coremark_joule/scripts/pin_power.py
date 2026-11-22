#!/usr/bin/env python3
"""Pin a design's power measured in shards into the source tree.

    bazelisk run //test/coremark_joule/designs/asap7/xiangshan:pin_power

XiangShan's power is hours of simulation and one report_power per unit
(flow/power.bzl's shard_replays and stage_power_shards). As results.json
pins every point so that rendering the paper needs no flow, this pins
the measurement behind XiangShan's point: one file, role-named, beside
the design, with

  vectorless, vector_driven   the summed reports, stage_power()'s shape
  shards                      per unit: its path, scope, annotation rate
                              and own totals (merge_power_shards.py's
                              report)
  units                       the per-module breakdown, when measured
  provenance                  how and on what it was measured: the
                              bazel-orfs commit, the date, the clock
                              period (the SDC's) and each unit's minimum
                              period at global route (min_period_ps: the
                              SDC period minus its worst reg2reg slack,
                              from <unit>_kpi; null for a unit with no
                              KPI), the capture's cycles and the SAIF
                              window, the method, the machine class
                              (cores, GB of memory), `partial` with a
                              reason when not every unit is in, and
                              `pass`: first, or final

and nothing that names a machine, a person or a path. A pinned file is
checked in CI (power_pin_test.py); a fresh run is compared with it by
`check` (this script's --check), which prints the differences per shard
and leaves re-pinning to the human.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

METHOD = (
    "one RTL capture of every unit's ports (the SoC's RTL, the surgered core "
    "below XSTile), each unit's global-route netlist replayed alone from it "
    "and checked against it every clock phase, the replays' SAIFs merged, one "
    "report_power per unit on its own global-route ODB, summed"
)

FIELDS = [
    "bazel_orfs_commit",
    "date",
    "period_ps",
    "min_period_ps",
    "cycles",
    "saif_window_ps",
    "method",
    "machine",
    "partial",
    "pass",
    "replays",
]


def read_json(path):
    with open(path) as f:
        return json.load(f)


def machine():
    """The machine class: cores and memory, nothing that names it."""
    gb = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    gb = round(int(line.split()[1]) / 1024 / 1024)
    except OSError:
        pass
    return {"cores": os.cpu_count(), "memory_gb": gb}


def commit(root):
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return out if re.fullmatch(r"[0-9a-f]{40}", out) else None


def min_periods(kpis, units):
    """{unit: reg2reg min period in ps, or None}: every shard's unit,
    from its <unit>_kpi.txt (`reg2reg min period N ps`) where given."""
    out = {u: None for u in units}
    for spec in kpis or []:
        unit, _, path = spec.partition("=")
        if unit not in out:
            raise ValueError(
                "--kpi for {}, which is not a shard".format(unit or "(parent)")
            )
        with open(path) as f:
            m = re.search(r"^reg2reg min period (\d+) ps", f.read(), re.M)
        if not m:
            raise ValueError("{}: no `reg2reg min period` line".format(path))
        out[unit] = int(m.group(1))
    return out


def derived(period, min_ps, vector_driven):
    """What follows from the measured numbers, labelled as such: each
    unit's reg2reg WNS (the SDC period less its minimum period), the
    design's period (the parent's minimum period), the dynamic energy per
    cycle (the SAIF's activity is at the SDC's clock: dynamic power times
    the SDC period) and the power that energy gives at the design's
    period, leakage added at its own value."""
    total = vector_driven["Total"]
    dynamic_w = total["internal"] + total["switching"]
    energy_j = dynamic_w * period * 1e-12
    design = min_ps.get("")
    out = {
        "wns_ps": {
            u: (period - p if p is not None else None) for u, p in min_ps.items()
        },
        "design_period_ps": design,
        "dynamic_w_at_sdc_period": dynamic_w,
        "dynamic_energy_per_cycle_j": energy_j,
        "leakage_w": total["leakage"],
    }
    if design:
        out["power_w_at_design_period"] = energy_j / (design * 1e-12) + total["leakage"]
    return out


def replays(units, two_level, reports, stub_inputs, counted=None):
    """{unit: how its activity was replayed}: "whole" (its netlist from
    the capture, its ports checked), or "two-level" (its remainder with
    its cuts as stubs, then each cut from the remainder's record of its
    inputs), with the checked bits the netlist fixes (not compared) and
    the stub inputs that differ from the RTL (not required to match:
    each cut's outputs are checked)."""
    out = {u: {"method": "whole"} for u in units}
    for spec in two_level or []:
        unit, _, _ = spec.partition("=")
        out[unit] = {"method": "two-level", "not_compared_bits": 0}
    for spec in reports or []:
        unit, _, path = spec.partition("=")
        with open(path) as f:
            out[unit]["not_compared_bits"] = out[unit].get(
                "not_compared_bits", 0
            ) + len(json.load(f).get("not_compared", []))
    for spec in stub_inputs or []:
        unit, _, path = spec.partition("=")
        with open(path) as f:
            s = json.load(f)
        out[unit]["stub_inputs_differing"] = {
            "signals": s["signals"],
            "cycles": s["cycles"],
        }
    # a cut replayed in count mode: its outputs are not all equal to the
    # RTL's; how many differ, from when, which first
    for spec in counted or []:
        unit, _, rest = spec.partition("=")
        piece, _, path = rest.partition(":")
        with open(path) as f:
            c = json.load(f)
        out[unit].setdefault("outputs_differing", []).append(
            {
                "piece": piece,
                "signals": c["signals"],
                "cycles": c["cycles"],
                "first_cycle": c.get("first_cycle"),
                "first_signal": c.get("first_signal"),
                "top": [
                    {k: x[k] for k in ("signal", "cycles", "first_cycle") if k in x}
                    for x in c.get("top", [])[:10]
                ],
            }
        )
    return out


def pinned(args, root):
    period = int(
        re.search(
            r"^\s*set\s+clk_period\s+(\d+)", open(args.constraints).read(), re.M
        ).group(1)
    )
    with open(args.cycles) as f:
        cycles = int(f.readline())
    with open(args.window) as f:
        window = [int(x) for x in f.read().split()]
    report = read_json(args.report)
    out = {
        "provenance": {
            "bazel_orfs_commit": commit(root),
            "date": datetime.date.today().isoformat(),
            "period_ps": period,
            "min_period_ps": min_periods(
                args.kpi, [s["unit"] for s in report["shards"]]
            ),
            "derived": derived(
                period,
                min_periods(args.kpi, [s["unit"] for s in report["shards"]]),
                read_json(args.vector_driven),
            ),
            "cycles": cycles,
            "saif_window_ps": window,
            "method": METHOD,
            "machine": machine(),
            "partial": args.partial or False,
            "pass": args.pass_,
            "replays": replays(
                [s["unit"] for s in report["shards"]],
                args.two_level,
                args.replay_report,
                args.stub_inputs,
                args.counted,
            ),
            "notes": args.note or [],
        },
        "vectorless": read_json(args.vectorless),
        "vector_driven": read_json(args.vector_driven),
        "shards": report["shards"],
    }
    if args.units:
        out["units"] = read_json(args.units)
    return out


def differences(old, new, tolerance=1e-6):
    """Lines saying where a fresh run differs from the pinned one."""
    lines = []
    for arm in ("vectorless", "vector_driven"):
        for k, v in new[arm]["Total"].items():
            o = old[arm]["Total"].get(k)
            if o is None or abs(v - o) > tolerance * max(abs(o), 1e-12):
                lines.append("total {} {}: pinned {} fresh {}".format(arm, k, o, v))
    olds = {s["unit"]: s for s in old["shards"]}
    for s in new["shards"]:
        o = olds.pop(s["unit"], None)
        if o is None:
            lines.append("shard {}: not pinned".format(s["unit"] or "(parent)"))
            continue
        for arm in ("vectorless", "vector_driven"):
            for k, v in s[arm].items():
                if abs(v - o[arm][k]) > tolerance * max(abs(o[arm][k]), 1e-12):
                    lines.append(
                        "shard {} {} {}: pinned {} fresh {}".format(
                            s["unit"] or "(parent)", arm, k, o[arm][k], v
                        )
                    )
        if s["annotation"] != o["annotation"]:
            lines.append(
                "shard {} annotation: pinned {} fresh {}".format(
                    s["unit"], o["annotation"], s["annotation"]
                )
            )
    for unit in olds:
        lines.append(
            "shard {}: pinned, not in the fresh run".format(unit or "(parent)")
        )
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--vectorless", required=True)
    parser.add_argument("--vector-driven", required=True)
    parser.add_argument(
        "--report", required=True, help="merge_power_shards.py's report"
    )
    parser.add_argument("--units")
    parser.add_argument("--cycles", required=True, help="the capture's cycles file")
    parser.add_argument(
        "--window", required=True, help="saif_window.py --window-out's file"
    )
    parser.add_argument("--constraints", required=True)
    parser.add_argument(
        "--kpi",
        action="append",
        help="UNIT=<unit>_kpi.txt, the unit's reg2reg minimum period at global route",
    )
    parser.add_argument("--partial", help="why this is not every unit, when it is not")
    parser.add_argument(
        "--two-level", action="append", help="UNIT=: a unit replayed two-level"
    )
    parser.add_argument(
        "--replay-report",
        action="append",
        help="UNIT=<replay>_report.json, its not-compared bits (repeatable)",
    )
    parser.add_argument(
        "--stub-inputs", action="append", help="UNIT=<level 1>_stub_inputs.json"
    )
    parser.add_argument(
        "--counted",
        action="append",
        help="UNIT=PIECE:<replay>_outputs.json, a cut replayed in count mode",
    )
    parser.add_argument(
        "--note", action="append", help="a caveat the numbers carry, said beside them"
    )
    parser.add_argument(
        "--pass",
        dest="pass_",
        required=True,
        help="which pass: first (numbers not yet read and corrected) or final; only final goes into results.json",
    )
    parser.add_argument(
        "--out", required=True, help="the pinned file, relative to the workspace"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare with the pinned file instead of writing it",
    )
    args = parser.parse_args(argv)
    root = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
    new = pinned(args, root)
    path = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
    if args.check:
        if not os.path.exists(path):
            print("pin_power: nothing pinned at {}".format(args.out))
            return 0
        lines = differences(read_json(path), new)
        print(
            "\n".join(lines) if lines else "pin_power: the fresh run is the pinned one"
        )
        return 0
    with open(path, "w") as f:
        json.dump(new, f, indent=1, sort_keys=True)
        f.write("\n")
    print(
        "pin_power: pinned {} ({} shards{})".format(
            args.out, len(new["shards"]), ", partial" if args.partial else ""
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
