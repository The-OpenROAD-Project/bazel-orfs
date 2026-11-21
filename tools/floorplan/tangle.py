#!/usr/bin/env python3
"""Rung 2's facts from a block's netlist (extract_netlist.tcl's dump),
<block>.tangle.json, in minutes:

  block, identity {dump, tool}
  gtl [{seed, cells, cut, score, cells_share}]   the most tangled clusters
  net_range {levels [{level, nets, span_share}], long_share}
  contraction {sampled, quantiles {q10, q50, q90}, weak_share}

Groups of tangled logic (GTL): from SEEDS cells spread evenly over the
netlist, a cluster grows by the neighbour with the most nets into it, to
GTL_MAX cells. Its score is its cut over what Rent's rule gives a part
of its size, cut / (k |C|^p) at the block's own p and k (netlist.py's
fit, or --p/--k); a score well under one is logic that pulls in on
itself, which placement packs and routing cannot get out of. Each seed's
lowest score from GTL_MIN cells on is reported, the lowest first, one
per cluster.

Net range: the bisection level that first separates a net's cells (one
fixed partitioner, netlist.py's, to RANGE_LEVELS levels, every part
split): a net first cut at level L spans about a 2^-(L-1) share of the
block's side. long_share is the share of nets cut at level 1 or 2.

Mutual contraction (Hu and Marek-Sadowska) of each connection of a
sample of CONTRACTION_SAMPLE cells: the weight w(u,v) = sum over the
nets joining them of 2 / (d (d - 1)), contraction w(u,v)^2 / (w(u) w(v)).
A weakly contracted connection (under WEAK) is a long wire in a good
placement; weak_share is their share.

Stdlib only.
"""

import argparse
import hashlib
import heapq
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netlist as N  # noqa: E402

TOOL = "tangle 1"
SEEDS = 32
GTL_MIN = 64
GTL_MAX = 8192
TOP = 8
RANGE_LEVELS = 6
CONTRACTION_SAMPLE = 20000
WEAK = 0.05


def gtl(nl, p, k, seeds=SEEDS, gmin=GTL_MIN, gmax=GTL_MAX):
    n = nl.n
    if n < 2 * gmin:
        return []
    gmax = min(gmax, n // 4)
    out = []
    for i in range(seeds):
        seed = (i * n) // seeds
        inside = {seed}
        # per net: cells inside
        cnt = {}
        cut = 0
        conn = {}
        heap = []

        def add(c):
            nonlocal cut
            for ni in nl.cell_nets[c]:
                cs = nl.net_cells[ni]
                if len(cs) > N.BIG_NET:
                    continue
                v = cnt.get(ni, 0)
                d = len(cs) + len(nl.net_ports[ni])
                if v == 0 and d > 1:
                    cut += 1
                cnt[ni] = v + 1
                if v + 1 == len(cs) and not nl.net_ports[ni]:
                    cut -= 1
                if v == 0:
                    for x in cs:
                        if x not in inside:
                            conn[x] = conn.get(x, 0) + 1
                            heapq.heappush(heap, (-conn[x], x))

        add(seed)
        best = None
        while heap and len(inside) < gmax:
            g, c = heapq.heappop(heap)
            if c in inside or -g != conn.get(c):
                continue
            inside.add(c)
            add(c)
            size = len(inside)
            if size >= gmin:
                score = cut / (k * size**p)
                if best is None or score < best[0]:
                    best = (score, size, cut)
        if best:
            out.append(
                {
                    "seed": seed,
                    "score": round(best[0], 4),
                    "cells": best[1],
                    "cut": best[2],
                    "cells_share": round(best[1] / n, 5),
                }
            )
    out.sort(key=lambda r: (r["score"], r["seed"]))
    seen = set()
    uniq = []
    for r in out:
        if (r["cells"], r["cut"]) not in seen:
            seen.add((r["cells"], r["cut"]))
            uniq.append(r)
    return uniq[:TOP]


def net_range(nl, levels=RANGE_LEVELS):
    """Bisect every part to `levels`; the level each net is first cut."""
    n = nl.n
    part = [0] * n
    nl.stamp = 0
    nl.cmark = [0] * n
    nl.dmark = [0] * n
    nl.nmark = [0] * len(nl.net_cells)
    first = [0] * len(nl.net_cells)
    members = {0: list(range(n))}
    nxt = 1
    for level in range(1, levels + 1):
        new = {}
        for lab, cells in members.items():
            if len(cells) < 2 * N.MIN_G:
                new[lab] = cells
                continue
            order = nl._order(cells, part, lab)
            la, lb = nxt, nxt + 1
            nxt += 2
            half = len(order) // 2
            for c in order[:half]:
                part[c] = la
            for c in order[half:]:
                part[c] = lb
            nl._refine(order, part, la, lb)
            new[la] = [c for c in order if part[c] == la]
            new[lb] = [c for c in order if part[c] == lb]
        members = new
        for ni, cs in enumerate(nl.net_cells):
            if first[ni] or len(cs) < 2:
                continue
            p0 = part[cs[0]]
            for c in cs:
                if part[c] != p0:
                    first[ni] = level
                    break
    total = sum(1 for cs in nl.net_cells if len(cs) >= 2)
    rows = []
    for level in range(1, levels + 1):
        k = sum(1 for f in first if f == level)
        rows.append(
            {
                "level": level,
                "nets": k,
                "span_share": round(2.0 ** -((level - 1) / 2.0), 4),
            }
        )
    long_ = sum(r["nets"] for r in rows if r["level"] <= 2)
    return {
        "levels": rows,
        "nets": total,
        "long_share": round(long_ / total, 5) if total else 0.0,
    }


def contraction(nl, sample=CONTRACTION_SAMPLE, weak=WEAK):
    n = nl.n
    if n < 2:
        return {"sampled": 0}
    step = max(1, n // sample)
    picked = range(0, n, step)
    wcell = {}

    def weights(c):
        if c in wcell:
            return wcell[c]
        w = {}
        for ni in nl.cell_nets[c]:
            cs = nl.net_cells[ni]
            d = len(cs)
            if d < 2 or d > N.BIG_NET:
                continue
            x = 2.0 / (d * (d - 1))
            for o in cs:
                if o != c:
                    w[o] = w.get(o, 0.0) + x
        wcell[c] = (w, sum(w.values()))
        return wcell[c]

    vals = []
    for c in picked:
        w, tot = weights(c)
        for o, x in w.items():
            if o < c:
                continue
            _, to = weights(o)
            if tot > 0 and to > 0:
                vals.append(x * x / (tot * to))
        if len(wcell) > 4 * sample:
            wcell.clear()
    vals.sort()
    if not vals:
        return {"sampled": 0}

    def q(f):
        return round(vals[min(len(vals) - 1, int(f * len(vals)))], 5)

    return {
        "sampled": len(vals),
        "quantiles": {"q10": q(0.1), "q50": q(0.5), "q90": q(0.9)},
        "weak_share": round(sum(1 for v in vals if v < weak) / len(vals), 5),
    }


def build(lines, dump_hash, p=None, k=None):
    nl = N.Netlist(lines)
    if p is None or k is None:
        r = nl.rent()
        p = r["p"] if p is None else p
        k = r["k"] if k is None else k
    return {
        "block": nl.block,
        "identity": {"dump": "sha256:" + dump_hash, "tool": TOOL},
        "rent": {"p": p, "k": k},
        "gtl": gtl(nl, p, k) if p is not None else [],
        "net_range": net_range(nl),
        "contraction": contraction(nl),
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump", help="extract_netlist.tcl's dump")
    ap.add_argument("out", help="the tangle.json to write")
    ap.add_argument("--p", type=float, help="Rent's p, else the block's own fit")
    ap.add_argument("--k", type=float, help="Rent's k, else the block's own fit")
    args = ap.parse_args(argv)
    with open(args.dump, "rb") as f:
        raw = f.read()
    out = build(
        raw.decode().splitlines(), hashlib.sha256(raw).hexdigest(), args.p, args.k
    )
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
