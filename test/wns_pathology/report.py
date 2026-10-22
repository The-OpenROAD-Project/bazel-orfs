"""The study's tables and figure, from whatever results/ holds.

  report.py <results dir> [--svg out.svg]

results/facts/<flow>.tsv is read.tcl's read of a flow's global route;
results/arms/<arm>_{fix,control}.tsv the fix arms' reads;
results/not_measured.json the flows that failed before timing or were left
out. A section with no data says "Not yet measured".
"""

import argparse
import json
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


def load(results):
    facts = os.path.join(results, "facts")
    if not os.path.isdir(facts) or not os.listdir(facts):
        raise SystemExit("no results in %s: run the campaign first" % results)
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
    out.append("## Flags\n")
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
                "`%s`" % stem,
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


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--svg")
    a = ap.parse_args(argv)
    text, designs = report(a.results)
    sys.stdout.write(text)
    if a.svg:
        with open(a.svg, "w") as f:
            f.write(svg(designs))


if __name__ == "__main__":
    main(sys.argv[1:])
