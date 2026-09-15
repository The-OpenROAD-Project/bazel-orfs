#!/usr/bin/env python3
"""A complete account of which pins OpenSTA measured and which it guessed.

`report_power -saif` never fails for want of switching activity. A pin
the SAIF did not annotate is not an error -- OpenSTA estimates it, and
the estimate looks exactly like a measurement in the report. So a
CoreMark/Joule figure is worth no more than the answer to "which pins
were measured?", and that answer has to be enumerated rather than
asserted.

This reads three facts files produced by flow/activity_audit.tcl --
OpenSTA's own annotated and unannotated listings, the ODB's view of
every pin, and the design's clock and corner -- and puts every
unannotated pin in exactly one class. Each class carries a policy,
because "unannotated" does not mean "wrong":

  clock_network   OpenSTA gives a clock-network pin 2/period from the
                  SDC, exactly, bypassing the estimator entirely. Being
                  unannotated is the correct state for these.
  tied_constant   driven by a tie cell or a constant net: no switching.
  unconnected     connected to no net at all: nothing to switch.
  power_ground    excluded from the power calculation by construction.
  scan_test       tied off for functional operation; benign, and the
                  design says so in writing.
  top_port        an *input* port is a levelization root, which is where
                  OpenSTA's default activity enters the design and
                  spreads. Unannotated is fatal.
  macro_pin       an unannotated SRAM is memory energy being invented
                  rather than measured. Fatal.
  internal_cell_pin
                  the catch-all, and the class this study exists to
                  empty. Fatal above the budget the design declares.

The classification is the accounting. The *bound* -- how much the
estimator could move the answer even if it were wrong -- comes from
flow/activity_sweep.tcl and check_activity_sweep.py, which is the other
half of the claim and the one that carries a number.
"""

import argparse
import json
import re
import sys

# Liberty/LEF signal types that are not part of the switching power
# calculation at all. OpenSTA excludes them from both of its listings;
# one appearing here means the library did not mark it, which is worth
# recording rather than asserting away.
_PG_TYPES = ("POWER", "GROUND")

# A net the router treats as a constant source. TIEOFF is what a LEF
# marks a tie cell's output net as; POWER and GROUND appear when a pin is
# tied straight to a rail.
_CONSTANT_NET_TYPES = ("POWER", "GROUND", "TIEOFF")

_TIE_MASTER_TYPES = ("CORE_TIEHIGH", "CORE_TIELOW")

# Class -> whether an unannotated pin in it fails the audit.
FATAL_CLASSES = (
    "top_port",
    "macro_pin",
    "internal_cell_pin",
)

BENIGN_CLASSES = (
    "clock_network",
    "tied_constant",
    "unconnected",
    "power_ground",
    "scan_test",
    "waived",
    "top_port_output",
)

CLASSES = FATAL_CLASSES + BENIGN_CLASSES + ("unmatched",)


def read_pins(path):
    """The ODB's view of every pin, keyed by the path OpenSTA prints."""
    pins = {}
    with open(path) as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            if not line.strip():
                continue
            row = line.rstrip("\n").split("\t")
            # A short row means a field held a tab, which would silently
            # shift every column after it.
            if len(row) != len(header):
                raise ValueError(
                    "{}: expected {} columns, got {}: {!r}".format(
                        path, len(header), len(row), line
                    )
                )
            pins[row[0]] = dict(zip(header, row))
    return pins


def read_annotation(path):
    """OpenSTA's annotated and unannotated pin listings.

    The summary counts above the listings are deliberately not read.
    `Power::reportActivityAnnotation` computes `unannotated` as
    `pinCount()` minus the size of the annotated map, over two pin sets
    that filter power/ground pins differently, in unsigned arithmetic --
    so it can undercount, and on a design whose annotation reaches pins
    `pinCount()` does not count it underflows. The enumerations below it
    are the ground truth.

    Returns:
      (annotated, unannotated): a dict of path -> origin, and a list of
      paths.
    """
    annotated = {}
    unannotated = []
    section = None
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped == "Annotated pins:":
                section = "annotated"
                continue
            if stripped == "Unannotated pins:":
                section = "unannotated"
                continue
            if not stripped:
                continue
            if section == "annotated":
                # "{:>5} {}" -- origin, then the path.
                parts = stripped.split(None, 1)
                if len(parts) != 2:
                    continue
                annotated[parts[1]] = parts[0]
            elif section == "unannotated":
                unannotated.append(stripped)
    return annotated, unannotated


def _matches_any(name, patterns):
    for pattern in patterns:
        if re.search(pattern, name):
            return True
    return False


def driver_nets(pins):
    """Nets driven by a tie cell, from the pin table alone.

    A tie cell announces itself in the LEF as CORE_TIEHIGH or
    CORE_TIELOW; the net it drives does not always carry TIEOFF, so the
    driver has to be looked up rather than trusted to the net's own type.
    """
    tied = set()
    for pin in pins.values():
        if pin["master_type"] in _TIE_MASTER_TYPES and pin["net"]:
            tied.add(pin["net"])
    return tied


def classify(path, pin, tied_nets, policy):
    """The one class this unannotated pin belongs to."""
    if pin is None:
        return "unmatched"

    for waiver in policy.get("waivers", []):
        if re.search(waiver["pattern"], path):
            return "waived"

    if pin["sig_type"] in _PG_TYPES:
        # The cell's own rail pin. OpenSTA excludes these from both
        # listings; one reaching here means the liberty did not mark it.
        return "power_ground"

    if pin["net_sig_type"] in _CONSTANT_NET_TYPES:
        # A signal pin wired to a rail or to a tie-off net: constant by
        # construction, whatever the estimator would have assumed.
        return "tied_constant"

    if not pin["net"]:
        return "unconnected"

    if pin["net_sig_type"] == "CLOCK":
        return "clock_network"

    if pin["net"] in tied_nets:
        return "tied_constant"

    if pin["master_type"] in _TIE_MASTER_TYPES:
        return "tied_constant"

    if _matches_any(pin["port"], policy.get("scan_patterns", [])):
        return "scan_test"

    if pin["kind"] == "bterm":
        # An input port is a levelization root: it is where OpenSTA's
        # default activity enters the design and propagates from. An
        # output port is downstream of one and adds no activity of its
        # own.
        if pin["direction"] == "OUTPUT":
            return "top_port_output"
        return "top_port"

    if pin["master_type"] == "BLOCK" or _matches_any(
        pin["cell"], policy.get("macro_patterns", [])
    ):
        return "macro_pin"

    return "internal_cell_pin"


def audit(pins, annotated, unannotated, design, policy):
    tied_nets = driver_nets(pins)

    by_class = dict((name, []) for name in CLASSES)
    for path in unannotated:
        name = classify(path, pins.get(path), tied_nets, policy)
        by_class[name].append(path)

    origins = {}
    for origin in annotated.values():
        origins[origin] = origins.get(origin, 0) + 1

    fatal = []
    for name in FATAL_CLASSES:
        fatal.extend(by_class[name])
    # An unmatched pin is a name OpenSTA printed that the ODB table does
    # not contain. That is a join failure, not a benign pin, and it hides
    # whatever the pin really was.
    fatal.extend(by_class["unmatched"])

    total = len(annotated) + len(unannotated)
    budget = policy.get("max_unannotated_internal", 0)
    internal = len(by_class["internal_cell_pin"])
    over_budget = internal > budget

    other_fatal = len(fatal) - internal
    verdict = "fail" if (over_budget or other_fatal > 0) else "pass"

    return {
        "design": design.get("design", ""),
        "stage": design.get("stage", ""),
        "saif": design.get("saif", ""),
        "saif_scope": design.get("saif_scope", ""),
        "liberty": design.get("liberty", []),
        "clocks": design.get("clocks", []),
        "odb_pin_count": design.get("pin_count"),
        "listed_pin_count": total,
        "annotated": len(annotated),
        "annotated_by_origin": origins,
        "annotated_fraction": (float(len(annotated)) / total) if total else 0.0,
        "unannotated": len(unannotated),
        "unannotated_by_class": dict(
            (name, len(paths)) for name, paths in by_class.items()
        ),
        "internal_budget": budget,
        "fatal_count": len(fatal),
        "fatal_examples": sorted(fatal)[:50],
        "verdict": verdict,
    }


def report(result, out=sys.stdout):
    out.write("pin activity audit: {} at {}\n".format(result["design"], result["stage"]))
    out.write(
        "  annotated   {:>8}  ({:.4%} of {} listed pins)\n".format(
            result["annotated"], result["annotated_fraction"], result["listed_pin_count"]
        )
    )
    for origin in sorted(result["annotated_by_origin"]):
        out.write(
            "    {:<10}{:>8}\n".format(origin, result["annotated_by_origin"][origin])
        )
    out.write("  unannotated {:>8}\n".format(result["unannotated"]))
    for name in CLASSES:
        count = result["unannotated_by_class"].get(name, 0)
        if count == 0:
            continue
        flag = "FATAL" if name in FATAL_CLASSES or name == "unmatched" else "ok"
        out.write("    {:<20}{:>8}  {}\n".format(name, count, flag))
    out.write("  verdict     {:>8}\n".format(result["verdict"]))
    if result["fatal_examples"]:
        out.write("  first offenders:\n")
        for path in result["fatal_examples"][:10]:
            out.write("    {}\n".format(path))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pins", required=True, help="the *_pins.tsv")
    parser.add_argument("--annotation", required=True, help="the *_annotation.txt")
    parser.add_argument("--design", required=True, help="the *_design.json")
    parser.add_argument(
        "--policy",
        required=True,
        help="the design's pin_policy.json: its budget and its written waivers",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])

    pins = read_pins(args.pins)
    annotated, unannotated = read_annotation(args.annotation)
    with open(args.design) as f:
        design = json.load(f)
    with open(args.policy) as f:
        policy = json.load(f)

    result = audit(pins, annotated, unannotated, design, policy)

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    report(result)
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
