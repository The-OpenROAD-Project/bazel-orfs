"""The study's tables and figure, from whatever results/ holds.

  report.py <results dir> [--svg out.svg]

results/facts/<flow>.tsv is read.tcl's read of a flow's global route;
results/arms/<arm>_{fix,control}.tsv the fix arms' reads;
results/endpoints/<flow>.txt every reg2reg endpoint's period over its
own clock's period, one per line; results/not_measured.json the flows that failed before timing or
were left out. A section with no data says "Not yet measured".
"""

import argparse
import json
import math
import os
import sys

from classify import FLAGS_DOC, classify, parse

ARMS = {
    "asap7_gcd": ("asap7/gcd:gcd", "IO 20 % → 2 %"),
    "asap7_riscv32i": ("asap7/riscv32i:riscv_top", "IO 12.5 % → 2 %"),
    "gf180_riscv32i": ("gf180/riscv32i:riscv", "IO 20 % → 2 %"),
    "nangate45_picorv32": ("nangate45/picorv32:picorv32", "IO 20 % → 2 %"),
    "ihp_sg13g2_i2c_gpio_expander": (
        "ihp-sg13g2/i2c-gpio-expander:I2cGpioExpanderTop",
        "IO 4.0 → 0.2 ns",
    ),
    "nangate45_gcd": ("nangate45/gcd:gcd", "clock 0.25 → 0.433 ns"),
    "sky130hd_gcd": ("sky130hd/gcd:gcd", "clock 1.1 → 2.61 ns"),
    "ihp_sg13g2_riscv32i": ("ihp-sg13g2/riscv32i:riscv", "clock 2.0 → 3.87 ns"),
    "asap7_tpu": ("asap7/tpu:tpu", "clock 200 → 570 ps"),
    "nangate45_tpu": ("nangate45/tpu:tpu", "clock 1.0 → 1.42 ns"),
    "asap7_picorv32": ("asap7/picorv32:picorv32", "clock 300 → 437 ps, IO 20 % → 2 %"),
}


def fmt(v):
    return "–" if v is None else "%.4g" % v


NAMES = {}


def display(stem):
    """An ORFS design as ORFS names it: its directory, and its top where
    the directory holds more than one flow."""
    return NAMES.get(stem, stem)


def load(results):
    facts = os.path.join(results, "facts")
    if not os.path.isdir(facts) or not os.listdir(facts):
        raise SystemExit("no results in %s: run the campaign first" % results)
    names = os.path.join(results, "names.json")
    NAMES.clear()
    if os.path.exists(names):
        NAMES.update(json.load(open(names)))
    designs = {}
    for f in sorted(os.listdir(facts)):
        text = open(os.path.join(facts, f)).read()
        designs[f[: -len(".tsv")]] = (text, classify(parse(text)))
    return designs


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def report(results):
    designs = load(results)
    done = list(designs.values())
    out = []
    counts = {}
    for _, r in done:
        for f in r["flags"]:
            counts[f] = counts.get(f, 0) + 1
    flagged = sum(1 for _, r in done if r["flags"])
    out.append("## What sets WNS\n")
    out.append(groups_table(designs))
    out.append("\n## Flags\n")
    out.append("%d flows measured, %d flagged.\n" % (len(done), flagged))
    out.append(
        table(
            ["flag", "pathology", "flows"],
            [
                [f, FLAGS_DOC[f], counts.get(f, 0)]
                for f in sorted(FLAGS_DOC, key=lambda k: int(k[1:]))
            ],
        )
    )
    out.append("\n## Per flow\n")
    rows = []
    for stem, (_, r) in sorted(designs.items()):
        rows.append(
            [
                "`%s`" % display(stem),
                fmt(r["clock"]),
                fmt(r["reg2reg_min_period"]),
                fmt(r["wns"]),
                r["worst_group"],
                " ".join(r["flags"]) or "–",
                "; ".join("%s: %s" % (k, v) for k, v in r["evidence"].items()).replace(
                    "|", "\\|"
                ),
            ]
        )
    out.append(
        table(
            [
                "flow",
                "clock",
                "reg2reg period",
                "WNS",
                "worst group",
                "flags",
                "evidence",
            ],
            rows,
        )
    )
    out.append("\n## Fix arms\n")
    arms_dir = os.path.join(results, "arms")
    rows = []
    for stem, (flow, change) in ARMS.items():
        fix = os.path.join(arms_dir, stem + "_fix.tsv")
        ctl = os.path.join(arms_dir, stem + "_control.tsv")
        if not (os.path.exists(fix) and os.path.exists(ctl)):
            rows.append(["`%s`" % flow, change, "Not yet measured", "", "", "", "", ""])
            continue
        swept = [t for t, _ in designs.values() if t == open(ctl).read()]
        b, a = classify(parse(open(ctl).read())), classify(parse(open(fix).read()))
        p0, p1 = b["reg2reg_min_period"], a["reg2reg_min_period"]
        rows.append(
            [
                "`%s`" % flow,
                change,
                "%s → %s"
                % (" ".join(b["flags"]) or "none", " ".join(a["flags"]) or "none"),
                "%s → %s" % (b["worst_group"], a["worst_group"]),
                "%s → %s" % (fmt(b["wns"]), fmt(a["wns"])),
                "%s → %s" % (fmt(p0), fmt(p1)),
                "%+.1f %%" % ((p1 - p0) / p0 * 100) if p0 and p1 else "–",
                "identical" if swept else "**differs**",
            ]
        )
    out.append(
        table(
            [
                "flow",
                "change",
                "flags",
                "worst group",
                "WNS",
                "reg2reg period",
                "Δ period",
                "control vs sweep",
            ],
            rows,
        )
    )
    nm = os.path.join(results, "not_measured.json")
    if os.path.exists(nm):
        d = json.load(open(nm))
        out.append("\n## Not measured\n")
        out.append(
            table(
                ["flow", "why"],
                [["`%s`" % f["flow"], f["reason"]] for f in d["failed"]]
                + [
                    [
                        "`%s`" % f,
                        "left out: large, global route not in the remote cache",
                    ]
                    for f in d["excluded"]
                ],
            )
        )
    return "\n".join(out) + "\n", designs


def svg(designs):
    """WNS's period against the reg2reg period, both over the clock."""
    W, H, L, R, T, B = 640, 420, 56, 16, 16, 44
    xmax = ymax = 3.0
    X = lambda v: L + min(v, xmax) / xmax * (W - L - R)
    Y = lambda v: H - B - min(max(v, 0), ymax) / ymax * (H - T - B)
    colour = {"io": "#2a78d6", "clk": "#eb6834", "rest": "#898781"}
    parts = ['<rect width="%d" height="%d" fill="#fcfcfb"/>' % (W, H)]
    for v in (0, 0.5, 1, 1.5, 2, 2.5, 3):
        parts.append(
            '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#e1e0d9"/>'
            '<text x="%.1f" y="%d" text-anchor="middle">%g</text>'
            '<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="#e1e0d9"/>'
            '<text x="%d" y="%.1f" text-anchor="end">%g</text>'
            % (
                X(v),
                X(v),
                T,
                H - B,
                X(v),
                H - B + 16,
                v,
                L,
                W - R,
                Y(v),
                Y(v),
                L - 8,
                Y(v) + 4,
                v,
            )
        )
    parts.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#52514e" stroke-dasharray="4 4"/>'
        % (X(0), Y(0), X(3), Y(3))
    )
    for x, label, anchor, dx in (
        (1.3, "repair gave up (P8) →", "start", 6),
        (0.85, "← slack-rich (P7)", "end", -6),
    ):
        parts.append(
            '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#c3c2b7" stroke-dasharray="2 4"/>'
            '<text x="%.1f" y="%d" text-anchor="%s">%s</text>'
            % (X(x), X(x), T, H - B, X(x) + dx, T + 14, anchor, label)
        )
    parts.append(
        '<text x="%.1f" y="%.1f">above the diagonal: something else sets WNS (P1)</text>'
        % (X(0.12), Y(2.6))
    )
    for _, r in designs.values():
        if r["reg2reg_min_period"] is None:
            continue
        f = set(r["flags"])
        c = "io" if "P1" in f else "clk" if f & {"P7", "P8"} else "rest"
        parts.append(
            '<circle cx="%.1f" cy="%.1f" r="5" fill="%s" stroke="#fcfcfb" stroke-width="2"/>'
            % (
                X(r["reg2reg_min_period"] / r["clock"]),
                Y((r["clock"] - r["wns"]) / r["clock"]),
                colour[c],
            )
        )
    legend = [
        ("io", "IO path sets WNS (P1)"),
        ("clk", "clock out of reach or slack-rich (P7, P8)"),
        ("rest", "other flags or none"),
    ]
    for i, (c, label) in enumerate(legend):
        parts.append(
            '<circle cx="%d" cy="%d" r="5" fill="%s"/><text x="%d" y="%d">%s</text>'
            % (L + 330, T + 210 + 18 * i, colour[c], L + 342, T + 214 + 18 * i, label)
        )
    parts.append(
        '<text x="%d" y="%d" text-anchor="middle" fill="#0b0b0b">reg2reg period ÷ clock</text>'
        '<text transform="translate(14 %d) rotate(-90)" text-anchor="middle" fill="#0b0b0b">(clock − WNS) ÷ clock</text>'
        % ((L + W - R) // 2, H - 6, (T + H - B) // 2)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="system-ui, sans-serif" '
        'font-size="11" fill="#52514e">' % (W, H) + "".join(parts) + "</svg>\n"
    )


# What sets a design's WNS, one group each, in the order the figures
# and the list show them
GROUPS = [
    ("reg2reg logic", lambda f: not f & {"P0", "P1", "P5", "P7", "P8"}),
    (
        "reg2reg logic at its one-flop-loop floor",
        lambda f: "P5" in f and not f & {"P0", "P1", "P7", "P8"},
    ),
    ("an input/output budget in the .sdc", lambda f: "P1" in f and "P8" not in f),
    ("where repair stopped: the clock is out of reach", lambda f: "P8" in f),
    ("nothing: met with room to spare", lambda f: "P7" in f and not f & {"P1", "P8"}),
]


def grouped(designs):
    """[(group, [(stem, result), ...])], each group in WNS order."""
    out = []
    for name, test in GROUPS:
        members = [
            (stem, r)
            for stem, (_, r) in designs.items()
            if r["reg2reg_min_period"] is not None and test(set(r["flags"]))
        ]
        members.sort(key=lambda m: (m[1]["clock"] - m[1]["wns"]) / m[1]["clock"])
        out.append((name, members))
    return out


def groups_table(designs):
    rows = []
    for name, members in grouped(designs):
        rows.append(
            [
                name,
                len(members),
                ", ".join(
                    "`%s`%s" % (display(s), "\\*" if "P3" in r["flags"] else "")
                    for s, r in members
                ),
            ]
        )
    return table(["WNS is set by", "designs", "which"], rows) + (
        "\n\n\\* has registers the timer never sees (check_setup)."
    )


def _frame(W, H, body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'font-family="system-ui, sans-serif" font-size="11" fill="#52514e">'
        '<rect width="%d" height="%d" fill="#fcfcfb"/>' % (W, H, W, H)
        + "".join(body)
        + "</svg>\n"
    )


def _x_axis(X, top, bottom, label, ticks):
    out = []
    for v in ticks:
        out.append(
            '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s"%s/>'
            '<text x="%.1f" y="%d" text-anchor="middle">%g</text>'
            % (
                X(v),
                X(v),
                top,
                bottom,
                "#52514e" if v == 1 else "#e1e0d9",
                ' stroke-width="1.5"' if v == 1 else "",
                X(v),
                bottom + 14,
                v,
            )
        )
    out.append(
        '<text x="%.1f" y="%d" text-anchor="middle" fill="#0b0b0b">%s</text>'
        % ((X(ticks[0]) + X(ticks[-1])) / 2, bottom + 30, label)
    )
    return out


def _diamond(x, y):
    return (
        '<path d="M%.1f %.1f l5 5 l-5 5 l-5 -5 z" fill="#eb6834" stroke="#fcfcfb" stroke-width="1"/>'
        % (x, y - 5)
    )


def _legend(x, y, items):
    out = []
    for i, (kind, text) in enumerate(items):
        cx = x + 250 * i
        if kind == "dot":
            out.append('<circle cx="%d" cy="%d" r="4.5" fill="#2a78d6"/>' % (cx, y))
        elif kind == "diamond":
            out.append(_diamond(cx, y))
        elif kind == "hist":
            out.append(
                '<rect x="%d" y="%d" width="10" height="9" fill="#2a78d6" fill-opacity=".35" stroke="#2a78d6"/>'
                % (cx - 5, y - 5)
            )
        else:
            out.append(
                '<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="#52514e" stroke-width="2"/>'
                % (cx, cx, y - 6, y + 6)
            )
        out.append(
            '<text x="%d" y="%d" fill="#0b0b0b">%s</text>' % (cx + 10, y + 4, text)
        )
    return out


def dumbbell_svg(designs):
    """One row per design, grouped by what sets its WNS: the reg2reg period,
    the period WNS reports and the loop floor, all over the clock."""
    RH, L, R, T, W, XMAX = 15, 330, 24, 44, 960, 3.0
    groups = grouped(designs)
    n = sum(len(m) for _, m in groups) + 2 * len(groups)
    H = T + n * RH + 44
    X = lambda v: L + min(max(v, 0), XMAX) / XMAX * (W - L - R)
    body = _x_axis(
        X,
        T - 6,
        H - 40,
        "period ÷ the clock the .sdc asks for (1 = the clock)",
        [0, 0.5, 1, 1.5, 2, 2.5, 3],
    )
    body += _legend(
        L - 200,
        16,
        [
            ("dot", "reg2reg period: what the logic reaches"),
            ("diamond", "clock − WNS: what WNS reports"),
            ("tick", "one-flop-loop floor"),
        ],
    )
    y = T
    for name, members in groups:
        y += RH
        body.append(
            '<text x="8" y="%d" font-weight="600" fill="#0b0b0b">%s (%d)</text>'
            % (y + 4, name, len(members))
        )
        for stem, r in members:
            y += RH
            clk = r["clock"]
            r2r, wns = r["reg2reg_min_period"] / clk, (clk - r["wns"]) / clk
            body.append(
                '<text x="%d" y="%d" text-anchor="end">%s%s</text>'
                % (L - 10, y + 4, display(stem), " *" if "P3" in r["flags"] else "")
            )
            body.append(
                '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#c3c2b7" stroke-width="2"/>'
                % (X(r2r), X(wns), y, y)
            )
            if r["floor"]:
                f = r["floor"] / clk
                body.append(
                    '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#52514e" stroke-width="2"/>'
                    % (X(f), X(f), y - 5, y + 5)
                )
            body.append(
                '<circle cx="%.1f" cy="%d" r="4.5" fill="#2a78d6" stroke="#fcfcfb" stroke-width="1.5"/>'
                % (X(r2r), y)
            )
            body.append(_diamond(X(wns), y))
        y += RH
    return _frame(W, H, body)


def ridgeline_svg(designs, endpoints):
    """Per design, the histogram of every reg2reg endpoint's period over its
    own clock (a design may have several), bins of 2 % of the clock, heights log(1 + count) scaled to each
    row's own peak, in the groups and order of dumbbell_svg."""
    RH, L, R, T, W, XMAX, BIN = 30, 330, 24, 44, 960, 3.0, 0.02
    groups = grouped(designs)
    n = sum(len(m) for _, m in groups) + 2 * len(groups)
    H = T + n * RH + 44
    X = lambda v: L + min(max(v, 0), XMAX) / XMAX * (W - L - R)
    body = _x_axis(
        X,
        T - 6,
        H - 40,
        "endpoint period ÷ the clock the .sdc asks for (1 = the clock)",
        [0, 0.5, 1, 1.5, 2, 2.5, 3],
    )
    body += _legend(
        L - 200,
        16,
        [
            ("hist", "reg2reg endpoints, log count per row"),
            ("diamond", "clock − WNS: what WNS reports"),
            ("tick", "one-flop-loop floor"),
        ],
    )
    y = T
    for name, members in groups:
        y += RH
        body.append(
            '<text x="8" y="%d" font-weight="600" fill="#0b0b0b">%s (%d)</text>'
            % (y - 6, name, len(members))
        )
        for stem, r in members:
            y += RH
            clk = r["clock"]
            periods = endpoints.get(stem)
            body.append(
                '<text x="%d" y="%d" text-anchor="end">%s (%s)</text>'
                % (L - 10, y - 4, display(stem), len(periods) if periods else "–")
            )
            body.append(
                '<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="#c3c2b7"/>'
                % (L, W - R, y, y)
            )
            if periods:
                bins = {}
                for p in periods:
                    b = int(min(p, XMAX) // BIN)
                    bins[b] = bins.get(b, 0) + 1
                top = max(math.log1p(c) for c in bins.values())
                pts = []
                for b in range(int(XMAX / BIN) + 1):
                    h = math.log1p(bins.get(b, 0)) / top * (RH - 6)
                    pts += [
                        "%.1f,%.1f" % (X(b * BIN), y - h),
                        "%.1f,%.1f" % (X((b + 1) * BIN), y - h),
                    ]
                body.append(
                    '<polygon points="%.1f,%d %s %.1f,%d" fill="#2a78d6" fill-opacity=".35" stroke="#2a78d6" stroke-width="1"/>'
                    % (X(0), y, " ".join(pts), X(XMAX), y)
                )
            if r["floor"]:
                f = r["floor"] / clk
                body.append(
                    '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#52514e" stroke-width="2"/>'
                    % (X(f), X(f), y - 10, y + 2)
                )
            body.append(_diamond(X((clk - r["wns"]) / clk), y - 1))
        y += RH // 2
    return _frame(W, H, body)


# overlay_svg's groups: GROUPS folded to the three stories the endpoints
# tell, in the palette's first three slots
OVERLAY = [
    ("WNS measures the reg2reg logic", "#2a78d6", (0, 1)),
    ("an input/output budget in the .sdc sets WNS", "#eb6834", (2,)),
    ("the clock is out of reach: WNS is where repair stopped", "#1baf7a", (3,)),
]


def overlay_svg(designs, endpoints):
    """Every design's endpoints on shared axes as one line each: the share
    of its reg2reg endpoints at or beyond each period (over its own clock),
    log scale, coloured by what sets its WNS; a bold line per group is the
    median across its designs. Where a line reaches the bottom is the
    design's worst endpoint; how steeply it gets there tells a wall of
    endpoints from a lone path. Below, where WNS puts each design."""
    W, L, R, T, PH, XMAX, STEP, YMIN = 960, 64, 24, 52, 330, 3.0, 0.005, 1e-4
    STRIP = 22
    H = T + PH + 40 + STRIP * len(OVERLAY) + 40
    X = lambda v: L + min(max(v, 0), XMAX) / XMAX * (W - L - R)
    Y = (
        lambda f: T
        + (math.log10(1) - math.log10(max(f, YMIN))) / -math.log10(YMIN) * PH
    )
    xs = [i * STEP for i in range(int(XMAX / STEP) + 1)]
    groups = grouped(designs)
    body = []
    for e in range(0, int(-math.log10(YMIN)) + 1):
        f = 10**-e
        body.append(
            '<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="#e1e0d9"/>'
            '<text x="%d" y="%.1f" text-anchor="end">%s</text>'
            % (
                L,
                W - R,
                Y(f),
                Y(f),
                L - 6,
                Y(f) + 4,
                "100 %" if e == 0 else "%g %%" % (100 * f),
            )
        )
    for v in (0, 0.5, 1, 1.5, 2, 2.5, 3):
        body.append(
            '<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="%s"%s/>'
            '<text x="%.1f" y="%d" text-anchor="middle">%g</text>'
            % (
                X(v),
                X(v),
                T,
                T + PH,
                "#52514e" if v == 1 else "#e1e0d9",
                ' stroke-width="1.5"' if v == 1 else "",
                X(v),
                T + PH + 14,
                v,
            )
        )
    body.append(
        '<text x="%.1f" y="%d" text-anchor="middle" fill="#0b0b0b">endpoint period ÷ the clock the .sdc asks for (1 = the clock)</text>'
        % ((L + W - R) / 2, T + PH + 30)
    )
    body.append(
        '<text transform="translate(14 %d) rotate(-90)" text-anchor="middle" fill="#0b0b0b">share of a design\'s endpoints at or beyond</text>'
        % (T + PH / 2)
    )
    medians = []
    for label, colour, members_of in OVERLAY:
        rows = []
        for gi in members_of:
            for stem, r in groups[gi][1]:
                periods = sorted(endpoints.get(stem) or [])
                if not periods:
                    continue
                n, j, row = len(periods), 0, []
                for x in xs:
                    while j < n and periods[j] < x:
                        j += 1
                    row.append((n - j) / n)
                rows.append(row)
        for row in rows:
            pts = " ".join("%.1f,%.1f" % (X(x), Y(f)) for x, f in zip(xs, row) if f > 0)
            body.append(
                '<polyline points="%s" fill="none" stroke="%s" stroke-width="1" stroke-opacity=".35"/>'
                % (pts, colour)
            )
        if rows:
            medians.append(
                (
                    colour,
                    [
                        sorted(r[i] for r in rows)[len(rows) // 2]
                        for i in range(len(xs))
                    ],
                )
            )
    for colour, med in medians:
        pts = " ".join("%.1f,%.1f" % (X(x), Y(f)) for x, f in zip(xs, med) if f > 0)
        body.append(
            '<polyline points="%s" fill="none" stroke="#fcfcfb" stroke-width="5"/>'
            % pts
        )
        body.append(
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="2.5"/>'
            % (pts, colour)
        )
    y = T + PH + 52
    body.append(
        '<text x="%d" y="%d" font-weight="600" fill="#0b0b0b">where WNS puts each design</text>'
        % (L, y - 6)
    )
    for label, colour, members_of in OVERLAY:
        y += STRIP
        body.append(
            '<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="#e1e0d9"/>'
            % (L, W - R, y, y)
        )
        for gi in members_of:
            for stem, r in groups[gi][1]:
                w = (r["clock"] - r["wns"]) / r["clock"]
                body.append(
                    '<path d="M%.1f %d l4 4 l-4 4 l-4 -4 z" fill="%s" fill-opacity=".8"/>'
                    % (X(w), y - 4, colour)
                )
        n = sum(len(groups[gi][1]) for gi in members_of)
        body.append(
            '<rect x="%.1f" y="%d" width="10" height="3" fill="%s"/>'
            % (X(1.55) - 14, y - 10, colour)
        )
        body.append(
            '<text x="%.1f" y="%d" fill="#0b0b0b">%s (%d)</text>'
            % (X(1.55), y - 6, label, n)
        )
    for i, (label, colour, _) in enumerate(OVERLAY):
        x = L + 300 * i
        body.append(
            '<line x1="%d" x2="%d" y1="18" y2="18" stroke="%s" stroke-width="2.5"/>'
            % (x, x + 18, colour)
        )
        body.append(
            '<text x="%d" y="22" fill="#0b0b0b">%s</text>'
            % (x + 24, label.split(":")[0])
        )
    body.append(
        '<text x="%d" y="38">thin: one design each; bold: the median of the group</text>'
        % L
    )
    return _frame(W, H, body)


def load_endpoints(results):
    d = os.path.join(results, "endpoints")
    out = {}
    if os.path.isdir(d):
        for f in os.listdir(d):
            out[f[: -len(".txt")]] = [
                float(l) for l in open(os.path.join(d, f)) if l.strip()
            ]
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--svg", help="the scatter")
    ap.add_argument("--dumbbell", help="per design: reg2reg, WNS, floor")
    ap.add_argument("--ridgeline", help="per design: every endpoint")
    ap.add_argument("--overlay", help="every design's endpoints on one graph")
    a = ap.parse_args(argv)
    text, designs = report(a.results)
    sys.stdout.write(text)
    for path, draw in (
        (a.svg, lambda: svg(designs)),
        (a.dumbbell, lambda: dumbbell_svg(designs)),
        (a.ridgeline, lambda: ridgeline_svg(designs, load_endpoints(a.results))),
        (a.overlay, lambda: overlay_svg(designs, load_endpoints(a.results))),
    ):
        if path:
            with open(path, "w") as f:
                f.write(draw())


if __name__ == "__main__":
    main(sys.argv[1:])
