#!/usr/bin/env python3
"""Carve specs for tpu's N x N array cut into blocks of R x C processing elements.

  make_spec.py N R C OUT.json [--clock-at-top]

Block (bi, bj) holds rows bi*R..bi*R+R-1 and columns bj*C..bj*C+C-1. Its
ports face its neighbours: activations in on the west and out on the
east, weights and partial sums in on the north and out on the south. The
first tile, the module every block instantiates, is an interior block:
top-row blocks tie their partial-sum input to 0 (synthesis folded the
adders behind it), last-column blocks leave their activation outputs
open and bottom blocks their weight outputs (nothing reads them).

The clock, reset and load enable run through the tiles: each block row's
westmost tile reads the parent's, every other tile its west neighbour's,
with the activations; the bottom row's tiles also clock the deskew
registers below them. A macro inside the array reaches no parent net, and
the data flowing only east and south needs only its neighbours' clocks
close (Fisher and Kung). FIFOs outside the tpu are assumed, so nothing at
its ports has to meet an outside clock. With --clock-at-top only reset and
the load enable run through the tiles: the top level reaches every tile's
clock pin from above, and the deskew registers keep tpu's clock.
"""

import json
import sys


def pe(i, j, reg):
    return "u_array.g_pe_row[%d].g_pe_col[%d].u_pe.%s" % (i, j, reg)


# A register between two PEs has a name in each, and yosys keeps
# whichever sorts first: with two-digit rows or columns that is the
# neighbour's. A spec names such a net by both.
def a_east(n, i, j):
    """A PE's activation register, also its east neighbour's a_west."""
    if j + 1 < n:
        return [pe(i, j, "a_east"), pe(i, j + 1, "a_west")]
    return pe(i, j, "a_east")


def w(n, i, j):
    """A PE's weight register, also the PE below's w_north."""
    if i + 1 < n:
        return [pe(i, j, "w"), pe(i, j, "w_south"), pe(i + 1, j, "w_north")]
    return [pe(i, j, "w"), pe(i, j, "w_south")]


def spec(n, r, c, clock_at_top=False):
    def psum(i, j):
        # the last row's partial sums carry the deskew's names
        if i == n - 1:
            return "g_deskew[%d].cin" % j
        return [pe(i, j, "psum_south"), pe(i + 1, j, "psum_north")]

    tiles = []
    for bi in range(n // r):
        for bj in range(n // c):
            rows = range(bi * r, bi * r + r)
            cols = range(bj * c, bj * c + c)
            last_col = bj * c + c - 1 == n - 1
            seeds = []
            for i in rows:
                for j in cols:
                    seeds += [{"net": w(n, i, j)}, {"net": psum(i, j)}]
            # activation registers, those of the block's last column last:
            # a block at the array's east edge has none of those
            seeds += [
                {"net": a_east(n, i, j)} for i in rows for j in cols if j != cols[-1]
            ]
            if not last_col:
                seeds += [{"net": a_east(n, i, cols[-1])} for i in rows]
            ports = []
            for k, i in enumerate(rows):
                if bj == 0:
                    # the skew registers' outputs have no name of their
                    # own: the inputs of the first column's registers
                    ports.append(
                        {
                            "net": a_east(n, i, 0),
                            "via": "D",
                            "port": "a_in",
                            "port_lsb": 8 * k,
                        }
                    )
                else:
                    ports.append(
                        {
                            "net": a_east(n, i, cols[0] - 1),
                            "port": "a_in",
                            "port_lsb": 8 * k,
                        }
                    )
                if not last_col:
                    ports.append(
                        {
                            "net": a_east(n, i, cols[-1]),
                            "port": "a_out",
                            "port_lsb": 8 * k,
                        }
                    )
            for k, j in enumerate(cols):
                if bi == 0:
                    ports.append(
                        {
                            "net": "w_data",
                            "lsb": 8 * j,
                            "width": 8,
                            "port": "w_in",
                            "port_lsb": 8 * k,
                        }
                    )
                else:
                    ports.append(
                        {
                            "net": w(n, rows[0] - 1, j),
                            "port": "w_in",
                            "port_lsb": 8 * k,
                        }
                    )
                    ports.append(
                        {
                            "net": psum(rows[0] - 1, j),
                            "port": "psum_in",
                            "port_lsb": 32 * k,
                        }
                    )
                ports.append(
                    {"net": w(n, rows[-1], j), "port": "w_out", "port_lsb": 8 * k}
                )
                ports.append(
                    {"net": psum(rows[-1], j), "port": "psum_out", "port_lsb": 32 * k}
                )
            ports += [
                {"net": "clk", "port": "clk"},
                {"net": "rst", "port": "rst"},
                {"net": "w_valid", "port": "w_valid"},
            ]
            t = {"instance": "u_b%d_%d" % (bi, bj), "seeds": seeds, "ports": ports}
            unread = (["a_out"] if last_col else []) + (
                ["w_out"] if bi == n // r - 1 else []
            )
            if unread:
                t["unread"] = unread
            if bi == 0:
                t["tie"] = ["psum_in"]
            # the clock, reset and load enter each block row at its west
            # end and run east with the activations, tile to tile
            if bj > 0:
                t["chain_from"] = "u_b%d_%d" % (bi, bj - 1)
            # the bottom row's clock runs on into the deskew registers
            # its results go to
            if bi == n // r - 1 and not clock_at_top:
                t["south_registers"] = [{"net": psum(n - 1, j)} for j in cols]
            tiles.append(t)

    # the template: below the top row (its partial-sum adders are real),
    # left of the last column where there is one (its activation outputs
    # exist); a bottom block exports its weight outputs all the same
    def rank(t):
        return ("tie" in t, "a_out" in t.get("unread", []))

    tiles.sort(key=rank)
    return {
        "module": "tpu_block",
        "stops": [{"net": "g_skew[0].din"}],
        "tiles": tiles,
        # with the clock at the top, each tile's clock pin is reached from
        # above and only reset and the load enable run with the data
        "chain": ([] if clock_at_top else [["clk", "clk_out"]])
        + [["rst", "rst_out"], ["w_valid", "w_valid_out"]],
        "south": [] if clock_at_top else [["clk", "clk_south"]],
    }


if __name__ == "__main__":
    n, r, c = (int(x) for x in sys.argv[1:4])
    clock_at_top = "--clock-at-top" in sys.argv[5:]
    json.dump(spec(n, r, c, clock_at_top), open(sys.argv[4], "w"), indent=1)
