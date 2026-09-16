#!/usr/bin/env python3
"""Project a windowed glitch measurement onto a whole benchmark iteration.

`glitch_count` counts transitions in one module over one window, in two
arms: the same window run at zero delay and run with the module's cell
delays annotated from SDF. The difference is the glitch (5.2). This
module turns that pair into the three numbers 5.2 quotes.

The window is not the iteration. It was chosen for having the most
multiplies in it, so its duty cycle is several times the iteration's,
and a glitch figure read straight off it would overstate the busy term
and understate the idle one. So the arms are reduced to *per-cycle
rates*, separately for the cycles the unit is working and the cycles it
is not, and those rates are reweighted by the duty cycle the whole
iteration actually has. Keeping the two rates apart is the point: a
unit with no operand isolation switches when it is idle, and in this
design that term is the larger of the two.

Converting transitions to power needs one stated approximation: that
the energy of a transition is the same wherever in the module it
happens. It is not exactly true -- a net with more fanout costs more --
but the alternative is a per-net capacitance the VCD does not carry,
and the quantity wanted is a ratio, where the error largely divides
out. Everything this module reports as power is therefore the module's
own measured dynamic power scaled by a measured transition ratio, and
is labelled as such.
"""

import argparse
import json
import sys


def rates(arm):
    """Per-cycle transition rates, busy and idle, for one arm."""
    busy_cycles = arm["busy_cycles"]
    idle_cycles = arm["cycles"] - busy_cycles
    if busy_cycles <= 0 or idle_cycles <= 0:
        raise ValueError("window has no busy or no idle cycles to rate")
    return {
        "busy": arm["transitions_subtree_busy"] / busy_cycles,
        "idle": arm["transitions_subtree_idle"] / idle_cycles,
    }


def project(zero, sdf, duty, cycles_per_iteration, unit_dynamic_w=None,
            core_power_w=None):
    """Reduce the two arms to rates and reweight them onto an iteration."""
    if zero["busy_bursts"] != sdf["busy_bursts"]:
        raise ValueError(
            "arms disagree on the operation count (%d vs %d): the annotated "
            "run did not execute the same instructions"
            % (zero["busy_bursts"], sdf["busy_bursts"])
        )
    rz, rs = rates(zero), rates(sdf)
    busy_iter = duty * cycles_per_iteration
    idle_iter = cycles_per_iteration - busy_iter

    def total(r):
        return r["busy"] * busy_iter + r["idle"] * idle_iter

    zero_iter, sdf_iter = total(rz), total(rs)
    glitch_iter = sdf_iter - zero_iter

    out = {
        "window_cycles": zero["cycles"],
        "window_busy_cycles": zero["busy_cycles"],
        "window_operations": zero["busy_bursts"],
        "window_duty": zero["busy_fraction"],
        "rate_zero_busy": rz["busy"],
        "rate_zero_idle": rz["idle"],
        "rate_sdf_busy": rs["busy"],
        "rate_sdf_idle": rs["idle"],
        # Per-operation and per-idle-cycle glitch, which are the two
        # figures that project onto another workload without knowing
        # anything about this one.
        "glitch_per_operation": (
            (sdf["transitions_subtree_busy"] - zero["transitions_subtree_busy"])
            / zero["busy_bursts"]
        ),
        "glitch_per_idle_cycle": rs["idle"] - rz["idle"],
        "iteration_duty": duty,
        "transitions_zero_per_iteration": zero_iter,
        "transitions_sdf_per_iteration": sdf_iter,
        "glitch_per_iteration": glitch_iter,
        # Of the annotated total, which is the way the literature states
        # a glitch fraction: how much of what the unit really switches
        # the logic function did not ask for.
        "glitch_fraction": glitch_iter / sdf_iter if sdf_iter else 0.0,
        "glitch_ratio": sdf_iter / zero_iter if zero_iter else 0.0,
    }
    if unit_dynamic_w is not None:
        extra = unit_dynamic_w * (glitch_iter / zero_iter)
        out["unit_dynamic_w"] = unit_dynamic_w
        out["unit_glitch_w"] = extra
        if core_power_w:
            out["core_power_w"] = core_power_w
            out["glitch_share_of_core"] = extra / core_power_w
    return out


def unit_dynamic(path, key_substring):
    """Internal plus switching for the one module named, from the ODB report."""
    with open(path) as f:
        document = json.load(f)
    hits = [k for k in document if key_substring in k]
    if len(hits) != 1:
        raise ValueError(
            "%r matches %d modules, need exactly one" % (key_substring, len(hits))
        )
    rows = document[hits[0]]
    if len(rows) != 1:
        raise ValueError("%s has %d instances, need one" % (hits[0], len(rows)))
    row = rows[0]
    return row["internal"] + row["switching"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zero", required=True, help="glitch_count JSON, zero delay")
    ap.add_argument("--sdf", required=True, help="glitch_count JSON, annotated")
    ap.add_argument("--duty", type=float, required=True,
                    help="the unit's duty cycle over a whole iteration")
    ap.add_argument("--cycles-per-iteration", type=int, required=True)
    ap.add_argument("--units", help="stage_power_units JSON")
    ap.add_argument("--unit", help="substring naming one module in it")
    ap.add_argument("--core-power", type=float, help="the core's total power, W")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    with open(args.zero) as f:
        zero = json.load(f)
    with open(args.sdf) as f:
        sdf = json.load(f)
    dynamic = unit_dynamic(args.units, args.unit) if args.units else None
    result = project(zero, sdf, args.duty, args.cycles_per_iteration,
                     dynamic, args.core_power)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
