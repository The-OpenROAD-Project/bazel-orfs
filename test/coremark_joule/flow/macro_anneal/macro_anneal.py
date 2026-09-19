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
             channel between them -- by default exactly two halos, so
             the halos abut and no standard-cell row exists between
             banks for pdngen to have to power
  ballast    the standard-cell area under each module path at the same
             depth becomes a square block too, scaled so macros and logic
             together fill --fill of the core, so banks land next to the
             logic that reads them rather than in a corner
  pack       blocks are shelf-packed left to right into rows across the
             core with a gap wide enough for a power-strap pair: legal by
             construction, so the search is over order only
  anneal     simulated annealing over the block order; cost is the
             connectivity-weighted Manhattan distance between block
             centres plus a hard penalty for overrunning the core height
  emit       place_macro for every bank, origins snapped so the lowest-
             layer signal pins land on routing tracks, then FIRM
  straps     a macro narrower than one power-strap pitch can sit between
             two stripes and get no power at all (pdngen: grid contains
             no shapes or vias). Such banks step by a common multiple of
             the track and strap pitches and the block origin is nudged
             along the tracks until a stripe pair lies inside every
             bank's power rails

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
        self.track_patterns = {}  # (layer, "V"|"H") -> [(origin, count, step)]
        self.masters = {}  # name -> dict(w, h, vlayer, pox, hlayer, poy)
        self.pin_layers = {}  # master -> {"V": [layers], "H": [layers]}
        self.macros = []  # (inst, master)
        self.module_area = {}  # path -> dbu^2
        self.nets = collections.Counter()  # (macro inst, key) -> count
        self.edges = {}  # master -> {"L","R","B","T": pin count}
        self.net_edges = collections.Counter()  # (macro inst, key, edge) -> count

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
            elif kind == "trackpat":
                inv.track_patterns.setdefault((f[1], f[2]), []).append(
                    (int(f[3]), int(f[4]), int(f[5]))
                )
            elif kind == "pinlayers":
                inv.pin_layers.setdefault(f[1], {})[f[2]] = f[3:]
            elif kind == "master":
                inv.masters[f[1]] = {
                    "name": f[1],
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
            elif kind == "edges":
                inv.edges[f[1]] = dict(zip("LRBT", (int(x) for x in f[2:6])))
            elif kind == "netedge":
                inv.net_edges[(f[1], f[2], f[3])] += int(f[4])
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
    """Near-square grid of n banks of w x h with a channel: (cols, rows, W, H).

    The channel sits between banks only; a block's outer edge is the
    banks' own, and the packer keeps blocks apart.
    """
    cols = max(1, int(math.ceil(math.sqrt(n * h / float(w)))))
    cols = min(cols, n)
    rows = int(math.ceil(n / float(cols)))
    width = cols * w + (cols - 1) * chan
    height = rows * h + (rows - 1) * chan
    return cols, rows, width, height


class Straps:
    """The vertical power stripes pdngen will draw, as the platform declares them.

    ``pitch``, ``offset`` (from the core's left edge), ``pair`` (the span of
    one VDD+VSS pair) and ``inset`` (how far inside a macro's edge a stripe
    has to be to reach its rails), all in dbu. Zero pitch means unknown,
    and no alignment is attempted.
    """

    def __init__(self, pitch=0, offset=0, pair=0, inset=0):
        self.pitch, self.offset, self.pair, self.inset = pitch, offset, pair, inset

    def can_miss(self, width):
        """Whether a macro this wide can sit between two stripe pairs."""
        return self.pitch > 0 and width < self.pitch + self.pair + 2 * self.inset

    def pair_inside(self, x0, x, width):
        """Whether some stripe pair lies within the rails of a macro at x."""
        lo, hi = x + self.inset, x + width - self.inset
        k = int(math.floor((lo - x0 - self.offset) / float(self.pitch)))
        for j in (k, k + 1, k + 2):
            s = x0 + self.offset + j * self.pitch
            if s >= lo and s + self.pair <= hi:
                return True
        return False


class Block:
    def __init__(self, key, w, h, macros=None, master=None):
        self.key = key
        self.w = w
        self.h = h
        self.macros = macros or []  # instance names, tiled in this order
        self.master = master
        self.x = 0
        self.y = 0
        self.halo = (
            None  # dbu each side keeps clear; the packer's default gap/2 if None
        )
        self.chan = None  # dbu between the banks of a macro block

    @property
    def cx(self):
        return self.x + self.w / 2.0

    @property
    def cy(self):
        return self.y + self.h / 2.0

    def is_macro(self):
        return bool(self.macros)


def build_blocks(
    inv, depth, min_cluster, chan, fill, straps=None, channel_auto=False, gap=0
):
    """Macro blocks, ballast blocks, and the residual macros left to RTL-MP."""
    straps = straps or Straps()
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
        # The channel between two banks carries the pins of the two facing
        # sides; with channel_auto it is widened to what they need (the
        # sum is the same whichever way the banks are flipped).
        chan_b = chan
        if channel_auto:
            chan_b = max(
                chan,
                escape_need(inv, master, "R") + escape_need(inv, master, "L"),
                escape_need(inv, master, "T") + escape_need(inv, master, "B"),
            )
        cols, rows, _w, _h = tile_shape(len(insts), m["w"], m["h"], chan_b)
        # Banks step by a whole number of the origin lattice (the pin
        # layers' common track period, or the lowest pin layer's pitch
        # when the inventory has no patterns), so snapping the first bank
        # onto its tracks puts every bank on them and the channel between
        # neighbours is the same everywhere, never less than asked for.
        step_x = _multiple_of(m["w"] + chan_b, _pitch_of(inv, m, "V"))
        step_y = _multiple_of(m["h"] + chan_b, _pitch_of(inv, m, "H"))
        if straps.can_miss(m["w"]):
            # Every bank of the block must see a stripe pair, so the step
            # is a multiple of the strap pitch as well as of the track.
            step_x = _multiple_of(step_x, _lcm(straps.pitch, _pitch_of(inv, m, "V")))
        b = Block(
            pfx,
            (cols - 1) * step_x + m["w"],
            (rows - 1) * step_y + m["h"],
            insts,
            master,
        )
        b.cols = cols
        b.step_x = step_x
        b.step_y = step_y
        b.chan = chan_b
        if channel_auto:
            # The block's halo per side is what that side's pins need: the
            # bank rows' pins along a vertical side, the columns' along a
            # horizontal one. Two facing halos add up to their channel. A
            # flip about the x axis (the one a pin-fitted mock can have,
            # see flip_legal) swaps bottom and top, so those two share the
            # larger need; left and right keep their own.
            nl = rows * escape_need(inv, master, "L")
            nr = rows * escape_need(inv, master, "R")
            nb = cols * max(
                escape_need(inv, master, "B"), escape_need(inv, master, "T")
            )
            b.halo = {
                "L": max(gap // 2, nl),
                "R": max(gap // 2, nr),
                "B": max(gap // 2, nb),
                "T": max(gap // 2, nb),
            }
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
    """Shelf-pack blocks into rows across the core; returns the height used.

    ``gap`` separates blocks from each other and from the core edge. It
    has to hold a power-strap pair, or the standard cells the placer puts
    there end up in a channel pdngen cannot connect.
    """

    def __init__(self, inv, gap):
        self.x0, self.y0, self.x1, self.y1 = inv.core
        self.chan = gap

    def pack(self, blocks, order):
        # Each block keeps its halo clear per side (gap/2 unless the block
        # asked for more, see build_blocks). Neighbours in a row are the
        # right halo of one plus the left halo of the next apart; rows are
        # the lower row's tallest top halo plus the upper row's tallest
        # bottom halo apart, so a uniform halo reproduces the plain gap.
        half = self.chan // 2

        def halo(b, side):
            return half if b.halo is None else b.halo[side]

        rows = []
        cur = []
        x = self.x0 + self.chan
        for i in order:
            b = blocks[i]
            if cur:
                x = cur[-1].x + cur[-1].w + halo(cur[-1], "R") + halo(b, "L")
                if x + b.w + self.chan > self.x1:
                    rows.append(cur)
                    cur = []
                    x = self.x0 + self.chan
            b.x = x
            cur.append(b)
        if cur:
            rows.append(cur)
        y = self.y0 + self.chan
        top = y
        prev = None
        for row in rows:
            if prev is not None:
                y = (
                    top
                    + max(halo(b, "T") for b in prev)
                    + max(halo(b, "B") for b in row)
                )
            for b in row:
                b.y = y
            prev = row
            top = y + max(b.h for b in row)
        return top + self.chan


class Anneal:
    def __init__(self, inv, blocks, weights, gap, seed, iterations):
        self.inv = inv
        self.blocks = blocks
        self.weights = weights
        self.packer = Packer(inv, gap)
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


def _lcm(a, b):
    if a <= 0 or b <= 0:
        return max(a, b, 1)
    return a * b // math.gcd(a, b)


def _multiple_of(length, unit):
    return int(math.ceil(length / float(unit))) * unit if unit > 0 else length


def track_residues(inv, layer, axis):
    """(period, sorted residues) of a layer's tracks along an axis.

    The tracks of one layer may be several interleaved patterns (asap7's
    M2 y-grid is seven patterns of period 0.27 um, spaced 0.036 six times
    and 0.045 once), so the grid repeats with the patterns' common period
    and a track sits at each residue in it. None when the inventory has no
    patterns for the layer.
    """
    pats = inv.track_patterns.get((layer, axis))
    if not pats:
        return None
    period = 0
    for _, _, step in pats:
        if step > 0:
            period = _lcm(period, step) if period else step
    if not period:
        return None
    residues = set()
    for origin, _, step in pats:
        if step > 0:
            for k in range(period // step):
                residues.add((origin + k * step) % period)
    return period, sorted(residues)


def lattice(inv, master_name, axis):
    """Origin step along an axis that keeps every pin layer's tracks in phase.

    A block's tracks and the parent's both start at their die origin, so
    a macro origin that is a multiple of the common period of all the
    layers its pins use (asap7 with pins on M2 and M4: 2.16 um in y; M3
    and M5: 0.144 um in x) lands every pin on a parent track. Zero when
    the inventory does not say which layers the pins use.
    """
    lat = 0
    for layer in inv.pin_layers.get(master_name, {}).get(axis, []):
        tr = track_residues(inv, layer, axis)
        if tr:
            lat = _lcm(lat, tr[0]) if lat else tr[0]
    return lat


def flip_legal(inv, master_name, orient):
    """Whether a flip keeps the master's pins on tracks.

    A flip about the y axis moves a pin from x to w - x; the pins stay on
    tracks when the mirror image of each vertical pin layer's track set is
    the set itself, which is a property of the master's width alone (M3
    at pitch 0.036 from 0.009 needs w == 0.018 mod 0.036). Both layers of
    a two-layer edge must agree, and some pairs never can (asap7's M3 and
    M5 on one edge have no width both accept). R0 is always legal, and so
    is anything the inventory has no patterns for.
    """
    m = inv.masters[master_name]
    checks = []
    if orient in ("MY", "R180"):
        checks.append(("V", m["w"]))
    if orient in ("MX", "R180"):
        checks.append(("H", m["h"]))
    for axis, size in checks:
        for layer in inv.pin_layers.get(master_name, {}).get(axis, []):
            tr = track_residues(inv, layer, axis)
            if not tr:
                continue
            period, residues = tr
            mirrored = sorted(set((size - r) % period for r in residues))
            if mirrored != residues:
                return False
    return True


def layer_density(inv, master_name, axis):
    """Tracks per dbu across the layers a master's pins use on an axis.

    The wires leaving a side travel along its channel on the layers that
    run that way (vertical layers along a vertical channel), so the width
    a channel needs is pins over this density. Only the pin layers are
    counted, the layers the wires arrive on: a conservative floor for a
    channel that has more layers above them. Falls back to the lowest pin
    layer's pitch when the inventory has no patterns; zero when it has no
    tracks at all.
    """
    d = 0.0
    for layer in inv.pin_layers.get(master_name, {}).get(axis, []):
        tr = track_residues(inv, layer, axis)
        if tr:
            d += len(tr[1]) / float(tr[0])
    if d == 0.0:
        m = inv.masters[master_name]
        track = inv.tracks.get((m["vlayer"] if axis == "V" else m["hlayer"], axis))
        if track and track[1] > 0:
            d = 1.0 / track[1]
    return d


def escape_need(inv, master_name, edge, orient="R0"):
    """dbu of channel the pins on a placed edge of a flipped master need.

    Every pin is a wire that leaves through the channel along its side and
    runs along it: pins on a left or right edge into a vertical channel on
    vertical layers, bottom and top into a horizontal one. ``edge`` is the
    placed edge; the flip says which of the master's own edges lands there.
    This is the demand of one side; a channel between two macros carries
    both facing sides.
    """
    own = [e for e, placed in FLIPS[orient].items() if placed == edge][0]
    pins = inv.edges.get(master_name, {}).get(own, 0)
    if not pins:
        return 0
    d = layer_density(inv, master_name, "V" if edge in "LR" else "H")
    return int(math.ceil(pins / d)) if d > 0 else 0


def channel_shortfalls(inv, placed):
    """Channels between facing macros narrower than their pins need.

    For every pair of placed macros that face each other across a gap with
    no third macro between them, the channel is the gap, the demand is the
    pins on the two facing sides, and the shortfall is demand over width.
    Returns (a_inst, a_edge, b_inst, b_edge, width_dbu, need_dbu), largest
    shortfall first. The router finds these hours later as overflow on the
    GCell edges along the sides; here they cost a second.
    """
    rects = []
    for inst, master, x, y, orient in placed:
        m = inv.masters[master]
        rects.append((inst, master, orient, x, y, x + m["w"], y + m["h"]))
    needs = {}

    def need(r, edge):
        key = (r[1], r[2], edge)
        if key not in needs:
            needs[key] = escape_need(inv, r[1], edge, r[2])
        return needs[key]

    out = []
    for i, a in enumerate(rects):
        for j, b in enumerate(rects):
            if i == j:
                continue
            if b[3] >= a[5] and min(a[6], b[6]) > max(a[4], b[4]):
                width, ea, eb = b[3] - a[5], "R", "L"
            elif b[4] >= a[6] and min(a[5], b[5]) > max(a[3], b[3]):
                width, ea, eb = b[4] - a[6], "T", "B"
            else:
                continue
            total = need(a, ea) + need(b, eb)
            if total <= width:
                continue
            between = False
            for k, c in enumerate(rects):
                if k in (i, j):
                    continue
                if ea == "R":
                    if (
                        c[3] >= a[5]
                        and c[5] <= b[3]
                        and min(c[6], a[6], b[6]) > max(c[4], a[4], b[4])
                    ):
                        between = True
                        break
                elif (
                    c[4] >= a[6]
                    and c[6] <= b[4]
                    and min(c[5], a[5], b[5]) > max(c[3], a[3], b[3])
                ):
                    between = True
                    break
            if not between:
                out.append((a[0], ea, b[0], eb, width, total))
    out.sort(key=lambda t: t[5] - t[4], reverse=True)
    return out


def _pitch_of(inv, master, axis):
    lat = lattice(inv, master["name"], axis) if "name" in master else 0
    if lat:
        return lat
    layer = master["vlayer"] if axis == "V" else master["hlayer"]
    track = inv.tracks.get((layer, axis))
    return track[1] if track and track[1] > 0 else 1


def _track_multiple(length, track):
    """``length`` rounded up to a whole number of the track's pitch."""
    if not track or track[1] <= 0:
        return length
    pitch = track[1]
    return int(math.ceil(length / float(pitch))) * pitch


def snap_up(value, offset, pitch):
    """Smallest v >= value with v == offset (mod pitch)."""
    if pitch <= 0:
        return value
    k = int(math.ceil((value - offset) / float(pitch)))
    return offset + k * pitch


# A flip mirrors which edge a pin is on: MX about the x axis (bottom and
# top swap), MY about the y axis (left and right), R180 both.
FLIPS = {
    "R0": {"L": "L", "R": "R", "B": "B", "T": "T"},
    "MX": {"L": "L", "R": "R", "B": "T", "T": "B"},
    "MY": {"L": "R", "R": "L", "B": "B", "T": "T"},
    "R180": {"L": "R", "R": "L", "B": "T", "T": "B"},
}


def pin_offsets(m, orient):
    """The lowest-layer pin offsets of master m under a flip."""
    pox = m["w"] - m["pox"] if orient in ("MY", "R180") else m["pox"]
    poy = m["h"] - m["poy"] if orient in ("MX", "R180") else m["poy"]
    return pox, poy


def choose_orientation(inv, inst, master, x, y, centres):
    """The flip that turns the macro's connected pins toward what they connect to.

    Each connection from an edge of the macro pulls that edge toward its
    target: another placed macro's centre, or the core centre for the
    parent's cells, which are placed later and everywhere. The cost of an
    orientation is the pin-weighted Manhattan distance from each edge's
    midpoint, after the flip, to its targets; R0 wins ties, so a macro with
    evenly spread pins keeps R0.
    """
    m = inv.masters[master]
    w, h = m["w"], m["h"]
    cx0, cy0 = (inv.core[0] + inv.core[2]) / 2.0, (inv.core[1] + inv.core[3]) / 2.0
    pulls = []  # (edge, weight, tx, ty)
    for (mi, key, edge), n in inv.net_edges.items():
        if mi != inst:
            continue
        if key.startswith("macro:"):
            other = centres.get(key[len("macro:") :])
            if other is None:
                continue
            tx, ty = other
        else:
            tx, ty = cx0, cy0
        pulls.append((edge, n, tx, ty))
    if not pulls:
        return "R0"
    mid = {
        "L": (x, y + h / 2.0),
        "R": (x + w, y + h / 2.0),
        "B": (x + w / 2.0, y),
        "T": (x + w / 2.0, y + h),
    }
    best, best_cost = "R0", None
    for orient in ("R0", "MX", "MY", "R180"):
        if not flip_legal(inv, master, orient):
            continue
        cost = 0.0
        for edge, n, tx, ty in pulls:
            ex, ey = mid[FLIPS[orient][edge]]
            cost += n * (abs(ex - tx) + abs(ey - ty))
        if best_cost is None or cost < best_cost - 1e-9:
            best, best_cost = orient, cost
    return best


def macro_origin(inv, master, x, y, orient="R0"):
    """Origin at or after (x, y) whose lowest-layer pins sit on tracks."""
    m = inv.masters[master]
    lx, ly = lattice(inv, master, "V"), lattice(inv, master, "H")
    if lx or ly:
        # Every pin layer known: the origin is a whole number of lattice
        # steps from the die origin, which is where both the block's and
        # the parent's tracks start, so every pin on every layer is on a
        # track whatever the flip (flip_legal says which flips keep the
        # block's own pins on its tracks).
        ox = snap_up(x, inv.die[0] % lx, lx) if lx else x
        oy = snap_up(y, inv.die[1] % ly, ly) if ly else y
    else:
        vt = inv.tracks.get((m["vlayer"], "V"))
        ht = inv.tracks.get((m["hlayer"], "H"))
        pox, poy = pin_offsets(m, orient)
        ox = snap_up(x + pox, vt[0], vt[1]) - pox if vt else x
        oy = snap_up(y + poy, ht[0], ht[1]) - poy if ht else y
    g = inv.mfg_grid
    ox = int(math.ceil(ox / float(g))) * g
    oy = int(math.ceil(oy / float(g))) * g
    return ox, oy


def placements(inv, blocks, chan, straps=None, flips=True):
    """(inst, master, x, y, orient) in dbu for every macro in every macro block.

    Positions first, for every macro; then each macro's flip, chosen against
    the centres those positions give (a flip keeps the outline, so nothing
    moves), and the origin re-snapped so the flipped pins land on tracks.
    """
    straps = straps or Straps()
    out = []
    for b in blocks:
        if not b.is_macro():
            continue
        m = inv.masters[b.master]
        ox0, oy0 = macro_origin(inv, b.master, b.x, b.y)
        if straps.can_miss(m["w"]):
            # Nudge the block origin along the tracks until the first bank
            # holds a stripe pair; the step keeps every other bank in phase.
            tp = _pitch_of(inv, m, "V")
            for _ in range(int(straps.pitch // tp) + 2):
                if straps.pair_inside(inv.core[0], ox0, m["w"]):
                    break
                ox0, _ = macro_origin(inv, b.master, ox0 + tp, oy0)
        for k, inst in enumerate(b.macros):
            col, row = k % b.cols, k // b.cols
            out.append((inst, b.master, ox0 + col * b.step_x, oy0 + row * b.step_y))
    centres = {}
    for inst, master, x, y in out:
        m = inv.masters[master]
        centres[inst] = (x + m["w"] / 2.0, y + m["h"] / 2.0)
    oriented = []
    for inst, master, x, y in out:
        orient = choose_orientation(inv, inst, master, x, y, centres) if flips else "R0"
        if orient != "R0":
            x, y = macro_origin(inv, master, x, y, orient)
        oriented.append((inst, master, x, y, orient))
    return oriented


def check_legal(inv, blocks, placed):
    """Every placed macro inside the core and no two overlapping."""
    problems = []
    x0, y0, x1, y1 = inv.core
    rects = []
    for inst, master, x, y, _ in placed:
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
    for inst, master, x, y, orient in placed:
        lines.append(
            "place_macro -macro_name {{{}}} -location {{{:.4f} {:.4f}}} "
            "-orientation {} -exact".format(inst, x / dbu, y / dbu, orient)
        )
    lines.append("foreach n {")
    for inst, _, _, _, _ in placed:
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
    p.add_argument(
        "--channel-um",
        type=float,
        default=4.0,
        help="between banks of one block; two halos, so the halos abut and no "
        "row is left between banks (default 4.0 for a 2 um halo)",
    )
    p.add_argument(
        "--block-gap-um",
        type=float,
        default=10.8,
        help="between blocks, and from the core edge; wide enough for a "
        "power-strap pair (default 10.8, two 5.4 um strap pitches)",
    )
    p.add_argument("--fill", type=float, default=0.6)
    p.add_argument(
        "--strap-pitch-um",
        type=float,
        default=0.0,
        help="pitch of the platform's vertical power stripes on the layer the "
        "macro grid connects to; 0 disables strap alignment",
    )
    p.add_argument(
        "--strap-offset-um",
        type=float,
        default=0.0,
        help="first stripe from the core's left edge",
    )
    p.add_argument(
        "--strap-pair-um",
        type=float,
        default=0.0,
        help="span of one VDD+VSS stripe pair",
    )
    p.add_argument(
        "--strap-inset-um",
        type=float,
        default=0.2,
        help="how far inside a macro edge a stripe must lie",
    )
    p.add_argument("--iterations", type=int, default=20000)
    p.add_argument("--same-prefix-bonus", type=float, default=1000.0)
    p.add_argument(
        "--channel-auto",
        action="store_true",
        help="widen each bank channel and each block's clearance to what the "
        "pins on the facing sides need (pins over the track density of the "
        "layers running along the channel); off, the widths given above "
        "are used and shortfalls are only reported",
    )
    p.add_argument(
        "--channel-check",
        choices=("warn", "error"),
        default="warn",
        help="what a channel narrower than its pins need does: a line on "
        "stderr and in the metrics, or a failed floorplan",
    )
    args = p.parse_args(argv[1:])

    with open(args.inventory) as f:
        inv = Inventory.parse(f.read())
    chan = int(round(args.channel_um * inv.dbu))
    gap = int(round(args.block_gap_um * inv.dbu))
    straps = Straps(
        int(round(args.strap_pitch_um * inv.dbu)),
        int(round(args.strap_offset_um * inv.dbu)),
        int(round(args.strap_pair_um * inv.dbu)),
        int(round(args.strap_inset_um * inv.dbu)),
    )
    blocks, residual = build_blocks(
        inv,
        args.depth,
        args.min_cluster,
        chan,
        args.fill,
        straps,
        channel_auto=args.channel_auto,
        gap=gap,
    )
    weights = build_weights(inv, blocks, args.depth, args.same_prefix_bonus)
    anneal = Anneal(inv, blocks, weights, gap, args.seed, args.iterations)
    order, cost = anneal.run()
    placed = placements(inv, blocks, chan, straps)
    problems = check_legal(inv, blocks, placed)
    shortfalls = channel_shortfalls(inv, placed)
    for a, ea, b, eb, width, need in shortfalls[:40]:
        print(
            "macro_anneal: channel {:.1f} um between {} ({}) and {} ({}): "
            "their pins need {:.1f} um".format(
                width / inv.dbu, a, ea, b, eb, need / inv.dbu
            ),
            file=sys.stderr,
        )
    if shortfalls:
        print(
            "macro_anneal: {} channel(s) narrower than their pins need; the "
            "router would find them as overflow along the macro sides "
            "(--channel-auto widens them)".format(len(shortfalls)),
            file=sys.stderr,
        )
        if args.channel_check == "error":
            problems.append(
                "{} channels narrower than their pins need".format(len(shortfalls))
            )
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
        "channel_shortfalls": [
            {
                "a": a,
                "a_edge": ea,
                "b": b,
                "b_edge": eb,
                "width_um": width / inv.dbu,
                "need_um": need / inv.dbu,
            }
            for a, ea, b, eb, width, need in shortfalls[:200]
        ],
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
