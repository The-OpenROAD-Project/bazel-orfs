#!/usr/bin/env python3
"""Check a pin trap's arms against the numbers worked out by hand.

    trap_test.py --trap NAME ARM:PART=probe.json ...

PART is a block name or "top". Each trap's check states, from the trap's
geometry alone, where the block's own choice must land (the bad number)
and where the hand-made answer must land (the good one), as bounds, never
as a recorded result: a trap passes when its own arm is caught in the
trap and its hand arm is out of it. A probe that is missing or malformed
is an error, not a skip.
"""

import argparse
import json
import sys


def side_share(probe, port, side):
    """The share of a port's pins on one side of its die."""
    counts = probe["pin_sides"].get(port)
    if counts is None:
        raise ValueError(
            "%s has no port %s (has %s)"
            % (probe["design"], port, sorted(probe["pin_sides"]))
        )
    total = sum(counts.values())
    if total == 0:
        raise ValueError("%s port %s has no pins" % (probe["design"], port))
    return counts[side] / total


def check_face_away(p, bits=32, block_w=100.08):
    """Trap 1. Bounds from the geometry: block a is block_w wide, its
    contract on the west, the parent's logic only east of it.

    own: the e ports' cells follow en to the west, so fewer than a quarter
      of e_in and e_out reach the east side; every one of the 2 * bits
      interface wires then runs from the block's west half across it, at
      least block_w / 2 each: parent wire >= bits * block_w.
    hand: every e pin on the east side, each wire a channel's length, so
      the parent's wire is at most a fifth of own's; what the block pays
      (one long en net) still leaves block + parent at most two thirds of
      own's.
    """
    own_a, own_t, hand_a, hand_t = p["own:a"], p["own:top"], p["hand:a"], p["hand:top"]
    claims = []
    for port in ("e_in", "e_out"):
        s = side_share(own_a, port, "right")
        claims.append(("own: %s on the east side < 25 %%" % port, s < 0.25, "%.0f %%" % (100 * s)))
        s = side_share(hand_a, port, "right")
        claims.append(("hand: %s all on the east side" % port, s == 1.0, "%.0f %%" % (100 * s)))
    bad = bits * block_w
    claims.append(
        (
            "own: parent wire >= bits * block_w = %.0f um" % bad,
            own_t["wirelength_um"] >= bad,
            "%d um" % own_t["wirelength_um"],
        )
    )
    claims.append(
        (
            "hand: parent wire <= own / 5",
            hand_t["wirelength_um"] * 5 <= own_t["wirelength_um"],
            "%d vs %d um" % (hand_t["wirelength_um"], own_t["wirelength_um"]),
        )
    )
    own_total = own_a["wirelength_um"] + own_t["wirelength_um"]
    hand_total = hand_a["wirelength_um"] + hand_t["wirelength_um"]
    claims.append(
        (
            "hand: block + parent wire <= 2/3 of own",
            hand_total * 3 <= own_total * 2,
            "%d vs %d um" % (hand_total, own_total),
        )
    )
    return claims


CHECKS = {
    "face_away": check_face_away,
}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trap", required=True, choices=sorted(CHECKS))
    ap.add_argument("probes", nargs="+", metavar="ARM:PART=JSON")
    a = ap.parse_args(argv)
    probes = {}
    for spec in a.probes:
        key, sep, path = spec.partition("=")
        if not sep or ":" not in key:
            raise SystemExit("bad probe argument %r, want ARM:PART=JSON" % spec)
        with open(path) as f:
            probes[key] = json.load(f)
    claims = CHECKS[a.trap](probes)
    failed = 0
    for claim, ok, detail in claims:
        print("%s  %s: %s" % ("PASS" if ok else "FAIL", claim, detail))
        failed += not ok
    print("%s: %d of %d claims hold" % (a.trap, len(claims) - failed, len(claims)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
