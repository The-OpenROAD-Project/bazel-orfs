#!/usr/bin/env python3
"""Plan macro shapes, places, pin edges and channel routing for a parent.

Input is synthesis only: per partition its std-cell area, the bits between
each pair of partitions, and the platform's pin and track pitches. Output is
per macro an outline and a place on the die, per edge the interface bundles
it carries in pin order with the share of one pin layer they need, and the
parent's routing demand against its capacity.

  shape     footprint = std_um2 * growth / util, unless the macro is fixed
            (a hardened block's outline); the aspect ratio is chosen from
            ASPECTS to minimise the macro's fullest edge
  place     global placement on the fixed die: quadratic wirelength (bits-
            weighted squared distance, Gauss-Seidel), then rounds in which a
            legaliser (largest macro first, at the free place nearest its
            quadratic position, a channel from every neighbour) anchors the
            next quadratic solve with a growing weight; the legal placement
            with the least wirelength wins; memories are macros like any
            other and block routing; a soft partition marked whitespace
            (the parent's own logic) fills the free space and pulls its
            partners toward the die centre; die sizes and aspect ratios are
            searched for the smallest die meeting the limits; deterministic
  edge      each bundle goes to the edge of each end that faces the other
            end; a bundle to a soft partition (the parent's own logic, split
            over several regions) goes to the region nearest the macro
  layer     an east or west edge places pins on the horizontal pin layer,
            north or south on the vertical one; one layer holds
            1 / (pitch * min_tracks * margin) pins per um of edge
  order     bundles on an edge are ordered by their partner's projection
            on it, so both ends of an interface face each other
  route     hard macros and memories block every routing layer; each bundle
            is routed on a gcell grid through the parent's free space only
            (channels and soft regions), shortest path under a congestion
            cost, and every gcell's demand is checked against its tracks
            (track_density per um per direction times the usable fraction)
  check     an edge over one layer needs a second (technical debt), over
            two it does not fit; a bundle with no path through free space
            would have to cross a macro; a gcell over capacity overflows

bazel-orfs's macro_select/plan_floorplan.py plans a ring of macros around
the parent's logic region, each with one pin side facing it; this plans
macros that also talk to each other, each edge its own pin side.

Input JSON: tech {pitch_um {H, V}, min_tracks, margin, track_density_per_um,
usable}; growth; util; channel_um; gcell_um; macros {name: {std_um2} or
{fixed_shape: [w, h]}, "memory": true for a memory macro, a soft partition
with "soft": true and, for the parent's logic, "whitespace": true}; nets [[a, b,
bits]]; optionally limits {edge, gcell}, die_slack, die_aspects; for
--evaluate, die {w, h}, placement {name: [x, y, w, h], a soft one a list of
such rects} and memories [[x, y, w, h]] as fixed blockages.

Stdlib only.
"""

import argparse
import heapq
import json
import math
import sys

ASPECTS = (1 / 6, 1 / 4, 1 / 3, 1 / 2, 2 / 3, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


def pins_per_um(tech, side):
    """Pins per um of one layer along an edge of `side`."""
    pitch = tech["pitch_um"]["H" if side in "EW" else "V"]
    return 1.0 / (pitch * tech["min_tracks"] * tech["margin"])


def footprint(m, plan):
    if "fixed_shape" in m:
        w, h = m["fixed_shape"]
        return w * h
    return m["std_um2"] * plan["growth"] / plan["util"]


def nets_by_pair(plan):
    bits = {}
    for a, b, n in (net[:3] for net in plan["nets"]):
        if a != b:
            k = tuple(sorted((a, b)))
            bits[k] = bits.get(k, 0) + n
    return bits


def center(r):
    return (r[0] + r[2] / 2, r[1] + r[3] / 2)


def gap_between(r, q):
    gx = max(q[0] - (r[0] + r[2]), r[0] - (q[0] + q[2]), 0)
    gy = max(q[1] - (r[1] + r[3]), r[1] - (q[1] + q[3]), 0)
    return math.hypot(gx, gy)


def side_toward(r, q):
    """Side of rect r facing rect q (y grows downward)."""
    oy = min(r[1] + r[3], q[1] + q[3]) - max(r[1], q[1])
    ox = min(r[0] + r[2], q[0] + q[2]) - max(r[0], q[0])
    (acx, acy), (bcx, bcy) = center(r), center(q)
    if oy > 0 and oy >= ox:
        return "E" if bcx > acx else "W"
    if ox > 0:
        return "S" if bcy > acy else "N"
    gx = max(q[0] - (r[0] + r[2]), r[0] - (q[0] + q[2]))
    gy = max(q[1] - (r[1] + r[3]), r[1] - (q[1] + q[3]))
    if gx >= gy:
        return "E" if bcx > acx else "W"
    return "S" if bcy > acy else "N"


def edge_span(r, side):
    """(fixed coordinate, start, end) of an edge."""
    x, y, w, h = r
    return {
        "N": (y, x, x + w),
        "S": (y + h, x, x + w),
        "W": (x, y, y + h),
        "E": (x + w, y, y + h),
    }[side]


def is_soft(plan, n):
    return plan["macros"][n].get("soft", False)


def whitespace(plan, n):
    """A soft partition with no rects of its own fills the parent's free space."""
    return plan["macros"][n].get("soft", False) and plan["macros"][n].get(
        "whitespace", False
    )


def regions(rects, n):
    """A soft partition is one rect or several."""
    r = rects[n]
    return r if isinstance(r[0], (list, tuple)) else [r]


def nearest_region(rects, soft, r):
    return min(regions(rects, soft), key=lambda q: (gap_between(r, q), q))


def soft_shares(plan, rects, me, soft):
    """A bundle to soft logic split over every region touching the macro, by the
    length of edge each faces; the nearest region takes it all when none touches."""
    r = rects[me]
    if whitespace(plan, soft):
        free = {}
        banned = plan.get("forbidden_sides", {}).get(me, ())
        for side in "NSEW":
            if side in banned:
                continue
            _, lo, hi = edge_span(r, side)
            fixed = edge_span(r, side)[0]
            outside = (
                fixed > plan["gcell_um"]
                if side in "NW"
                else (
                    fixed
                    < (plan["die"]["h"] if side == "S" else plan["die"]["w"])
                    - plan["gcell_um"]
                )
            )
            if not outside:
                continue
            length = (hi - lo) * front_free(plan, rects, me, side, soft)
            if length > 0:
                q = {
                    "N": [lo, fixed - 1, hi - lo, 1],
                    "S": [lo, fixed, hi - lo, 1],
                    "W": [fixed - 1, lo, 1, hi - lo],
                    "E": [fixed, lo, 1, hi - lo],
                }[side]
                free[side] = (length, q)
        tot = sum(v[0] for v in free.values())
        return (
            [(v[0] / tot, v[1]) for s, v in sorted(free.items())] if tot else [(1.0, r)]
        )
    reach = plan["channel_um"] + plan["gcell_um"]
    shares = {}
    for q in regions(rects, soft):
        if gap_between(r, q) > reach:
            continue
        s = side_toward(r, q)
        _, lo, hi = edge_span(r, s)
        a, b = (q[0], q[0] + q[2]) if s in "NS" else (q[1], q[1] + q[3])
        ov = min(b, hi) - max(a, lo)
        if ov > 0:
            shares.setdefault(s, [0.0, q])[0] += ov
    if not shares:
        return [(1.0, nearest_region(rects, soft, r))]
    tot = sum(v[0] for v in shares.values())
    return [(v[0] / tot, v[1]) for s, v in sorted(shares.items())]


def end_bits(plan):
    """A net's pins at each end, when the net names them ([a, b, bits,
    a_bits, b_bits]): {(me, other): pins}."""
    out = {}
    for net in plan["nets"]:
        if len(net) == 5 and net[0] != net[1]:
            a, b, _, na, nb = net
            out[(a, b)] = out.get((a, b), 0) + na
            out[(b, a)] = out.get((b, a), 0) + nb
    return out


def bundles(plan, rects):
    """(macro, partner, bits, partner rect) for every hard end of every net,
    the bits that end's own when the net says."""
    out = []
    ends = end_bits(plan)
    for (a, b), pair in sorted(nets_by_pair(plan).items()):
        for me, other in ((a, b), (b, a)):
            if is_soft(plan, me):
                continue
            n = ends.get((me, other), pair)
            if is_soft(plan, other):
                parts = soft_shares(plan, rects, me, other)
                left = n
                for i, (f, q) in enumerate(parts):
                    k = left if i == len(parts) - 1 else round(n * f)
                    left -= k
                    if k:
                        out.append((me, other, k, q))
            else:
                out.append((me, other, n, rects[other]))
    return out


def walls(plan, rects, m, side, partner, reach=None):
    """Merged spans of an edge with another hard macro closer than `reach` in front."""
    fixed, lo, hi = edge_span(rects[m], side)
    covered = []
    for n, r in rects.items():
        if n in (m, partner) or is_soft(plan, n):
            continue
        fs = edge_span(r, OPP[side])[0]
        d = fs - fixed if side in "SE" else fixed - fs
        if 0 <= d < (plan["gcell_um"] if reach is None else reach):
            a, b = (r[0], r[0] + r[2]) if side in "NS" else (r[1], r[1] + r[3])
            if min(b, hi) > max(a, lo):
                covered.append([max(a, lo), min(b, hi)])
    merged = []
    for a, b in sorted(covered):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def front_free(plan, rects, m, side, partner):
    """Share of an edge with free space in front of it."""
    _, lo, hi = edge_span(rects[m], side)
    tot = sum(b - a for a, b in walls(plan, rects, m, side, partner))
    return 1 - tot / (hi - lo) if hi > lo else 0


def anchor(plan, rects, m, side, partner, q):
    """Where along the edge a bundle wants to start: in front of its partner when
    the partner faces the edge, else at the free space nearest the partner."""
    fixed, lo, hi = edge_span(rects[m], side)
    axis = 0 if side in "NS" else 1
    if (
        not is_soft(plan, partner)
        and side_toward(q, rects[m]) == OPP[side]
        and gap_between(rects[m], q) <= plan["channel_um"] + 1e-6
    ):
        return min(max(q[axis], lo), hi)
    want = min(max(center(q)[axis], lo), hi)
    free, cur = [], lo
    for a, b in walls(plan, rects, m, side, partner, 2 * plan["channel_um"] + 1e-6):
        if a > cur:
            free.append((cur, a))
        cur = max(cur, b)
    if cur < hi:
        free.append((cur, hi))
    if not free:
        return want
    a, b = min(
        free,
        key=lambda f: (
            0 if f[0] <= want <= f[1] else min(abs(f[0] - want), abs(f[1] - want)),
            f,
        ),
    )
    return min(max(want, a), b)


def choose_side(plan, rects, m, q, partner):
    """The edge facing the partner, unless another macro walls it off; a side
    the plan forces for the pair wins, a side it forbids for the macro loses."""
    forced = plan.get("forced_sides", {}).get(m, {}).get(partner)
    if forced:
        return forced
    r = rects[m]
    s = side_toward(r, q)
    banned = plan.get("forbidden_sides", {}).get(m, ())
    if s in banned:
        (acx, acy), (bcx, bcy) = center(r), center(q)
        alts = [("S" if bcy > acy else "N"), ("E" if bcx > acx else "W")]
        alts += [OPP[a] for a in alts] + [OPP[s]]
        alts = [a for a in alts if a not in banned]
        if alts:
            return max(
                alts,
                key=lambda a: (front_free(plan, rects, m, a, partner), -alts.index(a)),
            )
    if front_free(plan, rects, m, s, partner) >= 0.5:
        return s
    (acx, acy), (bcx, bcy) = center(r), center(q)
    alt = ("S" if bcy > acy else "N") if s in "EW" else ("E" if bcx > acx else "W")
    return (
        alt
        if front_free(plan, rects, m, alt, partner)
        > front_free(plan, rects, m, s, partner)
        else s
    )


def assign(plan, rects):
    """Bundles per (macro, side), in pin order, each with its segment."""
    tech = plan["tech"]
    edges = {}
    for me, other, n, q in bundles(plan, rects):
        s = choose_side(plan, rects, me, q, other)
        edges.setdefault((me, s), []).append([other, n, q])
    out = {}
    for (m, s), bl in sorted(edges.items()):
        _, lo, hi = edge_span(rects[m], s)
        axis = 0 if s in "NS" else 1

        for o in bl:
            o.append(anchor(plan, rects, m, s, o[0], o[2]))
        bl.sort(key=lambda o: (o[3], o[0]))
        ppu1 = pins_per_um(tech, s)
        need = sum(o[1] for o in bl)
        length = hi - lo
        ppu = ppu1 * max(1, math.ceil(need / (length * ppu1))) if length else ppu1
        segs = []
        cur = lo
        for o, n, q, at in bl:
            start = max(cur, at)
            segs.append([o, n, start, start + n / ppu])
            cur = segs[-1][3]
        over = cur - hi
        for i in range(len(segs) - 1, -1, -1):
            if over <= 0:
                break
            room = segs[i][2] - (segs[i - 1][3] if i else lo)
            shift = min(over, room)
            for t in segs[i:]:
                t[2] -= shift
                t[3] -= shift
            over -= shift
        out[(m, s)] = {
            "bundles": segs,
            "need": need,
            "len": length,
            "cap1": length * ppu1,
            "util1": need / (length * ppu1) if length else math.inf,
        }
    return out


def pin_point(rects, edges, m, side, partner, frac=0.5):
    """The point a fraction along the partner's segment on the edge."""
    fixed, _, _ = edge_span(rects[m], side)
    for o, n, a, b in edges[(m, side)]["bundles"]:
        if o == partner:
            t = a + frac * (b - a)
            return (t, fixed) if side in "NS" else (fixed, t)
    raise KeyError((m, side, partner))


class Grid:
    """Gcells over the die; blocked where a hard macro or a memory sits."""

    def __init__(self, plan, rects, die):
        self.g = plan["gcell_um"]
        self.nx = int(math.ceil(die[0] / self.g))
        self.ny = int(math.ceil(die[1] / self.g))
        tech = plan["tech"]
        usable = tech["track_density_per_um"] * tech["usable"]
        self.cap = usable * self.g
        # per direction when the tech gives it: horizontal wires on the
        # horizontal layers, vertical on the vertical
        self.cap_h = (
            tech.get("track_density_h_per_um", tech["track_density_per_um"])
            * tech["usable"]
            * self.g
        )
        self.cap_v = (
            tech.get("track_density_v_per_um", tech["track_density_per_um"])
            * tech["usable"]
            * self.g
        )
        self.blocked = set()
        blocks = [rects[n] for n in rects if not is_soft(plan, n)] + [
            list(r) for r in plan.get("memories", [])
        ]
        for r in blocks:
            for i in range(int(r[0] // self.g), int(math.ceil((r[0] + r[2]) / self.g))):
                for j in range(
                    int(r[1] // self.g), int(math.ceil((r[1] + r[3]) / self.g))
                ):
                    cx, cy = (i + 0.5) * self.g, (j + 0.5) * self.g
                    if r[0] < cx < r[0] + r[2] and r[1] < cy < r[1] + r[3]:
                        self.blocked.add((i, j))
        self.h = {}
        self.v = {}

    def cell(self, p, side):
        """The free gcell just outside an edge point."""
        dx, dy = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[side]
        i = min(max(int((p[0] + dx * self.g / 2) // self.g), 0), self.nx - 1)
        j = min(max(int((p[1] + dy * self.g / 2) // self.g), 0), self.ny - 1)
        return (i, j)

    def route(self, a, b, bits):
        """Shortest path through free gcells under a congestion cost; None if blocked."""
        if a in self.blocked or b in self.blocked:
            return None
        dist = {a: 0.0}
        prev = {}
        pq = [(0.0, a)]
        while pq:
            d, c = heapq.heappop(pq)
            if c == b:
                break
            if d > dist[c]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if (
                    not (0 <= n[0] < self.nx and 0 <= n[1] < self.ny)
                    or n in self.blocked
                ):
                    continue
                use = (self.h if dx else self.v).get(n, 0)
                cap = self.cap_h if dx else self.cap_v
                cost = (
                    1.0
                    + 50.0 * max(0.0, (use + bits) / cap - 1.0)
                    + 2.0 * (use + bits) / cap
                )
                nd = d + cost
                if nd < dist.get(n, math.inf):
                    dist[n] = nd
                    prev[n] = (c, dx != 0)
                    heapq.heappush(pq, (nd, n))
        if b not in dist:
            return None
        path = []
        c = b
        while c != a:
            p, horiz = prev[c]
            (self.h if horiz else self.v)[c] = (self.h if horiz else self.v).get(
                c, 0
            ) + bits
            path.append(c)
            c = p
        return path

    def overflow(self):
        over = []
        for name, layer, cap in (("h", self.h, self.cap_h), ("v", self.v, self.cap_v)):
            for c, d in layer.items():
                if d > cap:
                    over.append([name, c[0], c[1], round(d), round(cap)])
        return sorted(over, key=lambda o: -o[3])


def route_all(plan, rects, edges, die):
    grid = Grid(plan, rects, die)
    res = []
    done = set()
    for me, other, n, q in sorted(
        bundles(plan, rects), key=lambda t: (-t[2], t[0], t[1])
    ):
        if is_soft(plan, other):
            s = side_toward(rects[me], q)
            res.append(
                {"a": me, "b": other, "bits": n, "kind": "to parent logic", "len_um": 0}
            )
            continue
        key = tuple(sorted((me, other)))
        if key in done:
            continue
        done.add(key)
        sa = choose_side(plan, rects, me, rects[other], other)
        sb = choose_side(plan, rects, other, rects[me], me)
        pa = pin_point(rects, edges, me, sa, other)
        pb = pin_point(rects, edges, other, sb, me)
        facing = (
            OPP[sa] == sb
            and gap_between(rects[me], rects[other]) <= plan["channel_um"] + 1e-6
        )
        if facing:
            res.append(
                {
                    "a": me,
                    "b": other,
                    "bits": n,
                    "kind": "facing",
                    "len_um": round(
                        gap_between(rects[me], rects[other])
                        + abs((pa[0] - pb[0]) if sa in "NS" else (pa[1] - pb[1]))
                    ),
                }
            )
            continue
        chunk = plan.get("route_chunk_bits", 128)
        nch = max(1, math.ceil(n / chunk))
        paths = []
        for k in range(nch):
            f = (k + 0.5) / nch
            qa = pin_point(rects, edges, me, sa, other, f)
            qb = pin_point(rects, edges, other, sb, me, f)
            paths.append(
                grid.route(
                    grid.cell(qa, sa), grid.cell(qb, sb), min(chunk, n - k * chunk)
                )
            )
        ok = all(p is not None for p in paths)
        res.append(
            {
                "a": me,
                "b": other,
                "bits": n,
                "kind": "channel" if ok else "OVER A MACRO",
                "len_um": round(max(len(p) for p in paths) * grid.g) if ok else None,
            }
        )
    return res, grid


def wirelength(plan, rects, die):
    """Bits times centre-to-centre Manhattan distance; a whitespace partition sits
    at the die centre."""
    c = {}
    for n in plan["macros"]:
        c[n] = (
            center(rects[n])
            if n in rects and not whitespace(plan, n)
            else (die[0] / 2, die[1] / 2)
        )
    return sum(
        w * (abs(c[a][0] - c[b][0]) + abs(c[a][1] - c[b][1]))
        for (a, b), w in nets_by_pair(plan).items()
    )


def quadratic(plan, shapes, die, anchors, alpha, iters=300):
    """Minimise bits-weighted squared distance between centres, plus alpha times the
    squared distance to each macro's anchor; a whitespace partition is fixed at the
    die centre. Gauss-Seidel, from the die centre."""
    names = sorted(shapes)
    bits = nets_by_pair(plan)
    scale = max(bits.values()) if bits else 1
    mid = (die[0] / 2, die[1] / 2)
    pos = {n: list(anchors[n]) if anchors else [mid[0], mid[1]] for n in names}
    adj = {n: [] for n in names}
    for (a, b), w in bits.items():
        for me, o in ((a, b), (b, a)):
            if me in adj:
                adj[me].append((o, w / scale))
    fixed = {n: center(r) for n, r in plan.get("fixed", {}).items() if n in pos}
    for n, c in fixed.items():
        pos[n] = list(c)
    tol = 1e-4 * max(die)
    for _ in range(iters):
        moved = 0.0
        for n in names:
            if n in fixed:
                continue
            sx = sy = sw = 0.0
            for o, w in adj[n]:
                p = pos[o] if o in pos else mid
                sx += w * p[0]
                sy += w * p[1]
                sw += w
            if anchors:
                sx += alpha * anchors[n][0]
                sy += alpha * anchors[n][1]
                sw += alpha
            if sw:
                new = [sx / sw, sy / sw]
                moved = max(moved, abs(new[0] - pos[n][0]) + abs(new[1] - pos[n][1]))
                pos[n] = new
        # Gauss-Seidel has converged: another sweep moves nothing
        if moved < tol:
            break
    return pos


def halos(plan, shapes):
    """Per macro half the channel its own wires need: its bits to other hard macros
    spread over four edges, at the usable track density, at least half a channel."""
    usable = plan["tech"]["track_density_per_um"] * plan["tech"]["usable"]
    out = {n: 0.0 for n in shapes}
    for (a, b), w in nets_by_pair(plan).items():
        if a in out and b in out and not is_soft(plan, a) and not is_soft(plan, b):
            out[a] += w
            out[b] += w
    k = plan.get("halo_scale", 1.0)
    return {
        n: max(
            plan["channel_um"] / 2,
            min(k * v / 4 / usable / 2, plan.get("halo_max_um", 400)),
        )
        for n, v in out.items()
    }


def legalise(plan, shapes, desired, die, order="area"):
    """Largest macro first (order "area"), or the one with the most bits to the
    other macros first (order "bits"), each at the free place nearest its
    desired centre, its halo plus its neighbour's apart from every placed macro
    and a channel from the die edge; None if one does not fit."""
    edge_gap = plan["channel_um"]
    halo = halos(plan, shapes)
    placed = {n: list(r) for n, r in plan.get("fixed", {}).items() if n in shapes}
    weight = {n: 0 for n in shapes}
    for (a, b), w in nets_by_pair(plan).items():
        if a in weight and b in weight:
            weight[a] += w
            weight[b] += w
    if order == "bits":
        key = lambda n: (-weight[n], -shapes[n][0] * shapes[n][1], n)  # noqa: E731
    else:
        key = lambda n: (-shapes[n][0] * shapes[n][1], n)  # noqa: E731
    for n in sorted(shapes, key=key):
        if n in placed:
            continue
        w, h = shapes[n]
        gap = edge_gap
        dx, dy = desired[n][0] - w / 2, desired[n][1] - h / 2
        xs = {min(max(dx, gap), die[0] - gap - w), gap, die[0] - gap - w}
        ys = {min(max(dy, gap), die[1] - gap - h), gap, die[1] - gap - h}
        for o, r in placed.items():
            g = halo[n] + halo[o]
            xs |= {r[0] + r[2] + g, r[0] - w - g, r[0], r[0] + r[2] - w}
            ys |= {r[1] + r[3] + g, r[1] - h - g, r[1], r[1] + r[3] - h}
        best = None
        for x in sorted(xs):
            if x < gap - 1e-6 or x + w > die[0] - gap + 1e-6:
                continue
            for y in sorted(ys):
                if y < gap - 1e-6 or y + h > die[1] - gap + 1e-6:
                    continue
                cand = [x, y, w, h]
                if any(
                    min(overlap_pen(cand, r, halo[n] + halo[o])) > 1e-6
                    for o, r in placed.items()
                ):
                    continue
                cost = abs(x - dx) + abs(y - dy)
                if best is None or cost < best[0]:
                    best = (cost, cand)
        if best is None:
            return None
        placed[n] = best[1]
    return placed


def overlap_pen(r, q, gap):
    ox = min(r[0] + r[2] + gap, q[0] + q[2] + gap) - max(r[0], q[0])
    oy = min(r[1] + r[3] + gap, q[1] + q[3] + gap) - max(r[1], q[1])
    return ox, oy


def place(plan, shapes, die, rounds=24):
    """Global placement: quadratic wirelength, then rounds of legalisation whose
    result anchors the next quadratic solve with a growing weight (SimPL-style),
    largest macro first and then best connected first; the legal placement with
    the least wirelength wins."""
    hard = {n: s for n, s in shapes.items() if not whitespace(plan, n)}
    best = None
    for order in ("area", "bits"):
        anchors = None
        for k in range(rounds):
            alpha = 0.0 if anchors is None else 0.02 * (1.6**k)
            pos = quadratic(plan, hard, die, anchors, alpha)
            legal = legalise(plan, hard, pos, die, order)
            if legal is None:
                break
            wl = wirelength(plan, legal, die)
            if best is None or wl < best[0] - 1e-6:
                best = (wl, {n: list(r) for n, r in legal.items()})
            anchors = {n: center(r) for n, r in legal.items()}
    return best[1] if best else None


def shapes_for(plan, aspects):
    out = {}
    for n, m in plan["macros"].items():
        if "fixed_shape" in m:
            out[n] = tuple(m["fixed_shape"])
        else:
            a = footprint(m, plan)
            r = aspects.get(n, 1.0)
            out[n] = (math.sqrt(a / r), math.sqrt(a * r))
    return out


def worst(edges, m=None):
    return max([e["util1"] for (n, s), e in edges.items() if m in (None, n)] or [0])


def die_for(plan):
    return (plan["die"]["w"], plan["die"]["h"])


def need_area(plan, shapes):
    hard = sum(w * h for n, (w, h) in shapes.items() if not is_soft(plan, n))
    soft = sum(footprint(m, plan) for m in plan["macros"].values() if m.get("soft"))
    return hard, soft


def quick(plan, aspects, die):
    """Place and assign edges, no routing: (the fullest edges' utilisations,
    fullest first, wirelength) or None."""
    p = dict(plan, die={"w": die[0], "h": die[1]})
    rects = place(p, shapes_for(p, aspects), die)
    if rects is None:
        return None
    edges = assign(p, rects)
    full = sorted(
        [
            round(e["util1"], 4)
            for (m, s), e in edges.items()
            if not p["macros"][m].get("memory")
        ]
        or [0],
        reverse=True,
    )[:8]
    return (tuple(full), wirelength(p, rects, die)), rects


def tune_aspects(plan, aspects, die, passes=2):
    """Coordinate descent: per macro the aspect ratio that, after a full placement,
    leaves the fullest edge of the whole floorplan emptiest (wirelength breaks ties)."""
    out = dict(aspects)
    cur = quick(plan, out, die)
    if cur is None:
        return out, None
    for _ in range(passes):
        for n in sorted(plan["macros"]):
            m = plan["macros"][n]
            if "fixed_shape" in m or m.get("soft"):
                continue
            for r in plan.get("macro_aspects", {}).get(n, plan.get("aspects", ASPECTS)):
                if r == out.get(n, 1.0):
                    continue
                q = quick(plan, {**out, n: r}, die)
                if q is not None and q[0] < cur[0]:
                    out[n], cur = r, q
    return out, cur


def score(result, limits):
    over = sum(1 for x in result["routes"] if x["kind"] == "OVER A MACRO")
    edge = max(
        [e["util_one_layer"] for e in result["edges"] if not e.get("memory")] or [0]
    )
    ok = (
        over == 0
        and edge <= limits["edge"]
        and result["max_gcell_util"] <= limits["gcell"]
    )
    return (
        0 if ok else 1,
        over,
        result["die"][0] * result["die"][1] if ok else edge,
        result["max_gcell_util"],
    )


def solve(plan):
    """Search die sizes and aspect ratios with every macro square; tune the macros'
    aspect ratios on the best few dies; route those; the smallest die meeting the
    limits wins, else the least bad. Whitespace is at least the soft partitions'
    footprint."""
    limits = plan.get("limits", {"edge": 1.0, "gcell": 1.15})
    hard, soft = need_area(plan, shapes_for(plan, {}))
    dies = []
    slacks = list(plan.get("die_slack", (1.15, 1.25, 1.35, 1.45, 1.55)))
    while slacks:
        slack = slacks.pop(0)
        for ar in plan.get("die_aspects", (1.0, 1.25, 1.5, 1.75)):
            area = (hard + soft) * slack
            die = (math.sqrt(area / ar), math.sqrt(area * ar))
            q = quick(plan, {}, die)
            if q is not None:
                dies.append((q[0], die))
        if not slacks and not dies and slack < 64:
            slacks.append(slack * 1.25)
    dies.sort()
    best = None
    for _, die in dies[: plan.get("tune_dies", 3)]:
        aspects, q = tune_aspects(plan, {}, die)
        if q is None:
            continue
        p = dict(plan, die={"w": die[0], "h": die[1]})
        res = evaluate(p, q[1], die, aspects)
        key = score(res, limits)
        if best is None or key < best[0]:
            best = (key, res)
    return best[1]


def evaluate(plan, rects, die, aspects=None):
    edges = assign(plan, rects)
    routes, grid = route_all(plan, rects, edges, die)
    over = grid.overflow()
    return {
        "die": list(die),
        "rects": {n: r for n, r in sorted(rects.items())},
        "aspects": aspects or {},
        "edges": [
            {
                "macro": m,
                "side": s,
                "len_um": round(e["len"], 1),
                "bits": e["need"],
                "memory": plan["macros"][m].get("memory", False),
                "cap_one_layer": round(e["cap1"]),
                "util_one_layer": round(e["util1"], 3),
                "layers": 1 if e["util1"] <= 1 else (2 if e["util1"] <= 2 else 3),
                "order": [
                    [o, n, round(a, 1), round(b, 1)] for o, n, a, b in e["bundles"]
                ],
            }
            for (m, s), e in sorted(edges.items())
        ],
        "routes": routes,
        "gcell_capacity": round(grid.cap),
        "overflow": over[:20],
        "overflow_gcells": len(over),
        "max_gcell_util": round(
            max(
                [d / grid.cap for d in list(grid.h.values()) + list(grid.v.values())]
                or [0]
            ),
            3,
        ),
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("plan", help="input JSON, described above")
    ap.add_argument("--out", required=True, help="result JSON")
    ap.add_argument(
        "--evaluate",
        action="store_true",
        help="keep the plan's own placement and only assign edges and route",
    )
    args = ap.parse_args(argv)
    with open(args.plan) as f:
        plan = json.load(f)
    if args.evaluate:
        result = evaluate(
            plan, {n: r for n, r in plan["placement"].items()}, die_for(plan)
        )
    else:
        result = solve(plan)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    for e in result["edges"]:
        flag = (
            ""
            if e["layers"] == 1
            else ("  2 layers" if e["layers"] == 2 else "  DOES NOT FIT")
        )
        print(
            f'{e["macro"]:8s} {e["side"]} {e["bits"]:7d} bits / {e["cap_one_layer"]:6d} '
            f'= {100 * e["util_one_layer"]:5.0f}%{flag}'
        )
    for r in result["routes"]:
        if r["kind"] not in ("to parent logic",):
            print(f'{r["a"]}-{r["b"]} {r["bits"]} bits: {r["kind"]} {r["len_um"]} um')
    print(
        f'gcell capacity {result["gcell_capacity"]} tracks/direction; '
        f'{result["overflow_gcells"]} gcells over; max {100 * result["max_gcell_util"]:.0f}%'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
