#!/usr/bin/env python3
"""tpu's clock arrival per tile as a figure: clock_plot.py REPORT OUT.svg

REPORT is tpu_stitched_clock.txt (clock_arrival.tcl): per macro
instance, the earliest, mean and latest clock arrival at its registers.
Draws the 4 x 4 grid of tiles, each shaded and labelled by its mean
arrival, with the arrival's step from each tile to its east and south
neighbour: the clock skew data flowing that way sees.
"""

import re
import sys


def read(path):
    tiles = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"u_b(\d+)_(\d+) \S+ (\S+) ", line)
            if m:
                tiles[(int(m.group(1)), int(m.group(2)))] = float(m.group(3))
    return tiles


def svg(tiles):
    rows = 1 + max(r for r, _ in tiles)
    cols = 1 + max(c for _, c in tiles)
    lo, hi = min(tiles.values()), max(tiles.values())
    S, L, T = 120, 70, 60
    W, H = L + cols * S + 40, T + rows * S + 70
    # one hue, light to dark with the arrival
    ramp = ["#dbe8f7", "#b4cdee", "#86ade2", "#5a8ed4", "#2f6dbf"]
    o = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" font-family="Helvetica, Arial, sans-serif">'
        % (W, H, W, H),
        '<rect width="%d" height="%d" fill="#fcfcfb"/>' % (W, H),
        '<text x="%d" y="26" font-size="15" font-weight="600" fill="#0b0b0b">tpu: clock arrival at each tile\'s registers, ps</text>'
        % L,
        '<text x="%d" y="44" font-size="11" fill="#52514e">stitched at global route; the clock enters each row from the west and runs east through the tiles</text>'
        % L,
    ]
    for (r, c), t in sorted(tiles.items()):
        x, y = L + c * S, T + r * S
        k = min(len(ramp) - 1, int((t - lo) / (hi - lo + 1e-9) * len(ramp)))
        o.append(
            '<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="#fcfcfb" stroke-width="2"/>'
            % (x, y, S, S, ramp[k])
        )
        o.append(
            '<text x="%d" y="%d" font-size="15" font-weight="600" fill="#0b0b0b" text-anchor="middle">%.0f</text>'
            % (x + S / 2, y + S / 2 + 5, t)
        )

    def step(cx, cy, label):
        o.append(
            '<rect x="%d" y="%d" width="46" height="18" rx="9" fill="#fcfcfb" stroke="#52514e" stroke-width="0.5"/>'
            % (cx - 23, cy - 9)
        )
        o.append(
            '<text x="%d" y="%d" font-size="11" fill="#0b0b0b" text-anchor="middle">%s</text>'
            % (cx, cy + 4, label)
        )

    # the steps over the tiles, on the edges they cross
    for (r, c), t in sorted(tiles.items()):
        x, y = L + c * S, T + r * S
        if (r, c + 1) in tiles:
            step(x + S, y + S / 2 + 30, "+%.0f &#8594;" % (tiles[(r, c + 1)] - t))
        if (r + 1, c) in tiles:
            step(x + S / 2, y + S, "%+.0f &#8595;" % (tiles[(r + 1, c)] - t))
    o.append(
        '<text x="%d" y="%d" font-size="11" fill="#52514e">step to the east neighbour: the skew activations flowing east see; to the south: weights and sums</text>'
        % (L, T + rows * S + 30)
    )
    o.append("</svg>")
    return "\n".join(o)


def main(argv):
    report, out = argv
    with open(out, "w") as f:
        f.write(svg(read(report)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
