"""Format A/B comparison tables from probe JSON outputs with 2-sigma resolution."""

import json
import math
import os
import sys
from pathlib import Path


def mean(xs):
    return sum(xs) / len(xs)


def sample_std(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def compare_metric(stock_vals, added_vals):
    """Return (stock_mean, added_mean, delta, pct, two_sigma_pool, resolvable, resolved)."""
    k = min(len(stock_vals), len(added_vals))
    s_mean = mean(stock_vals)
    a_mean = mean(added_vals)
    delta = a_mean - s_mean
    pct = (100.0 * delta / abs(s_mean)) if s_mean != 0 else 0.0
    s_sd = sample_std(stock_vals)
    a_sd = sample_std(added_vals)
    pooled_sd = math.sqrt((s_sd**2 + a_sd**2) / 2.0)
    two_sigma = 2.0 * pooled_sd
    resolvable = two_sigma * math.sqrt(2.0 / k) if k >= 2 else 0.0
    resolved = abs(delta) > resolvable if k >= 2 else True
    return {
        "stock_mean": s_mean,
        "added_mean": a_mean,
        "delta": delta,
        "pct": pct,
        "two_sigma": two_sigma,
        "resolvable": resolvable,
        "resolved": resolved,
    }


def render_markdown(records):
    """Render Markdown summary tables for synth and grt probe JSON records."""
    by_stage_arm = {}
    for rec in records:
        key = (rec["stage"], rec["arm"])
        by_stage_arm.setdefault(key, []).append(rec)
    for vals in by_stage_arm.values():
        vals.sort(key=lambda r: r["seed"])

    lines = []
    if ("1_synth", "stock") in by_stage_arm and ("1_synth", "added") in by_stage_arm:
        s = by_stage_arm[("1_synth", "stock")][0]
        a = by_stage_arm[("1_synth", "added")][0]
        lines.append("### Synthesis (`1_synth`, shared across placement seeds)")
        lines.append("")
        lines.append("| Metric | Stock ASAP7 | +256 Added Cells | Delta |")
        lines.append("|---|---:|---:|---:|")
        for label, key, fmt in (
            ("Logical stdcells", "stdcell_count", "{:,.0f}"),
            ("Stdcell area (um^2)", "stdcell_area_um2", "{:,.1f}"),
            ("Buffers (`BUF*`)", "buf_count", "{:,.0f}"),
            ("Inverters (`INV*`)", "inv_count", "{:,.0f}"),
            ("Added-cell instances", "added_cell_count", "{:,.0f}"),
            ("Added-cell area (um^2)", "added_cell_area_um2", "{:,.1f}"),
        ):
            sv, av = s[key], a[key]
            dv = av - sv
            pct = f" ({100.0 * dv / sv:+.2f}%)" if sv else ""
            lines.append(
                f"| {label} | {fmt.format(sv)} | {fmt.format(av)} | {fmt.format(dv)}{pct} |"
            )
        lines.append("")

    if ("5_1_grt", "stock") in by_stage_arm and ("5_1_grt", "added") in by_stage_arm:
        s_list = by_stage_arm[("5_1_grt", "stock")]
        a_list = by_stage_arm[("5_1_grt", "added")]
        k = min(len(s_list), len(a_list))
        lines.append(
            f"### Global Route (`5_1_grt`, `k = {k}` placement seeds @ 473 ps SDC)"
        )
        lines.append("")
        lines.append(
            "| Metric | Stock (seeds) | +Added (seeds) | Delta (mean) | 2sigma | Resolvable | Verdict |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        metrics = [
            ("reg2reg min period (ps)", lambda r: r["reg2reg_min_period_ps"], "{:.1f}"),
            (
                "Stdcell flop-to-flop min period (ps)",
                lambda r: r.get("ff_only_min_period_ps", r["reg2reg_min_period_ps"]),
                "{:.1f}",
            ),
            ("reg2reg TNS (ns)", lambda r: r["reg2reg_tns_ns"], "{:.1f}"),
            (
                "Violating endpoints",
                lambda r: float(r["reg2reg_violating_endpoints"]),
                "{:,.0f}",
            ),
            ("Stdcell area (um^2)", lambda r: r["stdcell_area_um2"], "{:,.1f}"),
            ("Logical stdcells", lambda r: float(r["stdcell_count"]), "{:,.0f}"),
            ("Buffers (`BUF*`)", lambda r: float(r["buf_count"]), "{:,.0f}"),
            ("Inverters (`INV*`)", lambda r: float(r["inv_count"]), "{:,.0f}"),
            ("Added-cell instances", lambda r: float(r["added_cell_count"]), "{:,.0f}"),
            (
                "SLVT share (% stdcells)",
                lambda r: 100.0 * r["vt_counts"]["SLVT"] / max(1, r["stdcell_count"]),
                "{:.1f}",
            ),
            (
                "LVT share (% stdcells)",
                lambda r: 100.0 * r["vt_counts"]["LVT"] / max(1, r["stdcell_count"]),
                "{:.1f}",
            ),
            ("Guide wirelength (mm)", lambda r: r["guide_wl_um"] / 1000.0, "{:,.2f}"),
            (
                "Total power @ 473 ps (mW)",
                lambda r: r["report_power"]["Total"]["total"] * 1000.0,
                "{:.1f}",
            ),
            (
                "Leakage power (mW)",
                lambda r: r["report_power"]["Total"]["leakage"] * 1000.0,
                "{:.2f}",
            ),
        ]
        for label, fn, fmt in metrics:
            svs = [fn(r) for r in s_list]
            avs = [fn(r) for r in a_list]
            cmp = compare_metric(svs, avs)
            s_str = " / ".join(fmt.format(v) for v in svs)
            a_str = " / ".join(fmt.format(v) for v in avs)
            d_str = f"{cmp['delta']:+.2f} ({cmp['pct']:+.2f}%)"
            verdict = "resolved" if cmp["resolved"] else "did not resolve"
            lines.append(
                f"| {label} | {s_str} | {a_str} | {d_str} | "
                f"{cmp['two_sigma']:.2f} | {cmp['resolvable']:.2f} | {verdict} |"
            )
        lines.append("")

        # Top added stems from seed 1 at grt
        top_stems = list(a_list[0].get("added_by_stem", {}).items())[:15]
        if top_stems:
            lines.append("### Top Added Cell Families at Global Route (seed 1)")
            lines.append("")
            lines.append("| Stem | Instances |")
            lines.append("|---|---:|")
            for stem, cnt in top_stems:
                lines.append(f"| `{stem}` | {cnt:,d} |")
            lines.append("")

    return "\n".join(lines)


def _resolve(p):
    path = Path(p)
    if not path.is_absolute():
        bwd = os.environ.get("BUILD_WORKING_DIRECTORY")
        if bwd:
            path = Path(bwd) / path
    return path


def main(argv):
    if len(argv) < 2:
        print("usage: report.py <probe.json> [...] [--out report.md]", file=sys.stderr)
        return 2
    out_path = None
    paths = []
    i = 1
    while i < len(argv):
        if argv[i] == "--out":
            out_path = _resolve(argv[i + 1])
            i += 2
        else:
            paths.append(_resolve(argv[i]))
            i += 1
    records = [json.loads(p.read_text()) for p in paths]
    md = render_markdown(records)
    if out_path:
        out_path.write_text(md + "\n")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
