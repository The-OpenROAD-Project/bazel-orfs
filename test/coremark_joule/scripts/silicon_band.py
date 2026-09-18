"""Where one x86 or Arm core sits on this study's axes, from silicon.json.

Appendix A measures commodity cores at the wall plug and attributes power by
the slope of watts against active core count, which cancels the
platform's fixed draw. Its boundary is stated as "core and its private
caches" -- the same boundary this study hardens and reports, reached by
a different route.

That makes a region on Figure 1 possible that is *measured* rather than
apportioned. An earlier version of this took §A.1's package figures and
divided by an assumed core share of 50-80 %; the assumption was the
dominant uncertainty in the result and it is now unnecessary.

It is drawn as a region rather than as three markers because it is three
parts standing in for a class, and because a marker beside this study's
points would invite reading silicon on N7, Intel 7 and N4 against a
predictive 7 nm kit as one trend.
"""

import argparse
import json
import sys


def parts(document):
    """The parts that carry both coordinates."""
    out = []
    for p in document.get("parts", []):
        x = p.get("coremark_per_mhz")
        y = p.get("coremark_per_mj_slope")
        if x is None or y is None:
            continue
        out.append({"part": p.get("part", "?"), "x": float(x), "y": float(y) * 1000.0})
    return out


def band(document):
    """The rectangle those parts occupy, or None when none can be placed."""
    pts = parts(document)
    if not pts:
        return None
    xs = [p["x"] for p in pts]
    ys = [p["y"] for p in pts]
    return {
        "x_min": min(xs), "x_max": max(xs),
        "y_min": min(ys), "y_max": max(ys),
        "parts": len(pts),
    }


def read(path):
    with open(path) as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("silicon")
    args = ap.parse_args(argv)
    sys.stdout.write(json.dumps(band(read(args.silicon)), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
