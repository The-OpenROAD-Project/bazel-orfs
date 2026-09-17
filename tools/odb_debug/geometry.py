#!/usr/bin/env python3
"""Placement forensics on an odb-debug geometry dump.

`od_dump <dir> 1` (daemon.tcl) writes four text files: summary.txt
(dbu, die, core, counts), rows.txt (one row fragment per line: x0 y0 x1
y1 sites), macros.txt (name master x0 y0 x1 y1 orient status) and
insts.txt (name master x y w h status, every non-macro instance). This
reads them and answers the questions a stalled or failed legaliser
raises:

  free      how much standard-cell site area the floorplan has, how it is
            distributed (a coarse grid), and how much of it sits in row
            fragments too narrow to hold anything -- the slivers between
            abutting macros.
  inside    which instances global placement left inside a macro footprint,
            per macro: the legaliser has to move every one of them out.
  failed    given the instance names a legaliser reported (DPL-0035 lines),
            where they are: inside a macro, in a sliver, stacked on one
            coordinate, and how crowded their neighbourhood is.

Standard library only, so it runs on the host python3 next to the daemon;
with matplotlib installed, --png draws the macro outlines over the free-site
grid and the instances in question.

    python3 tools/odb_debug/geometry.py free   <dump-dir>
    python3 tools/odb_debug/geometry.py inside <dump-dir>
    python3 tools/odb_debug/geometry.py failed <dump-dir> <names.txt>
    python3 tools/odb_debug/geometry.py free   <dump-dir> --png map.png
"""

import collections
import os
import sys


def read_summary(d):
    out = {}
    with open(os.path.join(d, "summary.txt")) as f:
        for line in f:
            k, _, v = line.strip().partition(" ")
            out[k] = v
    dbu = float(out["dbu"])
    out["die_um"] = [int(v) / dbu for v in out["die"].split()]
    out["core_um"] = [int(v) / dbu for v in out["core"].split()]
    out["dbu"] = dbu
    return out


def read_rows(d, dbu):
    rows = []
    with open(os.path.join(d, "rows.txt")) as f:
        for line in f:
            p = line.split()
            if len(p) >= 4:
                rows.append(tuple(int(v) / dbu for v in p[:4]))
    return rows


def read_macros(d, dbu):
    macros = []
    with open(os.path.join(d, "macros.txt")) as f:
        for line in f:
            p = line.split()
            if len(p) >= 6:
                macros.append(
                    {
                        "name": p[0],
                        "master": p[1],
                        "box": tuple(int(v) / dbu for v in p[2:6]),
                        "status": p[7] if len(p) > 7 else "",
                    }
                )
    return macros


def read_insts(d, dbu):
    """Non-macro instances as (name, master, cx, cy, w, h, status)."""
    insts = []
    with open(os.path.join(d, "insts.txt")) as f:
        for line in f:
            p = line.split()
            if len(p) < 7:
                continue
            x, y, w, h = (int(v) / dbu for v in p[2:6])
            insts.append((p[0], p[1], x + w / 2, y + h / 2, w, h, p[6]))
    return insts


def is_logic(master):
    return not master.startswith(("TAPCELL", "FILL", "DECAP", "TIE"))


def containing_macro(macros, cx, cy):
    for i, m in enumerate(macros):
        x0, y0, x1, y1 = m["box"]
        if x0 < cx < x1 and y0 < cy < y1:
            return i
    return -1


def fragment_width_at(rows, cx, cy):
    """Width of the row fragment under a point, -1 when none."""
    best = -1.0
    for x0, y0, x1, y1 in rows:
        if y0 <= cy < y1 and x0 <= cx < x1:
            w = x1 - x0
            if best < 0 or w < best:
                best = w
    return best


def free_grid(summary, rows, bin_um):
    """Free-site area fraction per bin_um x bin_um cell of the core."""
    cx0, cy0, cx1, cy1 = summary["core_um"]
    nx = int((cx1 - cx0) // bin_um) + 1
    ny = int((cy1 - cy0) // bin_um) + 1
    grid = [[0.0] * nx for _ in range(ny)]
    for x0, y0, x1, y1 in rows:
        iy = min(max(int((y0 - cy0) // bin_um), 0), ny - 1)
        ix0 = max(int((x0 - cx0) // bin_um), 0)
        ix1 = min(int((x1 - cx0) // bin_um), nx - 1)
        for ix in range(ix0, ix1 + 1):
            bx0 = cx0 + ix * bin_um
            bx1 = bx0 + bin_um
            grid[iy][ix] += max(0.0, min(x1, bx1) - max(x0, bx0)) * (y1 - y0)
    return [[a / (bin_um * bin_um) for a in row] for row in grid], nx, ny


def cmd_free(d, png=None, bin_um=50.0):
    s = read_summary(d)
    rows = read_rows(d, s["dbu"])
    macros = read_macros(d, s["dbu"])
    cx0, cy0, cx1, cy1 = s["core_um"]
    core_area = (cx1 - cx0) * (cy1 - cy0)
    site_area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rows)
    widths = [x1 - x0 for x0, _, x1, _ in rows]
    narrow = [(x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rows if x1 - x0 < 20]
    macro_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in (m["box"] for m in macros))
    print(
        "die %.0f x %.0f um, core %.3f mm^2"
        % (
            s["die_um"][2] - s["die_um"][0],
            s["die_um"][3] - s["die_um"][1],
            core_area / 1e6,
        )
    )
    print(
        "%d macros, %.3f mm^2 (%.0f%% of core)"
        % (len(macros), macro_area / 1e6, 100 * macro_area / core_area)
    )
    print(
        "standard-cell site area %.3f mm^2 (%.0f%% of core) in %d row fragments"
        % (site_area / 1e6, 100 * site_area / core_area, len(rows))
    )
    print(
        "fragment widths: <5 um %d, 5-20 um %d, 20-100 um %d, >=100 um %d"
        % (
            sum(1 for w in widths if w < 5),
            sum(1 for w in widths if 5 <= w < 20),
            sum(1 for w in widths if 20 <= w < 100),
            sum(1 for w in widths if w >= 100),
        )
    )
    print(
        "site area in fragments under 20 um wide: %.3f mm^2 (slivers between abutting macros)"
        % (sum(narrow) / 1e6)
    )
    grid, nx, ny = free_grid(s, rows, bin_um)
    flat = [v for row in grid for v in row]
    print(
        "free-site fraction per %.0f um bin: mean %.2f; bins under 10%% free: %d of %d; over 90%%: %d"
        % (
            bin_um,
            sum(flat) / len(flat),
            sum(1 for v in flat if v < 0.1),
            len(flat),
            sum(1 for v in flat if v > 0.9),
        )
    )
    biggest = sorted(
        macros, key=lambda m: -(m["box"][2] - m["box"][0]) * (m["box"][3] - m["box"][1])
    )[:8]
    for m in biggest:
        x0, y0, x1, y1 = m["box"]
        print(
            "  %-50s %6.0f x %6.0f um at (%6.0f, %6.0f) %s"
            % (m["name"][-50:], x1 - x0, y1 - y0, x0, y0, m["status"])
        )
    if png:
        draw(
            png,
            s,
            grid,
            nx,
            ny,
            bin_um,
            macros,
            points=None,
            title="free standard-cell sites (white) and macros (red)",
        )


def cmd_inside(d, png=None):
    s = read_summary(d)
    macros = read_macros(d, s["dbu"])
    insts = read_insts(d, s["dbu"])
    logic = [i for i in insts if is_logic(i[1])]
    inside = collections.Counter()
    pts = []
    for name, master, cx, cy, w, h, st in logic:
        k = containing_macro(macros, cx, cy)
        if k >= 0:
            inside[k] += 1
            pts.append((cx, cy))
    n = sum(inside.values())
    print(
        "%d non-macro instances, %d logic; %d logic cells (%.2f%%) have their centre inside a macro footprint"
        % (len(insts), len(logic), n, 100.0 * n / max(1, len(logic)))
    )
    for k, c in inside.most_common(10):
        m = macros[k]
        print(
            "  %6d in %-45s (%.0f x %.0f um)"
            % (c, m["name"][-45:], m["box"][2] - m["box"][0], m["box"][3] - m["box"][1])
        )
    if png:
        rows = read_rows(d, s["dbu"])
        grid, nx, ny = free_grid(s, rows, 50.0)
        draw(
            png,
            s,
            grid,
            nx,
            ny,
            50.0,
            macros,
            points=pts,
            title="%d logic cells inside macro footprints" % n,
        )


def cmd_failed(d, names_file, png=None):
    s = read_summary(d)
    rows = read_rows(d, s["dbu"])
    macros = read_macros(d, s["dbu"])
    insts = read_insts(d, s["dbu"])
    with open(names_file) as f:
        wanted = set(l.strip() for l in f if l.strip())
    by_name = dict((i[0], i) for i in insts)
    found = [by_name[n] for n in wanted if n in by_name]
    print("%d names, %d found in the dump" % (len(wanted), len(found)))
    if not found:
        return
    masters = collections.Counter(i[1] for i in found)
    print("masters:", ", ".join("%s x%d" % kv for kv in masters.most_common(5)))
    inside = sum(1 for i in found if containing_macro(macros, i[2], i[3]) >= 0)
    widths = [fragment_width_at(rows, i[2], i[3]) for i in found]
    print(
        "inside a macro footprint: %d; no row under the centre: %d; row fragment under 10 um: %d, 10-30 um: %d, over 30 um: %d"
        % (
            inside,
            sum(1 for w in widths if w < 0),
            sum(1 for w in widths if 0 <= w < 10),
            sum(1 for w in widths if 10 <= w < 30),
            sum(1 for w in widths if w >= 30),
        )
    )
    coords = collections.Counter((round(i[2], 3), round(i[3], 3)) for i in found)
    stacks = sorted(coords.values())
    print(
        "distinct coordinates: %d; largest stacks of failed cells on one coordinate: %s"
        % (len(coords), stacks[-5:])
    )
    # Crowding: all instances within a 10 x 10 um box around each failed cell.
    xs = sorted((i[2], i[3]) for i in insts)
    import bisect

    crowd = []
    step = max(1, len(found) // 200)
    for i in found[::step]:
        lo = bisect.bisect_left(xs, (i[2] - 5, -1e9))
        hi = bisect.bisect_right(xs, (i[2] + 5, 1e9))
        crowd.append(sum(1 for x, y in xs[lo:hi] if abs(y - i[3]) < 5))
    crowd.sort()
    print(
        "instances within a 10 x 10 um box around a failed cell (sample of %d): median %d, 90%% %d, max %d"
        % (
            len(crowd),
            crowd[len(crowd) // 2],
            crowd[int(len(crowd) * 0.9) - 1],
            crowd[-1],
        )
    )
    clusters = collections.Counter(
        (int(i[2] // 100) * 100, int(i[3] // 100) * 100) for i in found
    )
    print(
        "failed cells per 100 um square, top:",
        ", ".join("(%d,%d) %d" % (k[0], k[1], v) for k, v in clusters.most_common(6)),
    )
    if png:
        grid, nx, ny = free_grid(s, rows, 50.0)
        draw(
            png,
            s,
            grid,
            nx,
            ny,
            50.0,
            macros,
            points=[(i[2], i[3]) for i in found],
            title="%d instances the legaliser could not place" % len(found),
        )


def draw(png, s, grid, nx, ny, bin_um, macros, points, title):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ImportError:
        print("matplotlib not installed; no picture")
        return
    cx0, cy0 = s["core_um"][0], s["core_um"][1]
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(
        grid,
        origin="lower",
        extent=[cx0, cx0 + nx * bin_um, cy0, cy0 + ny * bin_um],
        cmap="Greys_r",
        vmin=0,
        vmax=1,
    )
    for m in macros:
        x0, y0, x1, y1 = m["box"]
        ax.add_patch(
            Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="tab:red", lw=0.7)
        )
        if x1 - x0 > 0.05 * (s["die_um"][2] - s["die_um"][0]):
            ax.text(
                (x0 + x1) / 2,
                y1,
                m["name"].split("/")[-1][:16],
                ha="center",
                va="top",
                fontsize=6,
                color="tab:red",
            )
    if points:
        ax.scatter([p[0] for p in points], [p[1] for p in points], s=2, c="tab:orange")
    ax.set_title(title)
    ax.set_xlabel("um")
    ax.set_ylabel("um")
    fig.tight_layout()
    fig.savefig(png, dpi=110)
    print("wrote", png)


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    png = None
    if "--png" in argv:
        i = argv.index("--png")
        png = argv[i + 1]
        argv = argv[:i] + argv[i + 2 :]
    cmd, d = argv[1], argv[2]
    if cmd == "free":
        cmd_free(d, png)
    elif cmd == "inside":
        cmd_inside(d, png)
    elif cmd == "failed":
        cmd_failed(d, argv[3], png)
    else:
        sys.stderr.write(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
