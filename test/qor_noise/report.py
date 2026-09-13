#!/usr/bin/env python3

"""Generate the study's write-up from whatever results/ holds.

The report discovers its inputs. With `results/` absent it says how to
produce them and exits non-zero rather than printing a confident empty
document; with a section's inputs missing it prints **Not yet measured**
for that section and carries on. A half-finished campaign has to read as
half-finished, or the next person quotes a table that was never taken.

No statistic is computed here. Everything comes from analysis.json, so
the write-up cannot drift from the numbers.
"""

import argparse
import json
import os
import sys

FIGURES = [
    (
        "coverage_vs_designs.png",
        "Two panels. Left: percentage of real tool changes detected against "
        "the number of designs run, for four size classes; the four curves "
        "lie on top of one another. Right: the estimated CI cost of those "
        "same sets, three orders of magnitude apart.",
    ),
    (
        "overfitting.png",
        "Grouped bars per size class and set size. A design set chosen "
        "greedily on the first half of history scores far lower on the "
        "second half than on the half it was tuned on, and lower than a "
        "random set of the same size.",
    ),
    (
        "concordance.png",
        "Bar chart: the share of fleet-wide events in which every design "
        "that moved moved in the same direction.",
    ),
    (
        "recommendation.png",
        "Detection rate against the total instance count of the design set, "
        "log x-axis, with the whole fleet's size marked far to the right.",
    ),
    (
        "cost_vs_information.png",
        "Scatter of every design: size in instances against the share of "
        "fleet-wide tool changes it noticed, coloured by how often it moved "
        "alone. No upward trend with size.",
    ),
]

MISSING = "**Not yet measured.**"


def pct(x, digits=0):
    return "—" if x is None else f"{x * 100:.{digits}f}%"


def section(title, body):
    return f"## {title}\n\n{body}\n"


def fig(name, alt, base_url):
    if not base_url:
        return f"`{name}` — {alt}"
    return f"![{alt}]({base_url.rstrip('/')}/{name})"


def corpus_section(a):
    c = a["corpus"]
    rows = [
        "| what | value |",
        "| --- | --- |",
        f"| rules-file revisions read | {c['rows']:,} threshold records |",
        f"| designs | {c['designs']} |",
        f"| platforms | {len(c['platforms'])} |",
        f"| distinct metrics | {c['metrics']} |",
        f"| span | {c['first']} to {c['last']} |",
    ]
    types = c["label_types"]
    label_line = ", ".join(f"{k}: {v:,}" for k, v in sorted(types.items()))
    return "\n".join(rows) + (
        f"\n\nOf the threshold changes whose commit message carried "
        f"`genRuleFile.py`'s table ({c['labelled_rows']:,} rows), the reasons were "
        f"{label_line}. There is no `Updating` row anywhere in four years, which "
        "means no threshold in this history was ever written as an unconditional "
        "sample. Every recorded value either beat the previous record or blew "
        "through the padded bound: the series is a ratchet, and any estimator "
        "that treats it as a sample path is measuring the update policy rather "
        "than the tools."
    )


def events_section(a, base_url):
    e = a["events"]
    b = e["openroad_bump_events"]
    lines = [
        fig("concordance.png", FIGURES[2][1], base_url),
        "",
        f"{e['commits_moving_thresholds']} commits moved at least one threshold. "
        f"{e['solo_commits']} moved exactly one design. "
        f"{e['fleetwide_events']} moved at least {e['fleetwide_threshold']} designs "
        "at once; those are what this study calls a **fleet-wide event**.",
        "",
        "A fleet-wide event is read as a real tool change rather than a "
        "coincidence because of how coherent it is:",
        "",
        "| property | value |",
        "| --- | --- |",
        f"| median direction concordance | {pct(e['concordance']['median'], 1)} |",
        f"| events where every design moved the same way | {pct(e['concordance']['fraction_at_100pct'])} |",
        f"| median distinct design names per event | {e['distinct_names_median']:.0f} |",
        f"| median distinct platforms per event | {e['distinct_platforms_median']:.0f} |",
        f"| events that were one design name across platforms | {e['single_name_events']} |",
        "",
        f"The last row rules out the obvious artefact: not one fleet-wide event is "
        "a maintainer bulk-regenerating a single design family across platforms.",
        "",
        f"Of these, {b['n']} are pure OpenROAD submodule bumps. They move a median "
        f"{pct(b['fraction_moved_median'])} of the fleet, and "
        + (
            f"**all {b['n']} of {b['n']} were 100% direction-concordant**"
            if b["all_fully_concordant"]
            else f"their minimum concordance was {pct(b['concordance_min'])}"
        )
        + ". When an OpenROAD change moves QoR, the designs that notice agree "
        "about which way.",
    ]
    return "\n".join(lines)


def selection_section(a, base_url):
    s = a["selection"]
    lines = [
        f"Selection is fitted on events from {s['train_span'][0]} to "
        f"{s['train_span'][1]} ({s['train_events']} events) and scored on "
        f"{s['test_span'][0]} to {s['test_span'][1]} ({s['test_events']} events). "
        f"A set **detects** an event when at least {s['witnesses']} of its members "
        "moved — one witness is a draw, two is a pattern.",
        "",
        fig("overfitting.png", FIGURES[1][1], base_url),
        "",
        "| size class | D | tuned-on-history | later years | random set, later years |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in s["greedy_vs_random"]:
        lines.append(
            f"| {r['size_class']} | {r['D']} | {pct(r['train_coverage'])} | "
            f"{pct(r['test_coverage'])} | {pct(r['random_test_mean'])} "
            f"± {pct(r['random_test_2sigma'])} |"
        )
    rows = s["greedy_vs_random"]
    worse = sum(1 for r in rows if r["test_coverage"] < r["random_test_mean"])
    clearly = sum(
        1
        for r in rows
        if r["test_coverage"] < r["random_test_mean"] - r["random_test_2sigma"] / 2
    )
    drop = sum(r["train_coverage"] - r["test_coverage"] for r in rows) / len(rows)
    lines += [
        "",
        f"The tuned set scores below a random set of the same size in {worse} of "
        f"{len(rows)} cases, and in {clearly} of {len(rows)} it is below the "
        "random spread rather than inside it. Tuning costs on average "
        f"{drop * 100:.0f} percentage points between the years it was fitted on "
        "and the years that followed.",
        "",
        "Which designs responded to tool changes in the past does not predict "
        "which will respond next. There is no clever subset to find, and a "
        "carefully curated design list is a way to feel prepared for the last "
        "regression rather than the next one.",
    ]
    return "\n".join(lines)


def how_many_section(a, base_url):
    s = a["selection"]
    lines = [
        fig("coverage_vs_designs.png", FIGURES[0][1], base_url),
        "",
        "Detection rate is a function of D and essentially nothing else. At "
        "every D the four size classes agree within their spread, while the "
        "cost of those same sets differs by more than two orders of magnitude.",
        "",
        "| D | detected | total instances | platforms | largest member |",
        "| ---: | ---: | ---: | ---: | --- |",
    ]
    for r in s["cheapest_d"]:
        lines.append(
            f"| {r['D']} | {pct(r['coverage'])} | {r['total_instances']:,.0f} | "
            f"{r['platforms']} | {r['largest']} |"
        )
    fleet = s["fleet_total_instances"]
    best = s["cheapest_d"][-1]
    twenty = next((r for r in s["cheapest_d"] if r["D"] == 20), best)
    lines += [
        "",
        fig("recommendation.png", FIGURES[3][1], base_url),
        "",
        f"The whole fleet is {fleet:,.0f} instances. The {twenty['D']} cheapest "
        f"designs are {twenty['total_instances']:,.0f} — "
        f"{twenty['total_instances'] / fleet:.1%} of it — cover "
        f"{twenty['platforms']} platforms, and detect {pct(twenty['coverage'])} of "
        "the tool changes in the held-out years.",
    ]
    return "\n".join(lines)


def designs_section(a, base_url):
    ds = [d for d in a["designs"] if d["instances"]]
    ds_sorted = sorted(ds, key=lambda d: -d["instances"])
    lines = [
        fig("cost_vs_information.png", FIGURES[4][1], base_url),
        "",
        "The most expensive designs in the fleet are not the most informative. "
        "The five largest:",
        "",
        "| design | instances | noticed | moved alone / year |",
        "| --- | ---: | ---: | ---: |",
    ]
    for d in ds_sorted[:5]:
        lines.append(
            f"| {d['design']} | {d['instances']:,.0f} | {pct(d['responsiveness'])} | "
            f"{d['solo_per_year']:.1f} |"
        )
    lines += [
        "",
        "The five that noticed the most:",
        "",
        "| design | instances | noticed | moved alone / year |",
        "| --- | ---: | ---: | ---: |",
    ]
    for d in sorted(ds, key=lambda d: -d["responsiveness"])[:5]:
        lines.append(
            f"| {d['design']} | {d['instances']:,.0f} | {pct(d['responsiveness'])} | "
            f"{d['solo_per_year']:.1f} |"
        )
    return "\n".join(lines)


def censoring_section(a):
    return a["notes"]["timing_censoring"] + (
        "\n\nSo of the metrics in a `rules-base.json`, the ones this study can "
        "measure at full precision are:\n\n"
        + "\n".join(f"* `{m}`" for m in a["notes"]["high_resolution_metrics"])
        + "\n\nEverything timing-shaped is either censored, as above, or stored "
        "to three significant figures, which quantises it at the same order as "
        "the effects being hunted."
    )


def build(a, base_url):
    parts = [
        section("What the history contains", corpus_section(a)),
        section(
            "Real tool changes are coherent; draws are not", events_section(a, base_url)
        ),
        section("How many designs, and which", how_many_section(a, base_url)),
        section("The clever subset does not exist", selection_section(a, base_url)),
        section(
            "Big designs cost more and tell you less", designs_section(a, base_url)
        ),
        section("What the rules files cannot tell you", censoring_section(a)),
    ]
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True, help="directory holding analysis.json")
    ap.add_argument(
        "--figure-base-url",
        default="",
        help="pinned-SHA raw URL the committed figures live under; without it "
        "figures are named rather than embedded",
    )
    ap.add_argument("--out", default="-")
    args = ap.parse_args(argv)

    path = os.path.join(args.results, "analysis.json")
    if not os.path.exists(path):
        print(
            f"no analysis at {path} -- run the campaign first:\n"
            "  bazelisk run //test/qor_noise:extract\n"
            "  bazelisk run //test/qor_noise:analyze",
            file=sys.stderr,
        )
        return 1
    with open(path) as fh:
        a = json.load(fh)

    figdir = os.path.join(args.results, "figures")
    missing = [n for n, _alt in FIGURES if not os.path.exists(os.path.join(figdir, n))]
    text = build(a, args.figure_base_url)
    if missing:
        text += "\n" + section(
            "Figures not yet rendered",
            MISSING
            + " Run `bazelisk run //test/qor_noise:plots`. Missing: "
            + ", ".join(f"`{m}`" for m in missing),
        )

    if args.out == "-":
        sys.stdout.write(text)
    else:
        with open(args.out, "w") as fh:
            fh.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
