#!/usr/bin/env python3
"""A block's netlist (extract_netlist.tcl's dump) as rung 1's facts,
<block>.netlist.json:

  block, identity {dump, tool}
  insts, nets, pins
  rent {p, k, levels [{level, parts, g, t}], fit [first, last]}
  buses {bus: {bits, sampled, cells_mean, breadth_mean, breadth_max, capped,
               feedthrough}}
  feedthrough {bits, cells, connections}
  fanout [{net, sinks, driver}]   the FANOUT_TOP nets of most sinks (the
        netlist's own sinks, after synthesis merged equal registers; no
        buffers yet), the driver a register, a hard object, a port or logic

A feed-through bit is an input that reaches an output port alone: a
chain of at most FT_CELLS single-input cells (buffers, inverters), every
net of it with one sink and no other. It is a wire across the block, not
its logic (ladder.py takes it out of Rent and the wire demand).

Rent's p and k from recursive bisection: every part is split in two by
one fixed partitioner (cells in breadth-first order from a far cell,
halved by count, then one pass of moves that each cut fewer nets; nets
of more than BIG_NET cells neither order nor move a cell); at
each level the mean cells G and the mean terminals T (nets with a cell
inside and a cell or a port outside) of the parts split; p and k by least
squares on log T = log k + p log G over the levels from 2 down with G of
at least MIN_G: level 0 is the block, whose terminals are its ports, and
a level-1 half has only the other half outside it. At
most WIDTH parts are split per level, evenly spaced, so a level costs at
most one pass over the netlist.

Each port bus's cone: forward from an input bit, backward from an output
bit, through combinational cells to the first registers (included), at
most CONE_CELLS cells (`capped` counts the bits that hit it); its
breadth is the most cells at one logic level. At most SAMPLE bits per
bus, evenly spaced.

Stdlib only.
"""

import argparse
import hashlib
import json
import math
import re
import sys

TOOL = "netlist 1"
WIDTH = 16
MIN_G = 4
CONE_CELLS = 1024
SAMPLE = 8
BIG_NET = 1000
FT_CELLS = 8
FANOUT_TOP = 20


def bus_of(name):
    return re.sub(r"\[[0-9]+\]$", "", name)


class Netlist:
    def __init__(self, lines):
        cell_ix = {}
        self.seq = []
        self.hard = []
        self.port_names = []
        self.port_dirs = []
        port_ix = {}
        nets = []
        self.block = None
        for line in lines:
            f = line.rstrip("\n").split("\t")
            k = f[0]
            if k == "n":
                nets.append(
                    (f[1], f[2] if len(f) > 2 else "", f[3] if len(f) > 3 else "")
                )
            elif k == "c":
                cell_ix[f[1]] = len(self.seq)
                self.seq.append(f[2] == "1")
                self.hard.append(len(f) > 3 and f[3] == "1")
            elif k == "b":
                self.block = f[1]
            elif k == "p":
                port_ix[f[1]] = len(self.port_names)
                self.port_names.append(f[2])
                self.port_dirs.append(f[3])
        n = len(self.seq)
        self.n = n
        # per net: cells (unique), drivers, sinks, ports
        self.net_cells = []
        self.net_drv = []
        self.net_snk = []
        self.net_ports = []
        self.cell_nets = [[] for _ in range(n)]
        self.cell_out = [[] for _ in range(n)]
        self.cell_in = [[] for _ in range(n)]
        self.port_net = [None] * len(self.port_names)
        pins = 0
        self.net_names = []
        for drv, snk, name in nets:
            self.net_names.append(name)
            ni = len(self.net_cells)
            cells = []
            d_cells = []
            s_cells = []
            ports = []
            for ends, out in ((drv, d_cells), (snk, s_cells)):
                for e in ends.split(","):
                    if not e:
                        continue
                    pins += 1
                    if e[0] == "p":
                        p = port_ix.get(e[1:])
                        if p is not None:
                            ports.append(p)
                            self.port_net[p] = ni
                    else:
                        c = cell_ix[e]
                        out.append(c)
                        cells.append(c)
            cells = sorted(set(cells))
            self.net_cells.append(cells)
            self.net_drv.append(d_cells)
            self.net_snk.append(s_cells)
            self.net_ports.append(ports)
            for c in cells:
                self.cell_nets[c].append(ni)
            for c in set(d_cells):
                self.cell_out[c].append(ni)
            for c in set(s_cells):
                self.cell_in[c].append(ni)
        self.pins = pins

    # --- Rent's rule by recursive bisection ---------------------------------

    def _stamp(self):
        self.stamp += 1
        return self.stamp

    def _bfs(self, part, label, start):
        """Cells of `label` reachable from start, breadth first, over nets
        of at most BIG_NET cells (a wider one, a reset, says nothing about
        where a cell sits)."""
        stamp = self._stamp()
        cmark, nmark = self.cmark, self.nmark
        order = [start]
        cmark[start] = stamp
        i = 0
        while i < len(order):
            c = order[i]
            i += 1
            for ni in self.cell_nets[c]:
                if nmark[ni] == stamp:
                    continue
                nmark[ni] = stamp
                cs = self.net_cells[ni]
                if len(cs) > BIG_NET:
                    continue
                for x in cs:
                    if cmark[x] != stamp and part[x] == label:
                        cmark[x] = stamp
                        order.append(x)
        return order

    def _order(self, cells, part, label):
        """The part's cells breadth first from a far cell (the last one a
        search from its lowest reaches); components one after another."""
        done = self._stamp()
        out = []
        for s in cells:
            if self.dmark[s] == done:
                continue
            probe = self._bfs(part, label, s)
            comp = self._bfs(part, label, probe[-1])
            for c in comp:
                self.dmark[c] = done
            out.extend(comp)
        return out

    def _refine(self, cells, part, la, lb):
        """One pass: a cell moves to the other half when that cuts fewer
        nets inside the part and keeps each half within 45-55 %."""
        cnt = {}
        for c in cells:
            side = 0 if part[c] == la else 1
            for ni in self.cell_nets[c]:
                if len(self.net_cells[ni]) > BIG_NET:
                    continue
                v = cnt.get(ni)
                if v is None:
                    v = cnt[ni] = [0, 0]
                v[side] += 1
        size = [sum(1 for c in cells if part[c] == la), 0]
        size[1] = len(cells) - size[0]
        lo = 0.45 * len(cells)
        for c in cells:
            x = 0 if part[c] == la else 1
            y = 1 - x
            if size[x] - 1 < lo:
                continue
            g = 0
            for ni in self.cell_nets[c]:
                v = cnt.get(ni)
                if v is None:
                    continue
                if v[x] == 1 and v[y] > 0:
                    g += 1
                elif v[y] == 0 and v[x] > 1:
                    g -= 1
            if g > 0:
                for ni in self.cell_nets[c]:
                    v = cnt.get(ni)
                    if v is None:
                        continue
                    v[x] -= 1
                    v[y] += 1
                part[c] = lb if y == 1 else la
                size[x] -= 1
                size[y] += 1

    def _terminals(self, cells, part, label):
        stamp = self._stamp()
        nmark = self.nmark
        t = 0
        for c in cells:
            for ni in self.cell_nets[c]:
                if nmark[ni] == stamp:
                    continue
                nmark[ni] = stamp
                if self.net_ports[ni]:
                    t += 1
                    continue
                for x in self.net_cells[ni]:
                    if part[x] != label:
                        t += 1
                        break
        return t

    def rent(self, width=WIDTH, min_g=MIN_G):
        n = self.n
        if n < 2 * min_g:
            return {"p": None, "k": None, "levels": [], "fit": None}
        part = [0] * n
        self.stamp = 0
        self.cmark = [0] * n
        self.dmark = [0] * n
        self.nmark = [0] * len(self.net_cells)
        members = {0: list(range(n))}
        nports = sum(1 for p in self.port_net if p is not None)
        levels = [{"level": 0, "parts": 1, "g": n, "t": nports}]
        frontier = [0]
        next_label = 1
        level = 0
        while frontier:
            level += 1
            if len(frontier) > width:
                step = len(frontier) / width
                frontier = [frontier[int(i * step)] for i in range(width)]
            children = []
            for lab in frontier:
                cells = members.pop(lab)
                if len(cells) < 2 * min_g:
                    continue
                order = self._order(cells, part, lab)
                la, lb = next_label, next_label + 1
                next_label += 2
                half = len(order) // 2
                for c in order[:half]:
                    part[c] = la
                for c in order[half:]:
                    part[c] = lb
                self._refine(order, part, la, lb)
                a = [c for c in order if part[c] == la]
                b = [c for c in order if part[c] == lb]
                members[la] = a
                members[lb] = b
                children += [la, lb]
            for lab in list(members):
                if lab not in children:
                    members.pop(lab)
            if not children:
                break
            gs, ts = [], []
            for lab in children:
                gs.append(len(members[lab]))
                ts.append(self._terminals(members[lab], part, lab))
            levels.append(
                {
                    "level": level,
                    "parts": len(children),
                    "g": round(sum(gs) / len(gs), 3),
                    "t": round(sum(ts) / len(ts), 3),
                }
            )
            frontier = [lab for lab in children if len(members[lab]) >= 2 * min_g]
        pts = [
            (math.log(L["g"]), math.log(L["t"]))
            for L in levels[2:]
            if L["g"] >= min_g and L["t"] > 0
        ]
        fit = [lv["level"] for lv in levels[2:] if lv["g"] >= min_g and lv["t"] > 0]
        if len(pts) < 2:
            return {"p": None, "k": None, "levels": levels, "fit": None}
        mx = sum(x for x, _ in pts) / len(pts)
        my = sum(y for _, y in pts) / len(pts)
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        sxy = sum((x - mx) * (y - my) for x, y in pts)
        p = sxy / sxx if sxx > 0 else 0.0
        k = math.exp(my - p * mx)
        return {
            "p": round(p, 4),
            "k": round(k, 4),
            "levels": levels,
            "fit": [fit[0], fit[-1]],
        }

    # --- each port's cone ---------------------------------------------------

    def cone(self, port, cap=CONE_CELLS):
        """(cells, breadth, capped) of a port bit's cone to the first
        registers."""
        ni = self.port_net[port]
        if ni is None:
            return 0, 0, False
        forward = self.port_dirs[port] == "input"
        seen = set()
        nets_seen = {ni}
        frontier = [ni]
        breadth = 0
        while frontier and len(seen) < cap:
            level = []
            for n in frontier:
                for c in self.net_snk[n] if forward else self.net_drv[n]:
                    if c not in seen:
                        seen.add(c)
                        level.append(c)
            breadth = max(breadth, len(level))
            nxt = []
            for c in level:
                if self.seq[c]:
                    continue
                for n in self.cell_out[c] if forward else self.cell_in[c]:
                    if n not in nets_seen:
                        nets_seen.add(n)
                        nxt.append(n)
            frontier = nxt
        return min(len(seen), cap), breadth, len(seen) >= cap

    def feedthrough(self, port):
        """(cells, nets) of an input bit's chain to an output port, else None."""
        if self.port_dirs[port] != "input":
            return None
        ni = self.port_net[port]
        cells = 0
        nets = 0
        while ni is not None and cells <= FT_CELLS:
            nets += 1
            snk = self.net_snk[ni]
            outs = [p for p in self.net_ports[ni] if self.port_dirs[p] == "output"]
            if outs:
                return (cells, nets) if not snk and len(outs) == 1 else None
            if len(snk) != 1:
                return None
            c = snk[0]
            if self.seq[c] or len(self.cell_in[c]) != 1 or len(self.cell_out[c]) != 1:
                return None
            cells += 1
            ni = self.cell_out[c][0]
        return None

    def buses(self, sample=SAMPLE, cap=CONE_CELLS):
        by = {}
        for i, name in enumerate(self.port_names):
            by.setdefault(bus_of(name), []).append(i)
        out = {}
        for bus, ports in sorted(by.items()):
            ports.sort(key=lambda i: self.port_names[i])
            if len(ports) > sample:
                step = len(ports) / sample
                pick = [ports[int(i * step)] for i in range(sample)]
            else:
                pick = ports
            cs = [self.cone(p, cap) for p in pick]
            ft = [self.feedthrough(p) for p in ports]
            out[bus] = {
                "feedthrough": sum(1 for x in ft if x),
                "bits": len(ports),
                "sampled": len(pick),
                "cells_mean": round(sum(c[0] for c in cs) / len(cs), 3),
                "breadth_mean": round(sum(c[1] for c in cs) / len(cs), 3),
                "breadth_max": max(c[1] for c in cs),
                "capped": sum(1 for c in cs if c[2]),
            }
        return out


def fanout(nl, top=FANOUT_TOP):
    rows = []
    for ni in range(len(nl.net_cells)):
        k = len(nl.net_snk[ni]) + sum(
            1 for p in nl.net_ports[ni] if nl.port_dirs[p] == "output"
        )
        if k >= 2:
            rows.append((k, ni))
    rows.sort(key=lambda r: (-r[0], r[1]))
    out = []
    for k, ni in rows[:top]:
        d = nl.net_drv[ni]
        if any(nl.port_dirs[p] == "input" for p in nl.net_ports[ni]):
            kind = "port"
        elif d and nl.hard[d[0]]:
            kind = "hard"
        elif d and nl.seq[d[0]]:
            kind = "register"
        else:
            kind = "logic"
        out.append({"net": nl.net_names[ni], "sinks": k, "driver": kind})
    return out


def build(lines, dump_hash):
    nl = Netlist(lines)
    ft = [x for x in (nl.feedthrough(p) for p in range(len(nl.port_names))) if x]
    return {
        "feedthrough": {
            "bits": len(ft),
            "cells": sum(c for c, _ in ft),
            "connections": sum(n for _, n in ft),
        },
        "block": nl.block,
        "identity": {"dump": "sha256:" + dump_hash, "tool": TOOL},
        "insts": nl.n,
        "fanout": fanout(nl),
        "nets": len(nl.net_cells),
        "pins": nl.pins,
        "rent": nl.rent(),
        "buses": nl.buses(),
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump", help="extract_netlist.tcl's dump")
    ap.add_argument("out", help="the netlist.json to write")
    args = ap.parse_args(argv)
    with open(args.dump, "rb") as f:
        raw = f.read()
    out = build(raw.decode().splitlines(), hashlib.sha256(raw).hexdigest())
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
