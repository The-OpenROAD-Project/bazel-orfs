"""The potential report as a page: findings, what-ifs, calibration.

Reads tier 1 findings (detect.py), tier 2 what-ifs (whatif.py) and the
calibration rows (calibrate/regfile_read.jsonl), and writes one markdown
page with a verdict per structure:

- rtl:        a what-if says rewriting the RTL buys at least the
              threshold in cells or in logic levels;
- flow:       a measured structure is more than `--flow-gap` times the
              literature's number for its configuration;
- expected:   within the literature's band;
- unmeasured: a shape found and no number for it yet.

A verdict is a recommendation; the flow's own period decides.
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect  # noqa: E402
import models  # noqa: E402

RTL_CELLS_PCT = 20.0
# The calibration spec built to the literature row's configuration.
LIT_SPEC = "alpha80x64"


def load_findings(paths):
    out = {}
    for p in paths:
        top = os.path.basename(p).replace("_potential_findings.json", "")
        with open(p) as f:
            out[top] = detect.dedup(json.load(f))
    return out


def load_whatifs(paths):
    out = {}
    for p in paths:
        with open(p) as f:
            w = json.load(f)
        out[w["top"]] = w
    return out


def whatif_verdict(w):
    area = w.get("area", {})
    delay = w.get("delay", {})
    cells = area.get("cells_saved_pct")
    levels = delay.get("levels_saved")
    if cells is not None and cells >= RTL_CELLS_PCT:
        return "rtl"
    if levels is not None and levels >= 1:
        return "rtl"
    return "expected"


def finding_line(f):
    what = f.get("leaf") or f.get("stem") or ""
    return "| %s | %s | %s | %s | %s |" % (
        f["kind"],
        detect.base_name(f["module"]),
        what,
        f.get("n", ""),
        f["estimate"].replace("|", "/"),
    )


def rank(f):
    return -(
        f.get("gates_today")
        or f.get("key_bit_loads")
        or f.get("bits")
        or f.get("n", 0) * f.get("leaf_cells", 0)
        or 0
    )


def render(findings, whatifs, calibration, fo4_ps, flow_gap):
    lines = ["# Potential report", ""]
    lines += ["FO4 of the library the flow times with: %.2f ps." % fo4_ps, ""]

    lines += ["## Verdicts", "", "| module | verdict | why |", "|---|---|---|"]
    for top in sorted(set(findings) | set(whatifs)):
        w = whatifs.get(top)
        if w:
            a, d = w.get("area", {}), w.get("delay", {})
            why = (
                "flattening %s: area-mapped cells %s -> %s (%s %%), delay-mapped levels %s -> %s"
                % (
                    ", ".join(w["leaf"]),
                    a.get("kept", {}).get("cells"),
                    a.get("flattened", {}).get("cells"),
                    a.get("cells_saved_pct"),
                    d.get("kept", {}).get("levels"),
                    d.get("flattened", {}).get("levels"),
                )
            )
            lines.append("| %s | %s | %s |" % (top, whatif_verdict(w), why))
        else:
            kinds = sorted({f["kind"] for f in findings.get(top, [])})
            lines.append(
                "| %s | unmeasured | shapes: %s |" % (top, ", ".join(kinds) or "none")
            )
    lines.append("")

    if calibration:
        lines += [
            "## Calibration: generated register files against the literature",
            "",
            "| spec | as generated | buffered | after repair_timing | FO4 | literature FO4 | ratio | verdict |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        lit = models.by_name("register file")[0]
        for c in calibration:
            fo4 = c["read_ps"] / fo4_ps
            # Only the configuration the literature row describes gets a
            # ratio; the rest are context.
            if c["spec"] == LIT_SPEC:
                ratio = "%.2f" % (fo4 / lit["fo4"])
                verdict = "flow" if fo4 / lit["fo4"] > flow_gap else "expected"
                lit_fo4 = "%.1f" % lit["fo4"]
            else:
                ratio, verdict, lit_fo4 = "", "no model", ""
            lines.append(
                "| %s | %.0f ps | %.0f ps | %.0f ps | %.1f | %s | %s | %s |"
                % (
                    c["spec"],
                    c["raw_read_ps"],
                    c["buffered_read_ps"],
                    c["read_ps"],
                    fo4,
                    lit_fo4,
                    ratio,
                    verdict,
                )
            )
        lines += [
            "",
            "Literature: %s, %s; %s." % (lit["name"], lit["source"], lit["scope"]),
            "",
        ]

    lines += [
        "## Literature rows",
        "",
        "| structure | FO4 | source | scope |",
        "|---|---:|---|---|",
    ]
    for m in models.MODELS:
        lines.append(
            "| %s | %.1f | %s | %s |" % (m["name"], m["fo4"], m["source"], m["scope"])
        )
    lines.append("")

    for top in sorted(findings):
        fs = sorted(findings[top], key=rank)
        lines += [
            "## %s: %d shapes" % (top, len(fs)),
            "",
            "| kind | module | leaf / stem | N | estimate |",
            "|---|---|---|---:|---|",
        ]
        lines += [finding_line(f) for f in fs[:12]]
        if len(fs) > 12:
            lines.append("| ... | %d more | | | |" % (len(fs) - 12))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--findings", nargs="*", default=[])
    p.add_argument("--whatif", nargs="*", default=[])
    p.add_argument("--calibration")
    p.add_argument(
        "--fo4-ps",
        type=float,
        required=True,
        help="FO4 of the library the flow times with",
    )
    p.add_argument("--flow-gap", type=float, default=2.0)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    calibration = []
    if args.calibration:
        with open(args.calibration) as f:
            calibration = [json.loads(l) for l in f if l.strip()]
    text = render(
        load_findings(args.findings),
        load_whatifs(args.whatif),
        calibration,
        args.fo4_ps,
        args.flow_gap,
    )
    with open(args.out, "w") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    sys.exit(main())
