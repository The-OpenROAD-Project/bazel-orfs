#!/usr/bin/env python3
"""Place a design's regular macro banks; leave the rest to RTL-MP.

XiangShan's XSCore carries 303 SRAM macros in 16 shapes, and almost all
of them are banks of something: 64 TAGE tables, 32 ways of L1D data, 32
of L1I data, 16 L2 TLB pages. RTL-MP is asked to discover that structure
from a flat list every time it runs. This tool reads the structure off
the hierarchy instead, tiles each bank group into one rectangular block,
arranges the blocks by how much they talk to each other and to the
standard-cell modules around them, and hands RTL-MP a floorplan in which
the banks are already FIRM. Whatever is too small or too irregular to be
a bank group is left unplaced for RTL-MP to finish.

Textbook throughout, and deliberately so:

  cluster    macros grouped by the `/`-separated prefix of their
             hierarchical instance name at a chosen depth, one block per
             (prefix, master); clusters below --min-cluster are residual
  tile       a block is a near-square grid of its banks with a fixed
             channel between them
  ballast    the standard-cell area under each module path at the same
             depth becomes a square block too, scaled so macros and logic
             together fill --fill of the core, so banks land next to the
             logic that reads them rather than in a corner
  pack       blocks are shelf-packed left to right into rows across the
             core: legal by construction, so the search is over order only
  anneal     simulated annealing over the block order; cost is the
             connectivity-weighted Manhattan distance between block
             centres plus a hard penalty for overrunning the core height
  emit       place_macro for every bank, origins snapped so the lowest-
             layer signal pins land on routing tracks, then FIRM

Stdlib only and seeded: the placement is a pure function of (inventory,
arguments, seed) and re-runs are byte-identical.

Usage: macro_anneal.py --inventory FILE --out placement.tcl [options]
The inventory is what dump_macros.tcl writes; see it for the format.
"""

import argparse
import collections
import json
import math
import random
import sys


class Inventory:
    def __init__(self):
        self.die = None
        self.core = None
        self.dbu = 1000
        self.mfg_grid = 1
        self.site = (1, 1)
        self.tracks = {}  # (layer, "V"|"H") -> (offset, pitch)
        self.masters = {}  # name -> dict(w, h, vlayer, pox, hlayer, poy)
        self.macros = []  # (inst, master)
        self.module_area = {}  # path -> dbu^2
        self.nets = collections.Counter()  # (macro inst, key) -> count

    @classmethod
    def parse(cls, text):
        inv = cls()
        for line in text.splitlines():
            f = line.split()
            if not f or f[0].startswith("#"):
                continue
            kind = f[0]
            if kind == "die":
                inv.die = tuple(int(x) for x in f[1:5])
                inv.dbu = int(f[6])
            elif kind == "core":
                inv.core = tuple(int(x) for x in f[1:5])
            elif kind == "mfg_grid":
                inv.mfg_grid = max(1, int(f[1]))
            elif kind == "site":
                inv.site = (int(f[1]), int(f[2]))
            elif kind == "track":
                inv.tracks[(f[1], f[2])] = (int(f[3]), int(f[4]))
            elif kind == "master":
                inv.masters[f[1]] = {
                    "w": int(f[2]),
                    "h": int(f[3]),
                    "vlayer": f[4],
                    "pox": int(f[5]),
                    "hlayer": f[6],
                    "poy": int(f[7]),
                }
            elif kind == "macro":
                inv.macros.append((f[1], f[2]))
            elif kind == "module":
                inv.module_area[f[1]] = inv.module_area.get(f[1], 0) + int(f[2])
            elif kind == "net":
                inv.nets[(f[1], f[2])] += int(f[3])
        if inv.die is None or inv.core is None:
            raise ValueError("inventory has no die/core lines")
        return inv


def prefix(path, depth):
    """The first `depth` `/`-segments of a module path; "/" for the top."""
    if path in ("", "/"):
        return "/"
    parts = path.split("/")
    return "/".join(parts[:depth])


def module_path_of(inst_name):
    parts = inst_name.split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else "/"


def tile_shape(n, w, h, chan):
    """Near-square grid of n banks of w x h with a channel: (cols, rows, W, H)."""
    cols = max(1, int(math.ceil(math.sqrt(n * h / float(w)))))
    cols = min(cols, n)
    rows = int(math.ceil(n / float(cols)))
    width = cols * w + (cols + 1) * chan
    height = rows * h + (rows + 1) * chan
    return cols, rows, width, height


class Block:
    def __init__(self, key, w, h, macros=None, master=None):
        self.key = key
        self.w = w
        self.h = h
        self.macros = macros or []  # instance names, tiled in this order
        self.master = master
        self.x = 0
        self.y = 0

    @property
    def cx(self):
        return self.x + self.w / 2.0

    @property
    def cy(self):
        return self.y + self.h / 2.0

    def is_macro(self):
        return bool(self.macros)


def build_blocks(inv, depth, min_cluster, chan, fill):
    """Macro blocks, ballast blocks, and the residual macros left to RTL-MP."""
    groups = collections.defaultdict(list)
    for inst, master in inv.macros:
        groups[(prefix(module_path_of(inst), depth), master)].append(inst)
    blocks = []
    residual = []
    for (pfx, master), insts in sorted(groups.items()):
        insts.sort()
        if len(insts) < min_cluster:
            residual.extend(insts)
            continue
        m = inv.masters[master]
        cols, rows, w, h = tile_shape(len(insts), m["w"], m["h"], chan)
        b = Block(pfx, w, h, insts, master)
        b.cols = cols
        blocks.append(b)
    macro_area = sum(b.w * b.h for b in blocks)
    core_w = inv.core[2] - inv.core[0]
    core_h = inv.core[3] - inv.core[1]
    budget = fill * core_w * core_h - macro_area
    ballast_raw = collections.Counter()
    for path, area in inv.module_area.items():
        ballast_raw[prefix(path, depth)] += area
    total_raw = sum(ballast_raw.values())
    scale = budget / float(total_raw) if total_raw > 0 and budget > 0 else 0.0
    for pfx, area in sorted(ballast_raw.items()):
        side = int(math.sqrt(area * scale))
        if side < chan:
            continue
        blocks.append(Block(pfx, side, side))
    return blocks, residual


def build_weights(inv, blocks, depth, same_prefix_bonus):
    """Symmetric weights between blocks from the macro pin connectivity."""
    by_macro = {}
    for i, b in enumerate(blocks):
        for inst in b.macros:
            by_macro[inst] = i
    ballast = {}
    for i, b in enumerate(blocks):
        if not b.is_macro():
            ballast[b.key] = i
    w = collections.Counter()
    for (inst, key), n in inv.nets.items():
        a = by_macro.get(inst)
        if a is None:
            continue
        if key.startswith("macro:"):
            bi = by_macro.get(key[len("macro:") :])
        else:
            bi = ballast.get(prefix(key, depth))
        if bi is None or bi == a:
            continue
        w[(min(a, bi), max(a, bi))] += n
    # Blocks of one prefix -- the tag and data arrays of one cache, the
    # tables of one predictor -- belong together whatever the pin counts
    # say.
    for i, a in enumerate(blocks):
        for j in range(i + 1, len(blocks)):
            if a.is_macro() and blocks[j].is_macro() and a.key == blocks[j].key:
                w[(i, j)] += same_prefix_bonus
    return w


class Packer:
    """Shelf-pack blocks into rows across the core; returns the height used."""

    def __init__(self, inv, chan):
        self.x0, self.y0, self.x1, self.y1 = inv.core
        self.chan = chan

    def pack(self, blocks, order):
        x = self.x0 + self.chan
        y = self.y0 + self.chan
        row_h = 0
        for i in order:
            b = blocks[i]
            if x + b.w + self.chan > self.x1 and x > self.x0 + self.chan:
                x = self.x0 + self.chan
                y += row_h + self.chan
                row_h = 0
            b.x, b.y = x, y
            x += b.w + self.chan
            row_h = max(row_h, b.h)
        return y + row_h + self.chan


class Anneal:
    def __init__(self, inv, blocks, weights, chan, seed, iterations):
        self.inv = inv
        self.blocks = blocks
        self.weights = weights
        self.packer = Packer(inv, chan)
        self.rng = random.Random(seed)
        self.iterations = iterations
        self.height_penalty = 1e9

    def cost(self, order):
        top = self.packer.pack(self.blocks, order)
        over = max(0, top - self.inv.core[3])
        dist = 0.0
        for (i, j), wgt in self.weights.items():
            a, b = self.blocks[i], self.blocks[j]
            dist += wgt * (abs(a.cx - b.cx) + abs(a.cy - b.cy)) / self.inv.dbu
        return dist + self.height_penalty * over / self.inv.dbu

    def propose(self, order):
        new = list(order)
        n = len(new)
        if n < 2:
            return new
        i, j = self.rng.sample(range(n), 2)
        if self.rng.random() < 0.5:
            new[i], new[j] = new[j], new[i]
        else:
            new.insert(j, new.pop(i))
        return new

    def run(self):
        order = list(range(len(self.blocks)))
        cur = self.cost(order)
        best, best_cost = list(order), cur
        # Initial temperature from the typical uphill move.
        deltas = []
        for _ in range(50):
            c = self.cost(self.propose(order))
            if c > cur:
                deltas.append(c - cur)
        t = (sum(deltas) / len(deltas)) if deltas else 1.0
        t = max(t, 1e-9)
        alpha = 0.001 ** (1.0 / max(1, self.iterations))
        for _ in range(self.iterations):
            cand = self.propose(order)
            c = self.cost(cand)
            if c <= cur or self.rng.random() < math.exp(-(c - cur) / t):
                order, cur = cand, c
                if cur < best_cost:
                    best, best_cost = list(order), cur
            t *= alpha
        self.packer.pack(self.blocks, best)
        return best, best_cost


def snap_up(value, offset, pitch):
    """Smallest v >= value with v == offset (mod pitch)."""
    if pitch <= 0:
        return value
    k = int(math.ceil((value - offset) / float(pitch)))
    return offset + k * pitch


def macro_origin(inv, master, x, y):
    """Origin at or after (x, y) whose lowest-layer pins sit on tracks."""
    m = inv.masters[master]
    vt = inv.tracks.get((m["vlayer"], "V"))
    ht = inv.tracks.get((m["hlayer"], "H"))
    ox = snap_up(x + m["pox"], vt[0], vt[1]) - m["pox"] if vt else x
    oy = snap_up(y + m["poy"], ht[0], ht[1]) - m["poy"] if ht else y
    g = inv.mfg_grid
    ox = int(math.ceil(ox / float(g))) * g
    oy = int(math.ceil(oy / float(g))) * g
    return ox, oy


def placements(inv, blocks, chan):
    """(inst, master, x, y) in dbu for every macro in every macro block."""
    out = []
    for b in blocks:
        if not b.is_macro():
            continue
        m = inv.masters[b.master]
        for k, inst in enumerate(b.macros):
            col, row = k % b.cols, k // b.cols
            x = b.x + chan + col * (m["w"] + chan)
            y = b.y + chan + row * (m["h"] + chan)
            ox, oy = macro_origin(inv, b.master, x, y)
            out.append((inst, b.master, ox, oy))
    return out


def check_legal(inv, blocks, placed):
    """Every placed macro inside the core and no two overlapping."""
    problems = []
    x0, y0, x1, y1 = inv.core
    rects = []
    for inst, master, x, y in placed:
        m = inv.masters[master]
        r = (x, y, x + m["w"], y + m["h"])
        if r[0] < x0 or r[1] < y0 or r[2] > x1 or r[3] > y1:
            problems.append("{} outside core".format(inst))
        rects.append((inst, r))
    rects.sort(key=lambda t: (t[1][0], t[1][1]))
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i][1], rects[j][1]
            if b[0] >= a[2]:
                break
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                problems.append("{} overlaps {}".format(rects[i][0], rects[j][0]))
    return problems


def emit_tcl(inv, placed, residual, out_path):
    dbu = float(inv.dbu)
    lines = [
        "# Written by macro_anneal.py: {} banks placed FIRM, {} macros left "
        "to rtl_macro_placer.".format(len(placed), len(residual)),
        "set block [ord::get_db_block]",
    ]
    for inst, master, x, y in placed:
        lines.append(
            "place_macro -macro_name {{{}}} -location {{{:.4f} {:.4f}}} "
            "-orientation R0 -exact".format(inst, x / dbu, y / dbu)
        )
    lines.append("foreach n {")
    for inst, _, _, _ in placed:
        lines.append("    {{{}}}".format(inst))
    lines.append("} {")
    lines.append("    [$block findInst $n] setPlacementStatus FIRM")
    lines.append("}")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inventory", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--metrics", help="JSON summary of the run")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--depth", type=int, default=3, help="cluster prefix depth")
    p.add_argument("--min-cluster", type=int, default=4)
    p.add_argument("--channel-um", type=float, default=4.4)
    p.add_argument("--fill", type=float, default=0.6)
    p.add_argument("--iterations", type=int, default=20000)
    p.add_argument("--same-prefix-bonus", type=float, default=1000.0)
    args = p.parse_args(argv[1:])

    with open(args.inventory) as f:
        inv = Inventory.parse(f.read())
    chan = int(round(args.channel_um * inv.dbu))
    blocks, residual = build_blocks(inv, args.depth, args.min_cluster, chan, args.fill)
    weights = build_weights(inv, blocks, args.depth, args.same_prefix_bonus)
    anneal = Anneal(inv, blocks, weights, chan, args.seed, args.iterations)
    order, cost = anneal.run()
    placed = placements(inv, blocks, chan)
    problems = check_legal(inv, blocks, placed)
    top = max((b.y + b.h for b in blocks), default=inv.core[1])
    metrics = {
        "macros": len(inv.macros),
        "placed": len(placed),
        "residual": len(residual),
        "blocks": [
            {
                "key": b.key,
                "master": b.master,
                "banks": len(b.macros),
                "x_um": b.x / inv.dbu,
                "y_um": b.y / inv.dbu,
                "w_um": b.w / inv.dbu,
                "h_um": b.h / inv.dbu,
            }
            for b in blocks
        ],
        "cost": cost,
        "height_used_um": (top - inv.core[1]) / inv.dbu,
        "core_height_um": (inv.core[3] - inv.core[1]) / inv.dbu,
        "problems": problems,
    }
    if args.metrics:
        with open(args.metrics, "w") as f:
            json.dump(metrics, f, indent=2, sort_keys=True)
    if problems:
        for pr in problems:
            print("macro_anneal: " + pr, file=sys.stderr)
        return 1
    emit_tcl(inv, placed, residual, args.out)
    print(
        "macro_anneal: {} macros in {} blocks placed, {} left to rtl_macro_placer, "
        "height {:.1f} of {:.1f} um, cost {:.0f}".format(
            len(placed),
            sum(1 for b in blocks if b.is_macro()),
            len(residual),
            metrics["height_used_um"],
            metrics["core_height_um"],
            cost,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
