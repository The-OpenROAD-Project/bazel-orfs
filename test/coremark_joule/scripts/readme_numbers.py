#!/usr/bin/env python3
"""Render the README's measured numbers from results.json, and nothing else.

The paper went through three drafts whose numbers coexisted in the prose:
a boundary cost of "2.8x to 4.2x" in the abstract and "5.7x to 9.8x" two
paragraphs later, the same ratio quoted three ways in three sections.
results.json was the single source of truth for the plot, and the prose
had none. This module gives it one.

Two things are rendered:

- Table 1, verbatim. The README carries it between `<!-- table1 -->`
  and `<!-- /table1 -->` markers and readme_numbers_test asserts the
  block equals what this module renders.
- A dict of named facts -- every ratio the prose quotes -- each rendered
  to the digits the prose uses. The test asserts each rendered string
  appears in the README, so a number that changes in results.json fails
  the test until the sentence that quotes it is updated.

Usage:
    bazelisk run //test/coremark_joule/scripts:readme_numbers -- results.json
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_results  # noqa: E402

# Display names, and the order Table 1 lists the cores in: by
# CoreMark/MHz, ascending.
NAMES = {
    "serv": "SERV",
    "picorv32": "picorv32",
    "ibex": "ibex",
    "veer": "VeeR EH1",
}

# Numbers from a configuration the study no longer runs: the three
# cacheless cores measured with their memories outside the boundary
# (§5.1, Table 8). They are the "before" of the boundary correction and
# are not re-derivable from results.json, which pins only the current
# configuration. Kept here so the ratios quoted against them are still
# computed rather than typed.
# The same three cacheless cores, core only: how far their line
# overpredicts VeeR, and their f/P and power spreads. From the builds
# the study no longer runs; the boundary argument of §4.6 is measured
# against them.
CORE_ONLY_OVERPREDICTS = 15.2
CORE_ONLY_F_OVER_P_SPREAD = 1.89
CORE_ONLY_POWER_SPREAD = 1.15

CORE_ONLY_COREMARK_PER_JOULE = {
    "serv": 5190.0,
    "picorv32": 86024.0,
    "ibex": 277510.0,
}

MODEL_SWITCH_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "results", "model_switch.json"
)
SWITCH_BEGIN = "<!-- switch -->"
SWITCH_END = "<!-- /switch -->"

COMMODITY_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "results",
    "commodity_coremark.csv",
)


def model_switch_rows(path=MODEL_SWITCH_JSON):
    """§5.1's Table 8b rows: the memory model switched and nothing else."""
    with open(path) as f:
        return json.load(f)["rows"]


def switch_change_pct(row):
    return 100.0 * (
        row["scaler"]["coremark_per_joule"] / row["fakeram"]["coremark_per_joule"] - 1
    )


def render_switch_table(rows=None):
    """Table 8b: FakeRAM and scaler points side by side, same periods and floorplans."""
    rows = model_switch_rows() if rows is None else rows
    order = list(NAMES)
    rows = sorted(
        rows, key=lambda r: order.index(r["core"]) if r["core"] in order else 99
    )
    head = (
        "| core | power, FakeRAM | power, scaler | CoreMark/Joule, FakeRAM | "
        "CoreMark/Joule, scaler | change | macro share, scaler |"
    )
    lines = [head, "|---" * 7 + "|"]
    for r in rows:
        lines.append(
            "| {core} | {pf:.1f} mW | {ps:.1f} mW | {cf:,.0f} | {cs:,.0f} | {ch:+.0f} % | {ms:.0f} % |".format(
                core=NAMES.get(r["core"], r["core"]),
                pf=1e3 * r["fakeram"]["power_w"],
                ps=1e3 * r["scaler"]["power_w"],
                cf=r["fakeram"]["coremark_per_joule"],
                cs=r["scaler"]["coremark_per_joule"],
                ch=switch_change_pct(r),
                ms=100.0 * r["scaler"]["macro_power_w"] / r["scaler"]["power_w"],
            )
        )
    return "\n".join(lines)


def commodity_rows(path=COMMODITY_CSV):
    """§4.9's rows: CoreMark/s and the power that goes with it, per CPU."""
    with open(path) as f:
        rows = list(csv.DictReader(l for l in f if not l.startswith("#")))
    out = {}
    for r in rows:
        power = float(r["power_w"]) if r["power_w"] else None
        out[r["cpu"]] = {
            "class": r["class"],
            "coremark_per_s": float(r["iterations_per_s"]),
            "power_w": power,
            "power_kind": r["power_kind"],
            "coremark_per_joule": (
                float(r["iterations_per_s"]) / power if power else None
            ),
        }
    return out


TABLE1_BEGIN = "<!-- table1 -->"
TABLE1_END = "<!-- /table1 -->"
SEEDS_BEGIN = "<!-- seeds -->"
SEEDS_END = "<!-- /seeds -->"


def points_by_core(document):
    return {p["core"]: p for p in document["points"]}


def ordered(document):
    return sorted(document["points"], key=lambda p: p["coremark_per_mhz"])


def memory_inside(point):
    """The `boundary` field, minus the prefix and suffix every point shares."""
    text = point["boundary"]
    prefix = "core + L1: "
    suffix = ", both hardened"
    if text.startswith(prefix):
        text = text[len(prefix) :]
    if text.endswith(suffix):
        text = text[: -len(suffix)]
    return text


def has_seeds(document):
    """True when every point carries a placement-seed ensemble (§5.13)."""
    return all("coremark_per_joule_2sigma" in p for p in document["points"])


def has_split(document):
    """True when every point carries the dynamic/leakage split."""
    return all(
        "dynamic_power_w" in p and "leakage_power_w" in p for p in document["points"]
    )


def render_table1(document):
    split = has_split(document)
    head = "| core | ISA | CoreMark/MHz | cycles/iter | f (MHz) | P (SAIF) "
    if split:
        head += "| dynamic | leakage "
    head += "| CoreMark/Joule | memory inside the boundary |"
    seeds = has_seeds(document)
    if seeds:
        head += " 2σ over seeds |"
    lines = [head, "|---" * ((10 if split else 8) + (1 if seeds else 0)) + "|"]
    for p in ordered(document):
        row = "| {name} | {isa} | {cmmhz:.4f} | {cycles:,} | {f:.1f} | {p:.1f} mW ".format(
            name=NAMES[p["core"]],
            isa=p["isa"],
            cmmhz=p["coremark_per_mhz"],
            cycles=p["cycles_per_iteration"],
            f=p["frequency_mhz"],
            p=p["power_w"] * 1e3,
        )
        if split:
            row += "| {dyn:.1f} mW | {leak:.2f} mW ".format(
                dyn=p["dynamic_power_w"] * 1e3, leak=p["leakage_power_w"] * 1e3
            )
        row += "| {cmj:,.0f} | {mem} |".format(
            cmj=p["coremark_per_joule"], mem=memory_inside(p)
        )
        if seeds:
            row += " ±{sig:,.0f} ({n}) |".format(
                sig=p["coremark_per_joule_2sigma"], n=p["seeds"]
            )
        lines.append(row)
    return "\n".join(lines)


def _ratio(a, b, digits):
    return "{:.{d}f}x".format(a / b, d=digits)


def seed_2sigma_pct(point):
    """2σ of a point's placement-seed ensemble as a percentage of the point."""
    return 100.0 * point["coremark_per_joule_2sigma"] / point["coremark_per_joule"]


def render_seed_table(document):
    """§5.13's table: every draw of every core, and 2σ over the five.

    One column per draw, labelled by the seed it was placed at (the
    design's own draw first), then 2σ in CoreMark/Joule and as a share of
    the pinned point, and 2σ of power. A point with no ensemble renders
    as not yet measured.
    """
    if not has_seeds(document):
        return "Not yet measured."
    labels = None
    rows = []
    order = list(NAMES)
    for p in sorted(
        document["points"],
        key=lambda p: order.index(p["core"]) if p["core"] in order else 99,
    ):
        samples = p["seed_samples"]
        these = [_seed_heading(x["seed"]) for x in samples]
        if labels is None:
            labels = these
        elif these != labels:
            raise SystemExit(
                "readme_numbers: {} was drawn at seeds {}, others at {}".format(
                    p["core"], these, labels
                )
            )
        rows.append(
            "| {core} | {draws} | ±{sig:,.0f} | {pct:.1f} % | ±{pw:.2f} |".format(
                core=NAMES.get(p["core"], p["core"]),
                draws=" | ".join(
                    "{:,.0f}".format(x["coremark_per_joule"]) for x in samples
                ),
                sig=p["coremark_per_joule_2sigma"],
                pct=seed_2sigma_pct(p),
                pw=1e3 * p["power_2sigma_w"],
            )
        )
    head = (
        "| Core | "
        + " | ".join(labels)
        + " | 2σ CoreMark/J | 2σ / point | 2σ power (mW) |"
    )
    return "\n".join([head, "|---" * (len(labels) + 4) + "|"] + rows)


TABLE7_BEGIN = "<!-- table7 -->"
TABLE7_END = "<!-- /table7 -->"
TABLE8_BEGIN = "<!-- table8 -->"
TABLE8_END = "<!-- /table8 -->"
GROUPS = ("Clock", "Sequential", "Combinational", "Macro")


def render_table7(document):
    """§4.7: report_power's cell-kind groups per point, and their shares."""
    head = "| core | total | Clock | Sequential | Combinational | **Macro** | logic (all but macro) |"
    lines = [head, "|---" * 7 + "|"]
    for p in document["points"]:
        g = p["power_groups_w"]
        total = p["power_w"]
        cells = [
            "{:.2f} ({:.1f} %)".format(1e3 * g[k], 100.0 * g[k] / total) for k in GROUPS
        ]
        cells[-1] = "**" + cells[-1] + "**"
        logic = total - g["Macro"]
        lines.append(
            "| {} | **{:.2f} mW** | {} | {:.2f} ({:.1f} %) |".format(
                NAMES[p["core"]],
                1e3 * total,
                " | ".join(cells),
                1e3 * logic,
                100.0 * logic / total,
            )
        )
    return "\n".join(lines)


def render_table8(document):
    """§5.1: each core with its memory outside the boundary and inside it."""
    by = points_by_core(document)
    head = "| core | CoreMark/MHz | CoreMark/Joule, core-only | CoreMark/Joule, core + L1 | factor |"
    lines = [head, "|---" * 5 + "|"]
    for p in document["points"]:
        c = p["core"]
        inside = p["coremark_per_joule"]
        if c in CORE_ONLY_COREMARK_PER_JOULE:
            before = CORE_ONLY_COREMARK_PER_JOULE[c]
            lines.append(
                "| {} | {:.4f} | {:,.0f} | **{:,.0f}** | {:.2f}x |".format(
                    NAMES[c], p["coremark_per_mhz"], before, inside, before / inside
                )
            )
        else:
            lines.append(
                "| {} | {:.4f} | {:,.0f} | {:,.0f} | 1.00x (already met) |".format(
                    NAMES[c], p["coremark_per_mhz"], inside, inside
                )
            )
    return "\n".join(lines)


def _seed_heading(label):
    return "own draw" if label == "own" else "seed " + label


def facts(document):
    """Every number the prose quotes, rendered to the digits it uses.

    Keys name the sentence's subject; values are the exact substring the
    README must contain. A fact whose wording moves is edited here and
    in the README together, which is the point.
    """
    by = points_by_core(document)
    pts = document["points"]
    cmj = {c: p["coremark_per_joule"] for c, p in by.items()}
    cmmhz = {c: p["coremark_per_mhz"] for c, p in by.items()}
    power = {c: p["power_w"] for c, p in by.items()}
    vectorless = {c: p["vectorless_power_w"] for c, p in by.items()}
    lit = [l["coremark_per_joule"] for l in document["literature"]]

    out = {}
    out["dateline"] = "As of {}".format(
        document["provenance"]["uniqueness"]["as_of_text"]
    )
    out["coremark_per_mhz_span"] = "a factor of {:.0f} in CoreMark/MHz".format(
        max(cmmhz.values()) / min(cmmhz.values())
    )
    out["coremark_per_mhz_span_x"] = "{:.0f}x in CoreMark/MHz".format(
        max(cmmhz.values()) / min(cmmhz.values())
    )
    out["coremark_per_joule_span"] = "CoreMark/Joule spans a factor of {:.0f}".format(
        max(cmj.values()) / min(cmj.values())
    )
    out["ibex_over_veer"] = _ratio(cmj["ibex"], cmj["veer"], 2)
    out["ibex_over_veer_core_only"] = _ratio(
        CORE_ONLY_COREMARK_PER_JOULE["ibex"], cmj["veer"], 2
    )
    out["veer_over_ibex_core_only_cmj"] = _ratio(
        cmj["veer"], CORE_ONLY_COREMARK_PER_JOULE["ibex"], 2
    )
    out["veer_over_ibex_perf"] = _ratio(cmmhz["veer"], cmmhz["ibex"], 2)
    out["ibex_over_veer_perf"] = _ratio(cmmhz["ibex"], cmmhz["veer"], 2)
    out["veer_over_ibex_cmj"] = _ratio(cmj["veer"], cmj["ibex"], 2)
    out["veer_over_ibex_power"] = _ratio(power["veer"], power["ibex"], 2)
    out["veer_vs_literature"] = "{} to {}".format(
        _ratio(cmj["veer"], max(lit), 2), _ratio(cmj["veer"], min(lit), 2)
    )
    out["ibex_vs_literature"] = _ratio(cmj["ibex"], max(lit), 1)
    for core, before in CORE_ONLY_COREMARK_PER_JOULE.items():
        out["boundary_factor_" + core] = _ratio(before, cmj[core], 2)
    factors = [before / cmj[c] for c, before in CORE_ONLY_COREMARK_PER_JOULE.items()]
    out["boundary_factor_range"] = "between {:.1f}x and {:.1f}x".format(
        min(factors), max(factors)
    )
    for core in by:
        out["vectorless_over_measured_" + core] = _ratio(
            vectorless[core], power[core], 2
        )
    # A vectorless comparison of ibex and VeeR: how close it would put them.
    vl_cmj = {c: cmmhz[c] * by[c]["frequency_mhz"] * 1e6 / vectorless[c] for c in by}
    out["vectorless_ibex_over_veer"] = _ratio(vl_cmj["ibex"], vl_cmj["veer"], 2)
    # §4.9: the commodity ladder, measured package power where the run logged it.
    c = commodity_rows()
    epyc = c["AMD EPYC 9654"]["coremark_per_joule"]
    out["epyc_9654_over_7950x"] = _ratio(
        epyc, c["AMD Ryzen 9 7950X"]["coremark_per_joule"], 2
    )
    out["xeon_8490h_over_13900k"] = _ratio(
        c["Intel Xeon Platinum 8490H"]["coremark_per_joule"],
        c["Intel Core i9-13900K"]["coremark_per_joule"],
        2,
    )
    out["ryzen_7900_over_7900x"] = _ratio(
        c["AMD Ryzen 9 7900 (65 W)"]["coremark_per_joule"],
        c["AMD Ryzen 9 7900X"]["coremark_per_joule"],
        2,
    )
    best = max(
        v["coremark_per_joule"]
        for v in c.values()
        if v["coremark_per_joule"] and v["power_kind"] == "measured"
    )
    out["ibex_over_best_package"] = _ratio(cmj["ibex"], best, 1)
    out["veer_over_best_package"] = _ratio(cmj["veer"], best, 1)
    out["best_package_over_serv"] = _ratio(best, cmj["serv"], 1)
    # §4.6: the fit, from fit_results.py on the same points.
    fit = fit_results.figures(pts)
    out["fit_overpredicts"] = "{:.2f}x".format(fit["overpredicts_compliant_by"])
    out["fit_f_over_p_spread"] = "{:.2f}x".format(fit["f_over_p_spread_cacheless"])
    out["fit_power_spread"] = "{:.2f}x".format(fit["power_spread_cacheless"])
    out["boundary_share_of_error"] = "took {:.0f} % out of the disagreement".format(
        100.0 * (1 - fit["overpredicts_compliant_by"] / CORE_ONLY_OVERPREDICTS)
    )
    # §4.7: the macro column and the logic under it.
    share = {c: 100.0 * p["macro_power_w"] / p["power_w"] for c, p in by.items()}
    out["macro_share_range"] = "{:.0f} to {:.0f} %".format(
        min(share.values()), max(share.values())
    )
    out["macro_share_ends"] = "{:.1f} % of SERV down to {:.1f} % of ibex".format(
        share["serv"], share["ibex"]
    )
    over = {
        c: p["macro_power_w"] / (p["power_w"] - p["macro_power_w"])
        for c, p in by.items()
        if c != "veer"
    }
    out["macro_over_logic_range"] = "between {:.1f} and {:.1f} times".format(
        min(over.values()), max(over.values())
    )
    g = {c: p["power_groups_w"] for c, p in by.items()}
    state = {c: g[c]["Clock"] + g[c]["Sequential"] for c in by if c != "veer"}
    out["state_power_range"] = "{:.1f} to {:.1f} mW".format(
        1e3 * min(state.values()), 1e3 * max(state.values())
    )
    comb = {c: g[c]["Combinational"] for c in by if c != "veer"}
    out["combinational_range"] = "{:.2f}--{:.2f} mW".format(
        1e3 * min(comb.values()), 1e3 * max(comb.values())
    )
    fp = {c: by[c]["frequency_mhz"] / (1e3 * power[c]) for c in by if c != "veer"}
    out["f_over_p_spread"] = "{:.2f}x".format(max(fp.values()) / min(fp.values()))
    out["veer_clock_mw"] = "{:.1f} mW".format(1e3 * g["veer"]["Clock"])
    out["veer_over_ibex_clock"] = _ratio(g["veer"]["Clock"], g["ibex"]["Clock"], 1)
    logic = {c: power[c] - by[c]["macro_power_w"] for c in by}
    out["veer_logic_mw"] = "{:.1f} mW".format(1e3 * logic["veer"])
    out["ibex_logic_mw"] = "{:.1f} mW".format(1e3 * logic["ibex"])
    out["veer_over_ibex_logic"] = _ratio(logic["veer"], logic["ibex"], 1)
    out["veer_macro_share"] = "{:.0f} %".format(share["veer"])
    # §5.1, Table 8b: what the memory model switch alone did.
    switch = {r["core"]: switch_change_pct(r) for r in model_switch_rows()}
    cacheless = [-switch[c] for c in ("serv", "picorv32", "ibex")]
    out["switch_cacheless_fall"] = "fell together, by {:.0f} to {:.0f} %".format(
        min(cacheless), max(cacheless)
    )
    out["switch_veer_fall"] = "VeeR fell {:.0f} %".format(-switch["veer"])
    # §5.13: the one gap in Table 1 the seed spread reaches.
    gap = 100.0 * abs(cmj["veer"] / cmj["picorv32"] - 1)
    out["veer_picorv32_gap"] = (
        "VeeR to picorv32, is {:.1f} % of the smaller point".format(gap)
    )
    if has_seeds(document):
        worst = max(pts, key=seed_2sigma_pct)
        out["largest_seed_2sigma"] = "largest 2σ is {:.1f} % of its point".format(
            seed_2sigma_pct(worst)
        )
        for p in pts:
            out["seed_2sigma_" + p["core"]] = "{} {:.1f} %".format(
                NAMES[p["core"]], seed_2sigma_pct(p)
            )
    return out


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", help="results.json")
    args = parser.parse_args(argv[1:])
    with open(args.results) as f:
        document = json.load(f)
    print(TABLE1_BEGIN)
    print(render_table1(document))
    print(TABLE1_END)
    print()
    print(SEEDS_BEGIN)
    print(render_seed_table(document))
    print(SEEDS_END)
    print()
    for begin, end, table in (
        (TABLE7_BEGIN, TABLE7_END, render_table7(document)),
        (TABLE8_BEGIN, TABLE8_END, render_table8(document)),
    ):
        print(begin)
        print(table)
        print(end)
        print()
    print(SWITCH_BEGIN)
    print(render_switch_table())
    print(SWITCH_END)
    print()
    for key, value in facts(document).items():
        print("{:36s} {}".format(key, value))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
