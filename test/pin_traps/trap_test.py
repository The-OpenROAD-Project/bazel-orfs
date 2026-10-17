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
        claims.append(
            ("own: %s on the east side < 25 %%" % port, s < 0.25, "%.0f %%" % (100 * s))
        )
        s = side_share(hand_a, port, "right")
        claims.append(
            ("hand: %s all on the east side" % port, s == 1.0, "%.0f %%" % (100 * s))
        )
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


def _total(p, arm):
    """Block + parent wire of one arm: every probe of that arm, once per
    built block (the parent's instances of one block share its wire)."""
    return sum(v["wirelength_um"] for k, v in p.items() if k.split(":")[0] == arm)


def _ratio_claim(label, good, bad, frac):
    return (
        "%s <= %.2f of own" % (label, frac),
        good <= bad * frac,
        "%d vs %d um" % (good, bad),
    )


def check_both_own(p, bits=32, block_w=60.048):
    """Trap 2. Two blocks, each its own: neither puts more than a quarter
    of its x pins on the side that faces the other; by hand all of them
    do. Every one of the 2 * bits interface wires then runs along the top
    edges instead of across the 4.32 um gap: the parent's wire by hand is
    at most half of own's, block + parent at most two thirds."""
    claims = []
    for block, side in (("a", "right"), ("b", "left")):
        for port in ("x_in", "x_out"):
            s = side_share(p["own:" + block], port, side)
            claims.append(
                (
                    "own: %s.%s facing < 25 %%" % (block, port),
                    s < 0.25,
                    "%.0f %%" % (100 * s),
                )
            )
            s = side_share(p["hand:" + block], port, side)
            claims.append(
                (
                    "hand: %s.%s all facing" % (block, port),
                    s == 1.0,
                    "%.0f %%" % (100 * s),
                )
            )
    claims.append(
        _ratio_claim(
            "hand: parent wire",
            p["hand:top"]["wirelength_um"],
            p["own:top"]["wirelength_um"],
            0.5,
        )
    )
    claims.append(
        _ratio_claim(
            "hand: block + parent wire", _total(p, "hand"), _total(p, "own"), 2.0 / 3
        )
    )
    return claims


def check_narrow_channel(p, bits=32, block_w=40.032):
    """Trap 9. A 2.16 um channel has no rows once the halos are cut, so
    the parent's 2 * bits registers between the blocks go to the strip
    east of b, and each register's two wires cross b: own's parent wire
    >= 2 * bits * block_w. By hand the registers sit in the channel: at
    most a quarter of own's parent wire, half of block + parent."""
    own_t, hand_t = p["own:top"]["wirelength_um"], p["hand:top"]["wirelength_um"]
    bad = 2 * bits * block_w
    return [
        (
            "own: parent wire >= 2 * bits * block_w = %.0f um" % bad,
            own_t >= bad,
            "%d um" % own_t,
        ),
        _ratio_claim("hand: parent wire", hand_t, own_t, 0.25),
        _ratio_claim(
            "hand: block + parent wire", _total(p, "hand"), _total(p, "own"), 0.5
        ),
    ]


def check_split_logic(p):
    """Trap 10. The parent's logic is one cluster; with the blocks abutting
    in the middle of a core they span the height of, the cluster is cut
    in two and every wire across the cut crosses both blocks over their
    tops. Own overflows; by hand (blocks at the edges, the logic between)
    nothing overflows and the parent's wire is at most four fifths."""
    own_t, hand_t = p["own:top"], p["hand:top"]
    return [
        (
            "own: parent overflows",
            own_t["total_overflow"] > 0,
            "%d" % own_t["total_overflow"],
        ),
        (
            "hand: parent does not overflow",
            hand_t["total_overflow"] == 0,
            "%d" % hand_t["total_overflow"],
        ),
        _ratio_claim(
            "hand: parent wire", hand_t["wirelength_um"], own_t["wirelength_um"], 0.8
        ),
    ]


def check_tidy_row(p, bits=16, core_h=115.776, file_h=19.44):
    """Trap 11. Four files in a row along the bottom: the north owner's
    2 * bits wires each run from the top edge's ports to its file at the
    bottom, at least the core height less two files, so own's parent wire
    >= 2 * bits * (core_h - 2 * file_h). By hand each file sits at its
    owner's edge: at most half of own's wire, and no overflow where own
    has some."""
    own_t, hand_t = p["own:top"], p["hand:top"]
    bad = 2 * bits * (core_h - 2 * file_h)
    return [
        (
            "own: parent wire >= %.0f um" % bad,
            own_t["wirelength_um"] >= bad,
            "%d um" % own_t["wirelength_um"],
        ),
        (
            "own: parent overflows",
            own_t["total_overflow"] > 0,
            "%d" % own_t["total_overflow"],
        ),
        (
            "hand: parent does not overflow",
            hand_t["total_overflow"] == 0,
            "%d" % hand_t["total_overflow"],
        ),
        _ratio_claim(
            "hand: parent wire", hand_t["wirelength_um"], own_t["wirelength_um"], 0.5
        ),
    ]


def check_flip(p):
    """Trap 7. The block mirrored (own) wins on wire against the block as
    built (plain), and by hand the rebuilt block wins at least as much;
    but the mirror puts block pins between the parent's tracks, where by
    hand (R0) none are. Off-track is geometry, checked against the
    parent's track grids: the parent's pin access still finds every pin
    here, so the trap shows the mirror's geometry, not a failure it
    causes."""
    plain, own, hand = p["plain:top"], p["own:top"], p["hand:top"]
    return [
        (
            "own: the mirror shortens the wire",
            own["wirelength_um"] < plain["wirelength_um"],
            "%d vs %d um" % (own["wirelength_um"], plain["wirelength_um"]),
        ),
        (
            "own: block pins off the parent's tracks",
            own["block_pins_off_track"] > 0,
            "%d of %d" % (own["block_pins_off_track"], own["block_pin_shapes"]),
        ),
        (
            "plain: no block pin off the parent's tracks",
            plain["block_pins_off_track"] == 0,
            "%d of %d" % (plain["block_pins_off_track"], plain["block_pin_shapes"]),
        ),
        (
            "hand: no block pin off the parent's tracks",
            hand["block_pins_off_track"] == 0,
            "%d of %d" % (hand["block_pins_off_track"], hand["block_pin_shapes"]),
        ),
        (
            "hand: wire no longer than own",
            hand["wirelength_um"] <= own["wirelength_um"],
            "%d vs %d um" % (hand["wirelength_um"], own["wirelength_um"]),
        ),
    ]


def check_random_io(p):
    """Trap 12. Today's flow, every parent pin free and the files placed
    by the macro placer against pins placed at random, against the hand
    answer, which also ties every pin to its owner's edge: with strictly
    more freedom, own's wire is still longer than the constrained hand
    answer by a third or more."""
    own, hand = p["own:top"], p["hand:top"]
    return [
        _ratio_claim(
            "hand: parent wire", hand["wirelength_um"], own["wirelength_um"], 0.75
        )
    ]


def check_wide_pins(p):
    """Trap 8. Pins drawn two M3 wire widths wide leave the parent's pin
    access without an access point (DRT-0073); one wire width, at the
    same places, does not. The pin it stops on need not be a wide one:
    a neighbour the pin placer put beside the first wide pin is enough,
    as in XiangShan's one pin per block. The wire is the same."""
    own, hand = p["own:top"], p["hand:top"]
    return [
        (
            "own: pin access stops on DRT-0073",
            "DRT-0073" in own["pin_access"],
            own["pin_access"],
        ),
        (
            "hand: pin access finds every pin",
            hand["pin_access"] == "ok",
            hand["pin_access"],
        ),
    ]


def check_mini_top(p):
    """The combined parent: traps 1, 9 and 10 in bands of one die. The
    traps still catch today's flow when they share a die: own overflows
    and hand does not, and hand's block + parent wire is at most two
    thirds of own's (the three traps alone: 9 187, 13 771 and 23 738 um
    own against 2 201, 4 459 and 18 447 by hand, 0.53 of own)."""
    own, hand = p["own:top"], p["hand:top"]
    return [
        (
            "own: parent overflows",
            own["total_overflow"] > 0,
            "%d" % own["total_overflow"],
        ),
        (
            "hand: parent does not overflow",
            hand["total_overflow"] == 0,
            "%d" % hand["total_overflow"],
        ),
        _ratio_claim(
            "hand: block + parent wire", _total(p, "hand"), _total(p, "own"), 2.0 / 3
        ),
    ]


CHECKS = {
    "both_own": check_both_own,
    "face_away": check_face_away,
    "flip": check_flip,
    "mini_top": check_mini_top,
    "narrow_channel": check_narrow_channel,
    "random_io": check_random_io,
    "split_logic": check_split_logic,
    "tidy_row": check_tidy_row,
    "wide_pins": check_wide_pins,
}


# The traps whose answer is a block's pins: a loop that writes each
# block's pins from its placed parent must reach the hand answer there.
# The others are answered by where the parent puts its blocks, which the
# pin loop does not move; there it must only do no harm.
PIN_ANSWERED = ("both_own", "face_away", "flip")


def check_loop(p, trap, rounds):
    """The pin loop's rounds r1..r<rounds> against own and hand: never
    more block + parent wire than own; on a trap answered by pins, round
    1 within a tenth of hand's."""
    claims = []
    own = _total(p, "own")
    for k in range(1, rounds + 1):
        rk = _total(p, "r%d" % k)
        claims.append(
            (
                "r%d: block + parent wire <= own" % k,
                rk <= own,
                "%d vs %d um" % (rk, own),
            )
        )
    if trap in PIN_ANSWERED:
        r1, hand = _total(p, "r1"), _total(p, "hand")
        claims.append(
            (
                "r1: block + parent wire <= 1.1 x hand",
                r1 <= 1.1 * hand,
                "%d vs %d um" % (r1, hand),
            )
        )
    return claims


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trap", required=True, choices=sorted(CHECKS))
    ap.add_argument(
        "--loop",
        type=int,
        default=0,
        metavar="ROUNDS",
        help="check the pin loop's rounds instead of the trap",
    )
    ap.add_argument("probes", nargs="+", metavar="ARM:PART=JSON")
    a = ap.parse_args(argv)
    probes = {}
    for spec in a.probes:
        key, sep, path = spec.partition("=")
        if not sep or ":" not in key:
            raise SystemExit("bad probe argument %r, want ARM:PART=JSON" % spec)
        with open(path) as f:
            probes[key] = json.load(f)
    claims = check_loop(probes, a.trap, a.loop) if a.loop else CHECKS[a.trap](probes)
    failed = 0
    for claim, ok, detail in claims:
        print("%s  %s: %s" % ("PASS" if ok else "FAIL", claim, detail))
        failed += not ok
    print("%s: %d of %d claims hold" % (a.trap, len(claims) - failed, len(claims)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
