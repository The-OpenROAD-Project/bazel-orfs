"""Flag what sets a design's worst slack at global route (ORFS #4583).

Reads read.tcl's "<key>\\t<value>" facts and writes one JSON object with
the pathology flags and the numbers behind them. The thresholds were fixed
before the sweep ran and are not tuned to its results.

  classify.py <target> <facts.tsv> [minutes]
"""

import json
import sys

# P1: an IO group's worst slack below reg2reg's by more than this share
IO_GAP = 0.02
# P2: of P1's path, the pin's wire and buffers more than this share
PIN_WIRE = 0.25
# P4: the worst reg2reg endpoint beyond the tenth worst by this share
OUTLIER = 0.10
# P5: reg2reg period within this share of the one-flop-loop floor
FLOOR = 0.03
# P7: WNS >= 0 and the reg2reg period under this share of the clock
SLACK_RICH = 0.85
# P8: the reg2reg period over this share of the clock
OUT_OF_REACH = 1.30
# P10: hold buffers over this share of instances, most from inputs
HOLD = 0.05

IO_GROUPS = ("in2reg", "reg2out", "in2out")

# check_setup warnings that leave registers untimed: unclocked registers,
# and unconstrained endpoints that are register data pins (read.tcl counts
# those; an output port the SDC gives no delay is left out by design)
UNSEEN = ("unclocked", "unconstrained_register_pins", "no_clock")


def parse(text):
    facts = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition("\t")
        facts[key] = value
    return facts


def num(facts, key):
    v = facts.get(key)
    return None if v in (None, "") else float(v)


def classify(facts):
    """The flags and the numbers they rest on."""
    clocks = {k[6:]: float(v) for k, v in facts.items() if k.startswith("clock.")}
    if not clocks:
        raise ValueError("no clock: nothing to time against")
    r2r_slack = num(facts, "reg2reg.slack")
    capture = facts.get("reg2reg.capture") or facts.get("worst.capture")
    clock = clocks.get(capture, min(clocks.values()))
    wns = num(facts, "wns")
    out = {"clock": clock, "wns": wns, "flags": [], "evidence": {}}
    ev = out["evidence"]

    worst_group = None
    for g in ("reg2reg",) + IO_GROUPS:
        s = num(facts, g + ".slack")
        if s is not None and (worst_group is None or s < worst_slack):
            worst_group, worst_slack = g, s
    out["worst_group"] = worst_group or "none"

    if r2r_slack is None:
        out["reg2reg_min_period"] = None
        out["flags"].append("P0")
        ev["P0"] = "no register-to-register path"
    else:
        period = clock - r2r_slack
        out["reg2reg_min_period"] = period

        if worst_group in IO_GROUPS and r2r_slack - worst_slack > IO_GAP * clock:
            out["flags"].append("P1")
            ev["P1"] = "%s %s -> %s, %.4g below reg2reg" % (
                worst_group,
                facts.get(worst_group + ".from"),
                facts.get(worst_group + ".to"),
                r2r_slack - worst_slack,
            )
            wire = num(facts, worst_group + ".pin_wire")
            delay = num(facts, worst_group + ".delay")
            if wire is not None and delay and wire > PIN_WIRE * delay:
                out["flags"].append("P2")
                ev["P2"] = "pin wire %.4g of %.4g" % (wire, delay)

        top = [float(x) for x in facts.get("reg2reg.top10", "").split()]
        if len(top) == 10 and top[0] - top[9] > OUTLIER * clock:
            out["flags"].append("P4")
            ev["P4"] = "%.4g worst, %.4g tenth, at %s" % (
                top[0],
                top[9],
                facts.get("reg2reg.to"),
            )

        floor = num(facts, "floor")
        if floor is not None and floor >= (1 - FLOOR) * period:
            out["flags"].append("P5")
            ev["P5"] = "floor %.4g, period %.4g" % (floor, period)

        if wns is not None and wns >= 0 and period < SLACK_RICH * clock:
            out["flags"].append("P7")
            ev["P7"] = "period %.4g of clock %.4g" % (period, clock)
        if period > OUT_OF_REACH * clock:
            out["flags"].append("P8")
            ev["P8"] = "period %.4g of clock %.4g" % (period, clock)

    unseen = {
        k[len("check_setup.") :]: int(float(v))
        for k, v in facts.items()
        if k.startswith("check_setup.")
        and k != "check_setup.ran"
        and any(u in k for u in UNSEEN)
    }
    unseen = {k: v for k, v in unseen.items() if v}
    if unseen:
        out["flags"].append("P3")
        ev["P3"] = ", ".join("%d %s" % (v, k) for k, v in sorted(unseen.items()))

    if facts.get("worst.macro") == "1":
        out["flags"].append("P6")
        ev["P6"] = "%s -> %s" % (facts.get("worst.from"), facts.get("worst.to"))

    if facts.get("check_setup.ran") != "1":
        raise ValueError("check_setup did not run")

    launch, cap = facts.get("worst.launch"), facts.get("worst.capture")
    real = lambda c: c and "virtual." + c not in facts
    if real(launch) and real(cap) and launch != cap:
        out["flags"].append("P9")
        ev["P9"] = "%s -> %s" % (launch, cap)

    holds = num(facts, "hold.buffers") or 0
    insts = num(facts, "instances") or 0
    sampled = num(facts, "hold.sampled") or 0
    from_input = num(facts, "hold.from_input") or 0
    if insts and holds > HOLD * insts and from_input > sampled / 2:
        out["flags"].append("P10")
        ev["P10"] = "%d hold buffers of %d instances, %d of %d sampled from inputs" % (
            holds,
            insts,
            from_input,
            sampled,
        )
    out["instances"] = int(insts)
    out["hold_buffers"] = int(holds)
    out["floor"] = num(facts, "floor")
    return out


def main(argv):
    target, path = argv[1], argv[2]
    out = {"target": target, "status": "done"}
    out.update(classify(parse(open(path).read())))
    if len(argv) > 3:
        out["minutes"] = float(argv[3])
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv)
