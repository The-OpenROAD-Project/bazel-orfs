"""The OpenROAD reference for the kit, from each part's global-route
snapshot (snapshot.tcl) and KPI (kpi_run.tcl), written into kit/snapshot/
of the source tree: `bazelisk run :kit_snapshot` (kit.bzl,
xs_kit_snapshot). It is informational and costs a global route of the
whole tile to remake, so the kit's own build only reads what this wrote.

One floorplan, with and without macros. The parent places each hardened
block as a footprint, its abstract scaled from the outline the block was
built at, pins included. The kit's block is that footprint: its outline
and pins are the abstract's, and each memory macro inside it sits where
the block's own run put it, its centre scaled by the same factor, its size
kept. A macro keeps its size, so its place is not its corner times the
scale: along each axis the stretches no macro covers shrink, and the
stretches macros cover keep their length (squeeze()), so two macros that
abut stay abutting and two apart stay apart. The flat floorplan is the
parent's, each block dissolved: the same macros at the block's origin plus
those positions. Overlaps and macros outside the die are counted and
listed, and stop the run.

  snapshot.json             commit, KPI, per part statistics, periods, histograms, congestion
  floorplan/macros.csv      every macro of the tile, flat, with where it sits in its block
  floorplan/flat/XSTile.def the tile without hardened blocks: die, ports, every macro FIXED
  floorplan/hier/XSTile.def the parent: die, ports, the blocks and the parent's macros
  floorplan/hier/<B>.def    each block at its footprint: outline, pins, its macros
  images/<part>_*.jpg       the viewer's floorplan, modules and global-route congestion
  images/<part>_*.png       placement density, the modules labelled, the slack histogram
  images/tile_module_map.png every module of the tile, each block's in its footprint
"""

import argparse
import csv
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

ORIENT = {
    "R0": "N",
    "R90": "W",
    "R180": "S",
    "R270": "E",
    "MX": "FS",
    "MY": "FN",
    "MXR90": "FW",
    "MYR90": "FE",
}
IMAGES = ["floorplan", "modules", "congestion"]


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def boxf(r):
    return [float(r[k]) for k in ("x0", "y0", "x1", "y1")]


def parse_kpi(path):
    """kpi_run.tcl's KPI_OUT: each group's worst slack and path, the reg2reg
    endpoint histogram and the minimum period."""
    out = {"groups": {}}
    for line in open(path):
        m = re.match(
            r"(reg2reg|in2reg|reg2out|in2out)\s+(-?\d+) ps\s+(\S+) -> (\S+)", line
        )
        if m:
            out["groups"][m.group(1)] = {
                "slack_ps": int(m.group(2)),
                "from": m.group(3),
                "to": m.group(4),
            }
            continue
        m = re.match(r"reg2reg endpoints bin (\d+) ps from (-?\d+) ps: (.*)", line)
        if m:
            out["histogram"] = {
                "bin_ps": int(m.group(1)),
                "from_ps": int(m.group(2)),
                "counts": [int(c) for c in m.group(3).split()],
            }
            continue
        m = re.match(r"reg2reg min period (\d+) ps", line)
        if m:
            out["period_ps"] = int(m.group(1))
    if "period_ps" not in out:
        sys.exit("snapshot: no period in %s" % path)
    return out


def parse_congestion(path):
    """global_route's final congestion report (GRT-0096): per layer resource,
    demand, usage and overflow, and the total wire length (GRT-0018)."""
    if not os.path.exists(path):
        return None
    layers, wirelength = [], None
    for line in open(path):
        m = re.match(
            r"\s*(\S+)\s+(\d+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s*/\s*(\d+)\s*/\s*(\d+)",
            line,
        )
        if m:
            layers.append(
                {
                    "layer": m.group(1),
                    "resource": int(m.group(2)),
                    "demand": int(m.group(3)),
                    "usage_pct": float(m.group(4)),
                    "overflow_h": int(m.group(5)),
                    "overflow_v": int(m.group(6)),
                    "overflow": int(m.group(7)),
                }
            )
        m = re.search(r"GRT-0018\].*?([\d.]+) um", line)
        if m:
            wirelength = float(m.group(1))
    return {"layers": layers, "wirelength_um": wirelength}


def squeeze(intervals, built, footprint):
    """x -> x' on one axis, [0, built] onto [0, footprint]: slope 1 where a
    macro covers the axis, the rest scaled to make up the difference."""
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    covered = sum(hi - lo for lo, hi in merged)
    if covered > footprint:
        sys.exit(
            "snapshot: macros cover %.1f um of an axis the footprint has %.1f um of"
            % (covered, footprint)
        )
    k = (footprint - covered) / (built - covered)

    def f(x):
        y, at = 0.0, 0.0
        for lo, hi in merged:
            if x <= lo:
                return y + (x - at) * k
            y += (lo - at) * k
            if x <= hi:
                return y + (x - lo)
            y += hi - lo
            at = hi
        return y + (x - at) * k

    return f, k


def overlaps(macros):
    """Pairs of macros whose boxes overlap, by name."""
    found = []
    ms = sorted(macros, key=lambda m: m["box"][0])
    for i, a in enumerate(ms):
        for b in ms[i + 1 :]:
            if b["box"][0] >= a["box"][2]:
                break
            if b["box"][1] < a["box"][3] and a["box"][1] < b["box"][3]:
                found.append([a["name"], b["name"]])
    return found


def def_text(design, dbu, die, pins, comps):
    """A DEF with the floorplan's facts only: die, ports placed, macros fixed.
    pins: (name, direction, layer, box); comps: (name, master, box, orient)."""
    d = lambda v: int(round(v * dbu))
    out = [
        "VERSION 5.8 ;",
        'DIVIDERCHAR "/" ;',
        'BUSBITCHARS "[]" ;',
        "DESIGN %s ;" % design,
        "UNITS DISTANCE MICRONS %d ;" % dbu,
        "DIEAREA ( %d %d ) ( %d %d ) ;" % tuple(d(v) for v in die),
    ]
    by_name = {}
    for name, direction, layer, box in pins:
        by_name.setdefault(name, (direction, []))[1].append((layer, box))
    out.append("PINS %d ;" % len(by_name))
    for name, (direction, shapes) in by_name.items():
        out.append(
            "- %s + NET %s + DIRECTION %s + USE SIGNAL" % (name, name, direction)
        )
        for layer, (x0, y0, x1, y1) in shapes:
            out.append(
                "  + PORT + LAYER %s ( 0 0 ) ( %d %d ) + FIXED ( %d %d ) N"
                % (layer, d(x1) - d(x0), d(y1) - d(y0), d(x0), d(y0))
            )
        out[-1] += " ;"
    out.append("END PINS")
    out.append("COMPONENTS %d ;" % len(comps))
    for name, master, box, orient in comps:
        out.append(
            "- %s %s + FIXED ( %d %d ) %s ;"
            % (name, master, d(box[0]), d(box[1]), ORIENT[orient])
        )
    out.append("END COMPONENTS")
    out.append("END DESIGN")
    return "\n".join(out) + "\n"


def to_jpeg(src, dst):
    """The viewer's PNG as a JPEG: a tenth of the bytes, for the repository."""
    from PIL import Image

    Image.open(src).convert("RGB").save(dst, "JPEG", quality=85, optimize=True)


def plot_density(path, density_csv, macros, die, title):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    rows = [
        [float(v) for v in line.split(",")]
        for line in open(density_csv)
        if not line.startswith("#")
    ]
    head = open(density_csv).readline()
    bin_um = float(re.search(r"bin_um ([\d.]+)", head).group(1))
    w, h = die[2] - die[0], die[3] - die[1]
    fig, ax = plt.subplots(figsize=(7, 7 * h / w + 0.6))
    im = ax.imshow(
        rows,
        origin="lower",
        extent=[0, len(rows[0]) * bin_um, 0, len(rows) * bin_um],
        cmap="viridis",
        vmin=0,
        vmax=1,
    )
    for m in macros:
        x0, y0, x1, y1 = m["box"]
        ax.add_patch(
            Rectangle(
                (x0 - die[0], y0 - die[1]),
                x1 - x0,
                y1 - y0,
                fill=False,
                edgecolor="white",
                linewidth=0.4,
            )
        )
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_xlabel("µm")
    ax.set_title(
        "%s: standard-cell density per %g µm bin (macros outlined)" % (title, bin_um),
        fontsize=9,
    )
    fig.colorbar(im, ax=ax, fraction=0.04, label="cell area / bin area")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


PALETTE = [
    "#e6194b",
    "#3cb44b",
    "#ffe119",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#f032e6",
    "#bfef45",
    "#fabed4",
    "#469990",
    "#dcbeff",
    "#9a6324",
    "#fffac8",
    "#800000",
    "#aaffc3",
]


def module_grid(modules_csv, die, bin_um, top=16):
    """Which module's cells are where in one part: each bin owned by the
    module with the most standard-cell area in it. The depth is the one that
    splits the part into the most modules of at least 2 % of its cell area
    each, at most `top` of them. Returns the grid (row 0 at the bottom, NaN
    where no module owns the bin), the modules, their labels, their cells'
    centres in the part's coordinates, and the common path above them."""
    rows = read_csv(modules_csv)
    by_depth = {}
    for r in rows:
        d = by_depth.setdefault(int(r["depth"]), {})
        d.setdefault(r["module"], []).append(
            (int(r["i"]), int(r["j"]), float(r["area_um2"]))
        )
    total = sum(a for r in by_depth.get(1, {}).values() for _, _, a in r) or 1.0
    best = None
    for depth, mods in sorted(by_depth.items()):
        big = [
            m
            for m, cells in mods.items()
            if sum(a for _, _, a in cells) >= 0.02 * total
        ]
        if best is None or len(big) > best[1]:
            best = (depth, len(big))
    mods = by_depth[best[0]]
    order = sorted(mods, key=lambda m: -sum(a for _, _, a in mods[m]))[:top]
    owner = {}
    for idx, m in enumerate(order):
        for i, j, a in mods[m]:
            if a > owner.get((i, j), (-1, 0))[1]:
                owner[(i, j)] = (idx, a)
    nx = int(-(-(die[2] - die[0]) // bin_um))
    ny = int(-(-(die[3] - die[1]) // bin_um))
    grid = [[float("nan")] * nx for _ in range(ny)]
    for (i, j), (idx, _) in owner.items():
        if 0 <= i < nx and 0 <= j < ny:
            grid[j][i] = idx
    common = os.path.commonprefix([m + "/" for m in order]) if len(order) > 1 else ""
    common = common[: common.rfind("/") + 1]
    # each module by its own name, with its parent's where two would read
    # the same; a long generated name by its stem:
    # issueQueueALU0BJU0_AluCsrFence... -> issueQueueALU0BJU0
    leaf = {
        m: (
            m.split("/")[-1].split("_")[0]
            if len(m.split("/")[-1]) > 20
            else m.split("/")[-1]
        )
        for m in order
    }
    twice = {n for n in leaf.values() if list(leaf.values()).count(n) > 1}
    label = {
        m: ("/".join(m.split("/")[-2:]) if leaf[m] in twice else leaf[m]) for m in order
    }
    centre = {}
    for m in order:
        cells = mods[m]
        a = sum(c[2] for c in cells)
        centre[m] = (
            sum((c[0] + 0.5) * bin_um * c[2] for c in cells) / a,
            sum((c[1] + 0.5) * bin_um * c[2] for c in cells) / a,
        )
    return {
        "grid": grid,
        "order": order,
        "label": label,
        "centre": centre,
        "common": common.rstrip("/"),
        "nx": nx,
        "ny": ny,
        "bin_um": bin_um,
    }


def draw_modules(ax, g, x0, y0, sx, sy, fontsize, zorder=0):
    """One part's module grid on `ax`, its origin at (x0, y0), scaled."""
    from matplotlib.colors import ListedColormap

    n = len(g["order"])
    ax.imshow(
        g["grid"],
        origin="lower",
        extent=[
            x0,
            x0 + g["nx"] * g["bin_um"] * sx,
            y0,
            y0 + g["ny"] * g["bin_um"] * sy,
        ],
        cmap=ListedColormap(PALETTE[:n]),
        vmin=-0.5,
        vmax=n - 0.5,
        interpolation="nearest",
        zorder=zorder,
    )
    for idx, m in enumerate(g["order"]):
        cx, cy = g["centre"][m]
        ax.text(
            x0 + cx * sx,
            y0 + cy * sy,
            g["label"][m],
            ha="center",
            va="center",
            fontsize=fontsize,
            weight="bold",
            color="black",
            zorder=zorder + 2,
            bbox=dict(
                boxstyle="round,pad=0.15",
                facecolor=PALETTE[idx],
                edgecolor="black",
                linewidth=0.4,
            ),
        )


def draw_macros(ax, macros, die, x0=0.0, y0=0.0, label=True, zorder=1):
    from matplotlib.patches import Rectangle

    w, h = die[2] - die[0], die[3] - die[1]
    for m in macros:
        a0, b0, a1, b1 = m["box"]
        big = (a1 - a0) * (b1 - b0) > 0.004 * w * h
        ax.add_patch(
            Rectangle(
                (x0 + a0 - die[0], y0 + b0 - die[1]),
                a1 - a0,
                b1 - b0,
                facecolor="none",
                edgecolor="white",
                linewidth=0.5,
                zorder=zorder,
            )
        )
        if big and label:
            ax.text(
                x0 + (a0 + a1) / 2 - die[0],
                y0 + (b0 + b1) / 2 - die[1],
                m["master"],
                ha="center",
                va="center",
                fontsize=7,
                color="white",
                weight="bold",
            )


def plot_modules(path, g, macros, die, title):
    """One part's module map: which module's cells are where, the modules
    named at their cells' centre, the macros outlined."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    w, h = die[2] - die[0], die[3] - die[1]
    fig, ax = plt.subplots(figsize=(8, 8 * h / w + 0.4))
    ax.set_facecolor("#202020")
    draw_modules(ax, g, 0.0, 0.0, 1.0, 1.0, 7)
    draw_macros(ax, macros, die)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_xlabel("µm")
    ax.set_title(
        "%s: where each module's cells are%s (macros outlined)"
        % (title, " (under %s)" % g["common"] if g["common"] else ""),
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_tile_modules(path, top_g, top_die, top_macros, blocks):
    """The whole tile's module map: the parent's own modules, and inside each
    block's footprint the block's module map, scaled from the outline it
    was built at as the floorplan is. blocks: name -> (grid, origin,
    footprint, built, the block's macros placed in the footprint)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    w, h = top_die[2] - top_die[0], top_die[3] - top_die[1]
    fig, ax = plt.subplots(figsize=(11, 11 * h / w + 0.4))
    ax.set_facecolor("#202020")
    draw_modules(ax, top_g, 0.0, 0.0, 1.0, 1.0, 6, zorder=0)
    draw_macros(ax, top_macros, top_die, zorder=1)
    for name, (g, origin, footprint, built, macros) in sorted(blocks.items()):
        ox, oy = origin[0] - top_die[0], origin[1] - top_die[1]
        ax.add_patch(
            Rectangle(
                (ox, oy),
                footprint[0],
                footprint[1],
                facecolor="#202020",
                edgecolor="none",
                zorder=3,
            )
        )
        draw_modules(
            ax,
            g,
            ox,
            oy,
            footprint[0] / built[0],
            footprint[1] / built[1],
            4.5,
            zorder=4,
        )
        draw_macros(ax, macros, [0, 0] + list(footprint), ox, oy, label=False, zorder=5)
        ax.add_patch(
            Rectangle(
                (ox, oy),
                footprint[0],
                footprint[1],
                facecolor="none",
                edgecolor="white",
                linewidth=1.5,
                zorder=7,
            )
        )
        ax.text(
            ox + 4,
            oy + footprint[1] - 4,
            name,
            ha="left",
            va="top",
            fontsize=9,
            color="white",
            weight="bold",
            zorder=8,
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor="#202020",
                edgecolor="white",
                linewidth=0.6,
            ),
        )
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_xlabel("µm")
    ax.set_title(
        "XSTile: every module, the parent's and each block's in its footprint (memory macros outlined)",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_histogram(path, hist, period, title, target=2000):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    b, x0, counts = hist["bin_ps"], hist["from_ps"], hist["counts"]
    xs = [x0 + i * b for i in range(len(counts))]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(xs, counts, width=b, align="edge", color="#4a7ab5", linewidth=0)
    ax.axvline(period, color="#c0392b", linewidth=1)
    ax.text(
        period, max(counts), " %d ps" % period, color="#c0392b", fontsize=8, va="top"
    )
    if target and xs[0] < target:
        ax.axvline(target, color="#555", linewidth=0.8, linestyle="--")
    ax.set_xlabel("endpoint's minimum period, ps (SDC period minus its worst slack)")
    ax.set_ylabel("reg2reg endpoints")
    ax.set_title(
        "%s at global route: every register-to-register endpoint" % title, fontsize=9
    )
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--top", required=True)
    p.add_argument(
        "--part",
        action="append",
        required=True,
        help="<part>=<snapshot dir>,<kpi.txt>,<kpi_paths.txt>",
    )
    p.add_argument("--kpi-json", required=True)
    p.add_argument(
        "--facts",
        required=True,
        help="kit/pinned/facts.json: the kit netlist's macro instances",
    )
    p.add_argument(
        "--settings",
        action="append",
        default=[],
        help="<part>=<stage>.mk the flow wrote",
    )
    p.add_argument("--out", required=True, help="relative to the workspace")
    a = p.parse_args()
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not ws:
        sys.exit("snapshot: run me with bazelisk run")
    out = os.path.join(ws, a.out)
    if os.path.isdir(out):
        shutil.rmtree(out)
    for d in ("images", "floorplan/flat", "floorplan/hier", "paths", "settings"):
        os.makedirs(os.path.join(out, d))

    parts = {}
    for spec in a.part:
        name, files = spec.split("=", 1)
        snap, kpi, paths = files.split(",")
        parts[name] = {"dir": snap, "kpi": kpi, "paths": paths}
    blocks = [n for n in parts if n != a.top]

    kpi_runs = json.load(open(a.kpi_json))["runs"]
    row = kpi_runs[-1]
    commit = subprocess.check_output(
        ["git", "-C", ws, "rev-parse", "HEAD"], text=True
    ).strip()
    report = {
        "commit": commit,
        "made": datetime.date.today().isoformat(),
        "kpi_row": {k: row[k] for k in ("date", "parent_ps", "blocks") if k in row},
        "parts": {},
    }

    data = {}
    for name, f in parts.items():
        stats = json.load(open(os.path.join(f["dir"], "stats.json")))
        kpi = parse_kpi(f["kpi"])
        cong = parse_congestion(os.path.join(f["dir"], "congestion.txt"))
        macros = [
            {
                "name": r["name"],
                "master": r["master"],
                "box": boxf(r),
                "orient": r["orient"],
            }
            for r in read_csv(os.path.join(f["dir"], "macros.csv"))
        ]
        data[name] = {
            "stats": stats,
            "macros": macros,
            "pins": read_csv(os.path.join(f["dir"], "pins.csv")),
        }
        report["parts"][name] = {"stats": stats, "kpi": kpi, "congestion": cong}
        for img in IMAGES:
            src = os.path.join(f["dir"], img + ".png")
            if not os.path.exists(src):
                sys.exit(
                    "snapshot: %s has no %s.png; snapshot.tcl's log says why"
                    % (name, img)
                )
            to_jpeg(src, os.path.join(out, "images", "%s_%s.jpg" % (name, img)))
        plot_density(
            os.path.join(out, "images", "%s_density.png" % name),
            os.path.join(f["dir"], "density.csv"),
            macros,
            stats["die_um"],
            name,
        )
        bin_um = float(
            re.search(
                r"bin_um ([\d.]+)",
                open(os.path.join(f["dir"], "density.csv")).readline(),
            ).group(1)
        )
        data[name]["modules"] = module_grid(
            os.path.join(f["dir"], "modules.csv"), stats["die_um"], bin_um
        )
        plot_modules(
            os.path.join(out, "images", "%s_module_map.png" % name),
            data[name]["modules"],
            macros,
            stats["die_um"],
            name,
        )
        plot_histogram(
            os.path.join(out, "images", "%s_histogram.png" % name),
            kpi["histogram"],
            kpi["period_ps"],
            name,
        )
        shutil.copy(f["paths"], os.path.join(out, "paths", "%s.txt" % name))

    # the settings each stage ran with, ORFS's defaults for the rest
    for spec in a.settings:
        name, path = spec.split("=", 1)
        stage = os.path.basename(path)[: -len(".mk")]
        os.makedirs(os.path.join(out, "settings", name), exist_ok=True)
        shutil.copy(path, os.path.join(out, "settings", name, stage + ".mk"))
        values = report["parts"][name].setdefault("settings", {})
        for line in open(path):
            m = re.match(r"export (\w+)\?=(.*)", line.rstrip("\n"))
            if m:
                values.setdefault(m.group(1), {})[stage] = m.group(2)

    top = data[a.top]
    dbu = int(top["stats"]["dbu_per_um"])
    die = top["stats"]["die_um"]
    master_pins = read_csv(os.path.join(parts[a.top]["dir"], "master_pins.csv"))
    top_pins = [(r["name"], r["direction"], r["layer"], boxf(r)) for r in top["pins"]]

    flat_rows, flat_macros, hier_comps = [], [], []
    for m in top["macros"]:
        if m["master"] in blocks:
            hier_comps.append((m["name"], m["master"], m["box"], m["orient"]))
            continue
        hier_comps.append((m["name"], m["master"], m["box"], m["orient"]))
        flat_macros.append(dict(m))
        flat_rows.append(
            {
                "name": m["name"],
                "master": m["master"],
                "x0": m["box"][0],
                "y0": m["box"][1],
                "x1": m["box"][2],
                "y1": m["box"][3],
                "orient": m["orient"],
                "block": "",
                "block_x0": "",
                "block_y0": "",
                "built_x0": "",
                "built_y0": "",
            }
        )

    # every macro under the kit netlist's own name: a block's flow flattens
    # some hierarchy the kit's synthesis keeps, so a path may differ in its
    # separators (internalBanks_0/m in the kit, internalBanks_0.m in the
    # block), and nothing else
    facts = json.load(open(a.facts))
    sep = lambda n: n.replace("/", ".")
    netlist = {}
    for master, d in facts["macros"].items():
        for i in d["instances"]:
            netlist[sep(i)] = (i, master)

    def kit_name(name, master):
        hit = netlist.get(sep(name))
        if hit is None or hit[1] != master:
            sys.exit(
                "snapshot: %s (%s) is no macro of the kit's netlist; is kit/pinned/ of this netlist?"
                % (name, master)
            )
        return hit[0]

    for row in flat_rows:
        row["name"] = kit_name(row["name"], row["master"])
    for m in flat_macros:
        m["name"] = kit_name(m["name"], m["master"])
    hier_comps = [
        (kit_name(n, mm) if mm not in blocks else n, mm, bx, o)
        for n, mm, bx, o in hier_comps
    ]

    scales, tile_blocks = {}, {}
    for b in blocks:
        insts = [m for m in top["macros"] if m["master"] == b]
        if len(insts) != 1:
            sys.exit("snapshot: %s has %d instances in %s" % (b, len(insts), a.top))
        inst = insts[0]
        if inst["orient"] != "R0":
            sys.exit(
                "snapshot: %s is %s in %s; the dissolve assumes R0"
                % (b, inst["orient"], a.top)
            )
        pins = [r for r in master_pins if r["master"] == b]
        fw, fh = float(pins[0]["width"]), float(pins[0]["height"])
        bd = data[b]["stats"]["die_um"]
        sx, sy = fw / (bd[2] - bd[0]), fh / (bd[3] - bd[1])
        scales[b] = {
            "instance": inst["name"],
            "footprint_um": [fw, fh],
            "built_um": [bd[2] - bd[0], bd[3] - bd[1]],
            "scale": [round(sx, 5), round(sy, 5)],
            "origin_um": inst["box"][:2],
        }
        fx, kx = squeeze(
            [(m["box"][0] - bd[0], m["box"][2] - bd[0]) for m in data[b]["macros"]],
            bd[2] - bd[0],
            fw,
        )
        fy, ky = squeeze(
            [(m["box"][1] - bd[1], m["box"][3] - bd[1]) for m in data[b]["macros"]],
            bd[3] - bd[1],
            fh,
        )
        scales[b]["free_space_scale"] = [round(kx, 5), round(ky, 5)]
        comps = []
        for m in data[b]["macros"]:
            x0, y0, x1, y1 = m["box"]
            fb = [fx(x0 - bd[0]), fy(y0 - bd[1])]
            fb += [fb[0] + x1 - x0, fb[1] + y1 - y0]
            flat_name = kit_name("%s/%s" % (inst["name"], m["name"]), m["master"])
            if not flat_name.startswith(inst["name"] + "/"):
                sys.exit("snapshot: %s is not under %s" % (flat_name, inst["name"]))
            comps.append(
                (flat_name[len(inst["name"]) + 1 :], m["master"], fb, m["orient"])
            )
            tb = [
                fb[0] + inst["box"][0],
                fb[1] + inst["box"][1],
                fb[2] + inst["box"][0],
                fb[3] + inst["box"][1],
            ]
            flat_macros.append(
                {
                    "name": flat_name,
                    "master": m["master"],
                    "box": tb,
                    "orient": m["orient"],
                }
            )
            flat_rows.append(
                {
                    "name": flat_name,
                    "master": m["master"],
                    "x0": round(tb[0], 4),
                    "y0": round(tb[1], 4),
                    "x1": round(tb[2], 4),
                    "y1": round(tb[3], 4),
                    "orient": m["orient"],
                    "block": b,
                    "block_x0": round(fb[0], 4),
                    "block_y0": round(fb[1], 4),
                    "built_x0": x0,
                    "built_y0": y0,
                }
            )
        bpins = [(r["pin"], r["direction"], r["layer"], boxf(r)) for r in pins]
        with open(os.path.join(out, "floorplan/hier/%s.def" % b), "w") as f:
            f.write(def_text(b, dbu, [0, 0, fw, fh], bpins, comps))
        tile_blocks[b] = (
            data[b]["modules"],
            inst["box"][:2],
            (fw, fh),
            (bd[2] - bd[0], bd[3] - bd[1]),
            [{"box": c[2], "master": c[1]} for c in comps],
        )

    plot_tile_modules(
        os.path.join(out, "images", "tile_module_map.png"),
        top["modules"],
        die,
        [m for m in top["macros"] if m["master"] not in blocks],
        tile_blocks,
    )

    with open(os.path.join(out, "floorplan/hier/%s.def" % a.top), "w") as f:
        f.write(def_text(a.top, dbu, die, top_pins, hier_comps))
    with open(os.path.join(out, "floorplan/flat/%s.def" % a.top), "w") as f:
        f.write(
            def_text(
                a.top,
                dbu,
                die,
                top_pins,
                [(m["name"], m["master"], m["box"], m["orient"]) for m in flat_macros],
            )
        )
    with open(os.path.join(out, "floorplan/macros.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(flat_rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(flat_rows, key=lambda r: r["name"]))

    over = overlaps(flat_macros)
    outside = [
        m["name"]
        for m in flat_macros
        if m["box"][0] < die[0]
        or m["box"][1] < die[1]
        or m["box"][2] > die[2]
        or m["box"][3] > die[3]
    ]
    named = {m["name"] for m in flat_macros}
    unplaced = sorted(set(i for i, _ in netlist.values()) - named)
    if unplaced or len(named) != len(flat_macros):
        sys.exit(
            "snapshot: the floorplan places %d macros once of the netlist's %d; not placed: %s"
            % (len(named), len(netlist), unplaced[:10])
        )
    report["floorplan"] = {
        "blocks": scales,
        "macros": len(flat_macros),
        "overlapping_pairs": over,
        "outside_die": outside,
    }
    with open(os.path.join(out, "snapshot.json"), "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
        f.write("\n")
    if over or outside:
        sys.exit(
            "snapshot: the dissolved floorplan has %d overlapping pairs and %d macros outside the die: %s"
            % (len(over), len(outside), (over + outside)[:10])
        )
    print(
        "snapshot: %d macros flat, %d overlapping pairs, %d outside the die; written to %s"
        % (len(flat_macros), len(over), len(outside), a.out)
    )


if __name__ == "__main__":
    main()
