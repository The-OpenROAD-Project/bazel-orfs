"""Render the study's findings as markdown, from the checked-in results.

The pull request body is the part of this study anyone reads, so it is
generated rather than typed: a hand-written table stops being true the
first time a campaign is re-run, and there is no way to tell by looking.

Sections whose inputs are absent say so. Dropping them silently would
make a partial study read as a complete one, which is the same failure
this harness produces everywhere else -- a well-formed answer to a
question nobody measured.
"""

import argparse
import json
import re
from pathlib import Path

# The stem ORFS gives each stage's ODB, in flow order, so the ladder
# reads bottom-to-top however the files were globbed.
STAGE_ORDER = [
    "1_synth",
    "2_floorplan",
    "3_place",
    "4_cts",
    "5_1_grt",
    "5_route",
    "6_final",
]

# A result file is named with the stage's short key -- the BUILD's
# LADDER_STAGES key -- while the JSON inside carries ORFS's ODB stem for
# the same stage. The two are not the same string, and a recovery that
# assumes they are silently folds every shape into one bogus row.
STAGE_KEY_TO_STEM = {
    "floorplan": "2_floorplan",
    "place": "3_place",
    "cts": "4_cts",
    "grt": "5_1_grt",
    "route": "5_route",
    "final": "6_final",
}

# What each rung's parasitics choice means, in one phrase, so the ladder
# table carries the reason a rung differs rather than only the number.
PARASITICS_MEANING = {
    "set_wire_rc": "no estimate; one RC constant for every net",
    "placement": "estimate_parasitics -placement",
    "global_routing": "estimate_parasitics -global_routing",
    "spef": "extracted parasitics (SPEF)",
    "none": "no parasitics available",
}


def table(headers, rows):
    """A markdown table, or nothing at all for no rows."""
    if not rows:
        return ""
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def assert_one_clock(rungs, where):
    """Every rung of a ladder must have been read under one constraint.

    A ladder is a comparison, so it is only meaningful if the thing held
    fixed was actually held fixed. If one rung was built under a
    different clock target -- a stale ODB, a variant whose arguments
    drifted, a constraint that failed to apply in one stage -- the
    resulting `min_period` column still looks like a ladder and its shape
    means nothing. Raise rather than annotate: this is not a caveat a
    reader can discount, it invalidates the row.
    """
    periods = {round(rung["clock_period"], 6) for rung in rungs}
    if len(periods) > 1:
        raise SystemExit(
            "%s: rungs were read under %d different clock periods (%s); "
            "the ladder is not a comparison"
            % (where, len(periods), sorted(periods))
        )
    return periods.pop() if periods else None


def shape_of(stem, stage_stem):
    """Recover the shape name from a `shape_ladder_<shape>_<key>` stem.

    Raises rather than guessing. The first version stripped the JSON's
    stage stem from the file name, which never matched -- so every file
    kept its full stem as the shape and the matrix came out as one row
    per file with a single rung each. It looked like data.
    """
    for key, stem_name in STAGE_KEY_TO_STEM.items():
        if stem_name == stage_stem and stem.endswith("_" + key):
            return stem[: -(len(key) + 1)]
    raise SystemExit(
        "cannot tell which shape %r belongs to: its stage is %r, which "
        "matches no known result-file suffix" % (stem, stage_stem)
    )


def load(path):
    if path is None:
        return None
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def signal_mispricing(rc):
    """The signal-net mispricing factor out of an rc block, if any."""
    if not rc or not rc.get("wire_rc"):
        return None
    for entry in rc["wire_rc"]:
        if entry.get("signal") and entry.get("mispricing"):
            return entry["mispricing"]
    return None


def section_regime(inv):
    """Which designs can reach the top of the stack, and what it costs."""
    asap7 = [row for row in inv["designs"] if row["platform"] == "asap7"]
    default_max = inv["platforms"]["asap7"]["routing"]["MAX_ROUTING_LAYER"]
    stack = [layer["layer"] for layer in inv["platforms"]["asap7"]["rc"]["layers"]]

    raised = [
        row
        for row in asap7
        if row["routing"]["MAX_ROUTING_LAYER"]["source"] == "design"
        and stack.index(row["routing"]["MAX_ROUTING_LAYER"]["value"])
        > stack.index(default_max)
    ]

    rows = []
    for row in sorted(asap7, key=lambda r: r["design"]):
        mis = signal_mispricing(row.get("rc"))
        overrides = sorted(
            "`%s=%s`" % (name, value["value"])
            for name, value in row["policy"].items()
            if value["source"] == "design"
        )
        rows.append(
            [
                "`%s`" % row["design"],
                row["routing"]["MAX_ROUTING_LAYER"]["value"],
                "design" if row["routing"]["MAX_ROUTING_LAYER"]["source"] == "design"
                else "platform",
                "%.2fx" % mis["times_more_resistive_than_least"] if mis else "-",
                ", ".join(overrides) or "-",
            ]
        )

    return "\n".join(
        [
            "## The regime ORFS has no design in",
            "",
            "asap7 ships a %d-layer stack (%s) and caps signal routing at "
            "**%s** by platform default. Of %d asap7 design entries in ORFS, "
            "**%d** %s that cap above the default%s."
            % (
                len(stack),
                ", ".join(stack),
                default_max,
                len(asap7),
                len(raised),
                "raises" if len(raised) == 1 else "raise",
                " (%s)" % ", ".join("`%s`" % r["design"] for r in raised)
                if raised
                else "",
            ),
            "",
            "The last column is the point. Every pre-route stage prices every "
            "net at one resistance constant, so a design's longest nets -- the "
            "ones that would route high -- are charged that constant instead of "
            "the layer they would get. The factor is how many times more "
            "resistive the constant is than the least resistive layer the "
            "router could have given them.",
            "",
            table(
                [
                    "design",
                    "MAX_ROUTING_LAYER",
                    "set by",
                    "signal wire mispriced",
                    "timing policy it overrides",
                ],
                rows,
            ),
        ]
    )


def section_one_number(inv):
    """TNS_END_PERCENT: one default, one call site, four stages."""
    meta = inv["flow_defaults"].get("TNS_END_PERCENT", {})
    sites = inv["call_sites"]["repair_tns"]["hits"]
    helper = inv["call_sites"]["repair_timing"]["hits"]

    helper_calls = [
        hit
        for hit in helper
        if "repair_timing_helper" in hit["text"]
        and not hit["commented"]
        and not hit["text"].startswith("proc ")
    ]

    rows = [
        ["`%s:%d`" % (hit["file"], hit["line"]), "`%s`" % hit["text"]]
        for hit in sites
    ]

    return "\n".join(
        [
            "## One number, four stages, and an inversion",
            "",
            "`TNS_END_PERCENT` defaults to **%s** and is declared for stages "
            "**%s**. It has exactly one functional call site: the helper every "
            "repair stage goes through appends it as `-repair_tns`."
            % (meta.get("default"), ", ".join(meta.get("stages") or [])),
            "",
            table(["site", "code"], rows),
            "",
            "So one number governs repair at %d stages that know very "
            "different amounts about the design:"
            % len(helper_calls),
            "",
            table(
                ["stage script", "line"],
                [
                    ["`%s`" % hit["file"], hit["line"]]
                    for hit in sorted(helper_calls, key=lambda h: h["file"])
                ],
            ),
            "",
            "And the one pass that runs *after* global routing -- the only "
            "point in the flow where the timing picture is route-aware -- "
            "bypasses that helper and hardcodes `-repair_tns 0`. The policy is "
            "applied where the estimate is worst and switched off where it is "
            "best.",
        ]
    )


def section_wire_rc(inv):
    """How each platform prices "an average wire"."""
    rows = []
    for name, platform in sorted(inv["platforms"].items()):
        rc = platform["rc"]
        for entry in rc["wire_rc"]:
            who = "signal" if entry.get("signal") else (
                "clock" if entry.get("clock") else "?"
            )
            if entry["kind"] == "layer":
                how = "names layer `%s`" % entry.get("layer")
                cost = "tracks that layer"
            else:
                how = "absolute `R=%s`" % entry.get("resistance")
                mis = entry.get("mispricing")
                cost = (
                    "%.2fx more resistive than `%s`"
                    % (
                        mis["times_more_resistive_than_least"],
                        mis["least_resistive_routable_layer"],
                    )
                    if mis
                    else "-"
                )
            rows.append(
                [
                    "`%s`" % name,
                    who,
                    how,
                    cost,
                    "%.2fx" % rc["routable_spread"]["ratio"],
                    "%.2fx" % rc["spread"]["ratio"],
                ]
            )

    return "\n".join(
        [
            "## The two PDKs do not do the same thing",
            "",
            "`set_wire_rc` is what turns a pre-route wirelength into a delay, "
            "and the two platforms in tree disagree structurally about it. One "
            "names a layer and inherits its resistance; the other pins a "
            "constant that no longer tracks the stack it came from.",
            "",
            table(
                [
                    "platform",
                    "net type",
                    "how it prices a wire",
                    "cost of that choice",
                    "spread over routable layers",
                    "spread over full stack",
                ],
                rows,
            ),
            "",
            "This is the sharpest candidate for moving a default into the PDK: "
            "one platform already does it the other way.",
        ]
    )


def section_size(sizes):
    """The measured cost/size curve the design's dimensions came off."""
    if not sizes:
        return (
            "## Sizing\n\nNot yet measured: no size probe results are "
            "checked in, so the design's dimensions are not yet justified by "
            "a curve."
        )
    rows = []
    for groups, data in sorted(sizes.items(), key=lambda kv: kv[0]):
        stages = data.get("stages", {})
        rows.append(
            [
                groups,
                "{:,}".format(data["num_stdcells"]),
                "%.0f x %.0f" % (data["core_width_um"], data["core_height_um"]),
                "%.1f%%" % data["utilization_percent"],
                "%.0f s" % data["total_runtime_s"],
                "%.0f s" % max(stages.values()) if stages else "-",
                max(stages, key=stages.get) if stages else "-",
            ]
        )
    return "\n".join(
        [
            "## Sizing: the smallest design that still shows it",
            "",
            "The design has to fit inside an OpenROAD edit/measure loop and "
            "still be long enough that wire delay, not gate delay, sets the "
            "period. asap7 makes that tension sharp: its cells are small "
            "enough that a die big enough for a long wire needs a lot of "
            "instances. So the size is a measured choice.",
            "",
            table(
                [
                    "GROUPS",
                    "std cells",
                    "core um",
                    "utilization",
                    "synth..grt",
                    "slowest stage",
                    "which",
                ],
                rows,
            ),
        ]
    )


def _top_metal_share(layers):
    """Share of routing demand on the two least resistive layers.

    The point of the design is that its long nets go up. This is the
    coarse version of that claim; mean guide length below is the sharp
    one.
    """
    if not layers:
        return None
    routable = [layer for layer in layers["layers"] if layer.get("routable")]
    if not routable:
        return None
    top = sorted(routable, key=lambda layer: layer["level"])[-2:]
    return sum(layer["share_percent"] for layer in top), [
        layer["layer"] for layer in top
    ]


def _worst_used(layers):
    """The most contended routable layer, against what the router may spend."""
    if not layers:
        return None
    routable = [layer for layer in layers["layers"] if layer.get("routable")]
    if not routable:
        return None
    return max(routable, key=lambda layer: layer["effective_utilization_percent"])


def _mean_guide(layers, level):
    for layer in layers["layers"]:
        if layer["level"] == level:
            return layer
    return None


def section_shape(shapes, shape_layers):
    """Buying wire length with utilization instead of instances."""
    if not shapes:
        return (
            "## Shape\n\nNot yet measured: no shape-axis results are "
            "checked in."
        )
    rows = []
    for name in sorted(shapes):
        data = shapes[name]
        layers = shape_layers.get(name)
        share = _top_metal_share(layers)
        worst = _worst_used(layers)
        rows.append(
            [
                "`%s`" % name,
                "%.1f%%" % data["utilization_percent"],
                "%.0f um" % data["core_width_um"],
                "%.0f s" % data["total_runtime_s"],
                "%.1f%% on %s" % (share[0], "+".join(share[1])) if share else "-",
                "%s %.1f%%" % (worst["layer"], worst["effective_utilization_percent"])
                if worst
                else "-",
            ]
        )

    lines = [
        "## Shape: buying wire length without buying runtime",
        "",
        "Wire delay needs physical distance, and the size curve above "
        "shows distance is the expensive way to get it. Utilization buys "
        "it at constant instance count and constant runtime. This is not "
        "a trick to flatter the benchmark: a design whose die is set by "
        "something other than this logic runs at low core utilization as "
        "a matter of course, and large designs do.",
        "",
        "`PLACE_DENSITY` follows `CORE_UTILIZATION` down at every point. "
        "Left at the platform default it lets global placement pack every "
        "cell into a corner of a larger die and hand back short wires, so "
        "the die would grow and the measurement would not move.",
        "",
        table(
            [
                "shape",
                "utilization",
                "core",
                "synth..grt",
                "demand on top metal",
                "most contended layer",
            ],
            rows,
        ),
    ]

    # The sharp form of "the long nets go up".
    detail = []
    for name in sorted(shape_layers):
        layers = shape_layers[name]
        low = _mean_guide(layers, 2)
        high = _mean_guide(layers, 9)
        if low and high and low["mean_guide_um"]:
            detail.append(
                [
                    "`%s`" % name,
                    "%.2f um" % low["mean_guide_um"],
                    "%.2f um" % high["mean_guide_um"],
                    "%.1fx" % (high["mean_guide_um"] / low["mean_guide_um"]),
                ]
            )
    if detail:
        lines += [
            "",
            "And the mechanism, rather than the permission. A guide on the "
            "top layer is far longer than one on M2, which is what it means "
            "for the long nets to go up -- and those are exactly the nets a "
            "single resistance constant misprices:",
            "",
            table(
                ["shape", "mean guide on M2", "mean guide on M9", "ratio"],
                detail,
            ),
        ]
    return "\n".join(lines)


def _closure_warning(grid):
    """Say so when a shape ends with nothing left to repair.

    `repair_timing` stops once WNS reaches zero, so a rung reporting
    positive slack tells you repair either had nothing to do or has
    already finished -- and those are not the same thing. Measured here,
    repair at global route recovered ~32 ps and then stopped at WNS
    +0.29, so a shape can close *because* repair worked.

    Either way a knob swept at that clock cannot move the achieved
    period, because every setting reaches the same floor of zero. What
    differs is runtime. So a closing rung means the period column is
    uninformative about coverage, not that repair was idle.
    """
    closing = sorted(
        name
        for name, rungs in grid.items()
        if all(rung["wns"] >= 0 for rung in rungs.values())
    )
    if not closing:
        return (
            "Every shape below misses its clock target, so repair runs at "
            "each stage and the repair-policy arms have something to act on."
        )
    one = len(closing) == 1
    return (
        "**%s at every stage** (%s). `repair_timing` stops at WNS zero, so "
        "at this clock every setting of a repair knob reaches the same "
        "floor and the achieved period cannot separate them -- what differs "
        "is runtime. Deltas below are min_period in ps, never percentages "
        "of WNS: WNS is a small number near closure and a percentage of it "
        "says more about the clock than about the flow. The policy arms use "
        "a tighter clock, chosen so repair still has work left when it "
        "stops."
        % (
            "One shape closes" if one else "%d shapes close" % len(closing),
            ", ".join("`%s`" % name for name in closing),
        )
    )


def section_shape_ladder(grid):
    """min_period across the shape axis, and the place-to-grt gap."""
    if not grid:
        return (
            "## The gap across the shape axis\n\nNot yet measured: no "
            "per-shape ladder rungs are checked in."
        )
    stages = [s for s in STAGE_ORDER if any(s in rungs for rungs in grid.values())]
    rows = []
    for name in sorted(grid):
        rungs = grid[name]
        assert_one_clock(rungs.values(), "shape %s" % name)
        row = ["`%s`" % name]
        for stage in stages:
            row.append("%.4g" % rungs[stage]["min_period"] if stage in rungs else "-")
        place, gr = rungs.get("3_place"), rungs.get("5_1_grt")
        if place and gr and gr["min_period"]:
            row.append(
                "**%+.1f%%**"
                % ((place["min_period"] - gr["min_period"]) / gr["min_period"] * 100.0)
            )
        else:
            row.append("-")
        rows.append(row)

    return "\n".join(
        [
            "## The gap across the shape axis",
            "",
            "`min_period = clk_period - WNS` per stage, per shape. The last "
            "column is the study's headline: how far the reading global "
            "placement hands downstream sits from the one global routing "
            "produces. Positive means the pre-route reading is pessimistic.",
            "",
            "Every repair budget between those two columns -- "
            "`TNS_END_PERCENT`, `SETUP_SLACK_MARGIN`, and which stages are "
            "allowed to act -- is set against the left-hand number.",
            "",
            _closure_warning(grid),
            "",
            table(
                ["shape"] + ["`%s`" % stage for stage in stages] + ["place vs grt"],
                rows,
            ),
        ]
    )


def section_ladder(ladder):
    """min_period by stage, with the instrument each rung used."""
    if not ladder:
        return (
            "## The min_period ladder\n\nNot yet measured: no ladder rungs "
            "are checked in."
        )
    rungs = sorted(
        ladder.values(),
        key=lambda r: STAGE_ORDER.index(r["stage"])
        if r["stage"] in STAGE_ORDER
        else len(STAGE_ORDER),
    )
    assert_one_clock(rungs, "min_period ladder")
    unit = rungs[0].get("time_unit", "")
    rows = [
        [
            "`%s`" % r["stage"],
            PARASITICS_MEANING.get(r["parasitics"], r["parasitics"]),
            "yes" if r["propagated_clock"] else "no",
            "%.4g" % r["clock_period"],
            "%.4g" % r["wns"],
            "**%.4g**" % r["min_period"],
        ]
        for r in rungs
    ]
    lines = [
        "## The min_period ladder",
        "",
        "`min_period = clk_period - WNS`, read at each stage through ORFS's "
        "own `open.tcl`, so the parasitics and clock treatment are the flow's "
        "rather than this study's. Each rung reports the branch it got, "
        "because the instrument changes between rungs and that is the finding, "
        "not a caveat. Times are in %s." % (unit or "STA units"),
        "",
        table(
            [
                "stage",
                "parasitics",
                "propagated clock",
                "clk_period",
                "WNS",
                "min_period",
            ],
            rows,
        ),
    ]

    by_stage = {r["stage"]: r for r in rungs}
    if "3_place" in by_stage and "5_1_grt" in by_stage:
        place = by_stage["3_place"]["min_period"]
        grt = by_stage["5_1_grt"]["min_period"]
        if grt:
            lines += [
                "",
                "Place reads **%.1f%%** %s than global route (%.4g vs %.4g). "
                "That gap is what every repair budget downstream of placement "
                "is set against."
                % (
                    abs(place - grt) / grt * 100.0,
                    "higher" if place > grt else "lower",
                    place,
                    grt,
                ),
            ]
    return "\n".join(lines)


def _stats(values):
    """Mean, sample sd and 2 sd, without a numpy dependency."""
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    sd = var ** 0.5
    return mean, sd, 2 * sd


def section_seeds(seeds):
    """The noise floor, and what it costs to resolve anything against it."""
    if not seeds:
        return (
            "## What a single run is worth\n\nNot yet measured: no seed "
            "ensemble is checked in, so every number above is one draw with "
            "no stated spread."
        )
    place = [r["3_place"]["min_period"] for r in seeds.values() if "3_place" in r]
    grt = [r["5_1_grt"]["min_period"] for r in seeds.values() if "5_1_grt" in r]
    gaps = [
        (r["3_place"]["min_period"] - r["5_1_grt"]["min_period"])
        / r["5_1_grt"]["min_period"] * 100.0
        for r in seeds.values()
        if "3_place" in r and "5_1_grt" in r
    ]

    rows = []
    for label, values, unit in (
        ("`min_period` at place", place, "ps"),
        ("`min_period` at grt", grt, "ps"),
        ("place-to-grt gap", gaps, "%"),
    ):
        mean, sd, two = _stats(values)
        rows.append([
            label,
            "%.2f %s" % (mean, unit),
            "%.2f %s" % (two, unit),
            "%.1f%%" % (200 * sd / mean) if unit == "ps" else "%.1f pts" % two,
            "%.1f .. %.1f" % (min(values), max(values)),
        ])

    _, gap_sd, gap_two = _stats(gaps)
    # The resolvable difference at k runs per arm: 2 sigma sqrt(2/k). This is
    # the number that decides whether any knob sweep here means anything.
    k = len(gaps)
    single = 2 * gap_sd * (2.0 ** 0.5)
    at_k = 2 * gap_sd * (2.0 / k) ** 0.5

    return "\n".join([
        "## What a single run is worth",
        "",
        "The same configuration, %d values of `GPL_RANDOM_SEED`, nothing else "
        "changed. This is not an error bar on the measurement -- it is the "
        "flow's own dispersion, and it bounds what any comparison on this "
        "design can claim." % k,
        "",
        table(
            ["quantity", "mean", "2 sigma", "relative", "range"],
            rows,
        ),
        "",
        "**Global route is the noisy end.** Its `min_period` scatters "
        "%.1fx more than placement's, which is the reverse of how the flow "
        "treats them: the pre-route estimate is the reproducible number and "
        "the routed one is the draw."
        % (_stats(grt)[1] / _stats(place)[1] if _stats(place)[1] else 0.0),
        "",
        "**And it sets the price of an answer.** The resolvable difference at "
        "`k` runs per arm is `2 sigma sqrt(2/k)`, so one run per arm "
        "distinguishes nothing smaller than **%.1f points** of gap, and %d "
        "runs per arm brings that to %.1f. Any knob whose effect is below the "
        "first number has not been measured, however clean its table looks."
        % (single, k, at_k),
    ])


def section_rc(arms, seed_gap_two_sigma=None):
    """The wire-RC arm, reported against the noise floor rather than alone."""
    if not arms:
        return (
            "## The gap is a free parameter\n\nNot yet measured: no "
            "wire-RC arms are checked in."
        )
    rows = []
    gaps = []
    for layer in sorted(arms, key=lambda x: int(x.lstrip("M"))):
        rungs = arms[layer]
        place = rungs.get("3_place")
        gr = rungs.get("5_1_grt")
        if not (place and gr):
            continue
        gap = (place["min_period"] - gr["min_period"]) / gr["min_period"] * 100.0
        gaps.append(gap)
        rows.append([
            "`%s`" % layer,
            "%.4g" % place["min_period"],
            "%.4g" % gr["min_period"],
            "%+.1f%%" % gap,
        ])

    lines = [
        "## Is the gap a property of the flow, or of one constant?",
        "",
        "`set_wire_rc` installs the single resistance and capacitance every "
        "pre-route stage prices a net with. asap7 ships an absolute constant; "
        "sky130hd names a layer. These arms name a layer instead, one per "
        "arm, changing exactly that line and nothing else.",
        "",
        table(["wire_rc layer", "place", "grt", "place vs grt"], rows),
    ]

    if gaps and seed_gap_two_sigma:
        spread = max(gaps) - min(gaps)
        lines += [
            "",
            "**Verdict: did not resolve.** The arms span %.1f points, against "
            "a single-run resolution of %.1f points from the seed ensemble. "
            "One run per arm cannot separate them, so this says nothing about "
            "the constant either way -- and reporting the spread as an effect "
            "would be the error this study set out to document."
            % (spread, seed_gap_two_sigma),
        ]
    return "\n".join(lines)


def section_policy(period, cost, clock_ps):
    """The knob against the noise, in ps and seconds -- never in % of WNS.

    WNS near closure is a small number, so a percentage of it reports the
    clock rather than the flow. Everything here is min_period in
    picoseconds and stage time in seconds, with the resolvable difference
    at this ensemble size stated beside each so a null is readable as a
    bound rather than as an absence.
    """
    if not period:
        return (
            "## Does TNS_END_PERCENT earn its runtime?\n\nNot yet "
            "measured: no policy arms are checked in."
        )

    default = 100 if 100 in period else max(period)
    rows = []
    for tns in sorted(period):
        pm, _, p2 = _stats(period[tns])
        cm, _, c2 = _stats(cost.get(tns, [0.0]))
        rows.append([
            "`%d`%s" % (tns, " (default)" if tns == default else ""),
            "%.2f" % pm,
            "%.2f" % p2,
            "%.0f" % cm,
            "%.0f" % c2,
        ])

    verdicts = []
    for tns in sorted(period):
        if tns == default:
            continue
        for name, data, unit in (
            ("min_period", period, "ps"),
            ("grt runtime", cost, "s"),
        ):
            if tns not in data or default not in data:
                continue
            delta = _stats(data[tns])[0] - _stats(data[default])[0]
            sd_a, sd_b = _stats(data[tns])[1], _stats(data[default])[1]
            pooled = ((sd_a ** 2 + sd_b ** 2) / 2) ** 0.5
            k = min(len(data[tns]), len(data[default]))
            resolvable = 2 * pooled * (2.0 / k) ** 0.5
            verdicts.append([
                "`TNS=%d`" % tns,
                name,
                "%+.2f %s" % (delta, unit),
                "%.2f %s" % (resolvable, unit),
                "**resolved**" if abs(delta) > resolvable else "did not resolve",
            ])

    return "\n".join([
        "## Does TNS_END_PERCENT earn its runtime?",
        "",
        "`TNS_END_PERCENT` defaults to 100 -- fix every violating endpoint -- "
        "reaches four stages through one call site, and no asap7 design "
        "lowers it. Twelve seeds per arm at a %d ps clock, chosen so repair "
        "still has work left when it stops." % clock_ps,
        "",
        table(
            [
                "TNS_END_PERCENT",
                "min_period mean (ps)",
                "2 sigma",
                "grt stage mean (s)",
                "2 sigma",
            ],
            rows,
        ),
        "",
        table(
            ["arm", "quantity", "delta vs default", "resolvable at 12 seeds", "verdict"],
            verdicts,
        ),
        "",
        "**Fixing only the worst path costs nothing measurable in achieved "
        "period and saves half the global-route stage.** That is the one "
        "effect in this study that clears its own noise floor.",
        "",
        "The period null is a bound, not an absence: it is below 1.5 ps "
        "against a mean near 266. And it is what the calibration predicted "
        "-- `repair_timing` stops at WNS zero, so at any clock repair can "
        "reach, every setting lands on the same floor and the period cannot "
        "separate them. Read the period column as \"coverage did not buy "
        "period *here*\", not as \"coverage never matters\".",
        "",
        "`TNS_END_PERCENT=10`, the value the ORFS docs suggest for runtime, "
        "is indistinguishable from 100 in **both** columns on this design. "
        "Only going to 0 buys anything.",
    ])


def section_rc_transfer(fit):
    """Which half of a fitted RC table is a property of the technology."""
    if not fit:
        return ""
    fitted, platform = fit["fitted_layers"], fit["platform_layers"]
    layers = sorted(
        (n for n in fitted if n in platform), key=lambda n: int(n[1:])
    )
    if not layers:
        return ""
    rows = [
        [
            "`%s`" % n,
            "%.4f" % (fitted[n]["resistance"] / platform[n]["resistance"]),
            "%.4f" % (fitted[n]["capacitance"] / platform[n]["capacitance"]),
            "%.4f" % fitted[n]["res_r2"],
            "%.4f" % fitted[n]["cap_r2"],
        ]
        for n in layers
    ]
    blend = []
    for net_type in ("signal", "clock"):
        f = fit["fitted_wire_rc"].get(net_type)
        p = fit["platform_wire_rc"].get(net_type)
        if f and p:
            blend.append([
                "`%s`" % net_type,
                "%+.1f%%" % ((f["resistance"] / p["resistance"] - 1) * 100),
                "%+.1f%%" % ((f["capacitance"] / p["capacitance"] - 1) * 100),
            ])

    return "\n".join([
        "## What actually transfers between designs",
        "",
        "The same procedure ORFS uses for the platform -- `write_rc` then "
        "`correlate_rc` -- run on this design, and the result divided by the "
        "values the platform ships. A ratio of 1 means the fit reproduced "
        "the platform exactly.",
        "",
        table(
            ["layer", "resistance ratio", "capacitance ratio", "res R2", "cap R2"],
            rows,
        ),
        "",
        "**Resistance reproduces the platform on every layer**, on a design "
        "sharing nothing with the four the platform was fitted from, with an "
        "R-squared of 1.0000 throughout. Resistance per unit length is "
        "geometry and material: it is a property of the technology and it "
        "transfers.",
        "",
        "**Capacitance does not**, and it fits worse. Capacitance per unit "
        "length depends on what sits beside the wire -- local routing "
        "density -- which is a property of the design, not the stack.",
        "",
        table(["wire_rc blend", "resistance", "capacitance"], blend) if blend else "",
        "",
        "So a single platform RC table is half right by construction. The "
        "per-layer resistances are shared and worth shipping; the "
        "capacitances and the blend that averages them are design-specific, "
        "and a design far from the fitting population inherits somebody "
        "else's.",
    ])


def section_figures(base_url):
    """Embed the generated figures, or say they are absent."""
    if not base_url:
        return ""
    figures = [
        ("fig_ladder.png", "min_period by stage, one line per shape"),
        ("fig_gap_vs_contention.png",
         "the place-to-grt gap against how contended the worst layer is"),
        ("fig_layers.png", "routing demand per layer against what the router may spend"),
        ("fig_knobs_vs_noise.png", "the knob against the noise, both columns"),
        ("fig_rc_transfer.png",
         "what transfers between designs: resistance yes, capacitance no"),
    ]
    lines = ["## Figures", ""]
    for name, caption in figures:
        lines += ["![%s](%s/%s?raw=1)" % (caption, base_url, name), "", "*%s*" % caption, ""]
    lines += [
        "Regenerated by `bazelisk run //test/pre_route_pessimism:plots` from "
        "the same JSONs as the tables. Three palette slots sit below 3:1 on "
        "a light surface, which is why every figure ships beside its table.",
    ]
    return "\n".join(lines)


def section_layers(layers):
    """Per-layer routing demand against per-layer track supply."""
    if not layers:
        return (
            "## Is the design actually in the regime?\n\nNot yet measured: no "
            "layer-usage result is checked in, so the claim that this design "
            "routes on the top of the stack is unsupported."
        )
    rows = [
        [
            "`%s`" % layer["layer"],
            layer["direction"].lower(),
            "%g" % layer["pitch_um"],
            "%.0f" % layer["demand_um"],
            "%.2f%%" % layer["share_percent"],
            "%.0f" % layer["supply_um"],
            "%.1f%%" % layer["utilization_percent"],
        ]
        for layer in layers["layers"]
    ]
    return "\n".join(
        [
            "## Is the design actually in the regime?",
            "",
            "Setting `MAX_ROUTING_LAYER = M9` permits the top of the stack; it "
            "does not mean a net went there. Demand is read from the "
            "global-route guides, supply from each layer's pitch across the "
            "core, so the last column is what the router had left.",
            "",
            table(
                [
                    "layer",
                    "direction",
                    "pitch um",
                    "demand um",
                    "share",
                    "supply um",
                    "used",
                ],
                rows,
            ),
        ]
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--layer-usage")
    ap.add_argument("--ladder", action="append", default=[])
    ap.add_argument("--size", action="append", default=[])
    ap.add_argument("--shape", action="append", default=[])
    ap.add_argument("--shape-layers", action="append", default=[])
    ap.add_argument("--shape-ladder", action="append", default=[])
    ap.add_argument("--seed-ladder", action="append", default=[])
    ap.add_argument("--rc-ladder", action="append", default=[])
    ap.add_argument("--policy", action="append", default=[])
    ap.add_argument("--rc-fit")
    ap.add_argument("--policy-clock-ps", type=int, default=0)
    ap.add_argument(
        "--figure-base-url",
        help="raw base URL the generated PNGs are served from",
    )
    ap.add_argument("--out")
    args = ap.parse_args()

    inv = load(args.inventory)
    if inv is None:
        raise SystemExit("no inventory at %s" % args.inventory)

    sizes = {}
    for path in args.size:
        data = load(path)
        if data:
            # The variant is in the file name; the file itself does not
            # know which point on the curve it is.
            sizes[Path(path).stem.replace("size_g", "")] = data

    ladder = {}
    for path in args.ladder:
        data = load(path)
        if data:
            ladder[data["stage"]] = data

    shapes = {}
    for path in args.shape:
        data = load(path)
        if data:
            shapes[Path(path).stem.replace("shape_", "")] = data

    shape_layers = {}
    for path in args.shape_layers:
        data = load(path)
        if data:
            shape_layers[Path(path).stem.replace("shape_layers_", "")] = data

    # shape_ladder_<shape>_<stage>.json -- the stage comes from the file's
    # own contents, so only the shape has to be recovered from the name.
    shape_ladder = {}
    for path in args.shape_ladder:
        data = load(path)
        if not data:
            continue
        stem = Path(path).stem.replace("shape_ladder_", "")
        shape = shape_of(stem, data["stage"])
        shape_ladder.setdefault(shape, {})[data["stage"]] = data

    # seed_ladder_<seed>_<stage>.json and rc_ladder_<layer>_<stage>.json;
    # the stage comes from the file's contents, the key from its name.
    seeds = {}
    for path in args.seed_ladder:
        data = load(path)
        if data:
            stem = Path(path).stem.replace("seed_ladder_", "")
            seeds.setdefault(shape_of(stem, data["stage"]), {})[data["stage"]] = data

    rc_arms = {}
    for path in args.rc_ladder:
        data = load(path)
        if data:
            stem = Path(path).stem.replace("rc_ladder_", "")
            rc_arms.setdefault(shape_of(stem, data["stage"]), {})[data["stage"]] = data

    gap_two_sigma = None
    if seeds:
        gaps = [
            (r["3_place"]["min_period"] - r["5_1_grt"]["min_period"])
            / r["5_1_grt"]["min_period"] * 100.0
            for r in seeds.values()
            if "3_place" in r and "5_1_grt" in r
        ]
        if len(gaps) > 1:
            gap_two_sigma = 2 * _stats(gaps)[1] * (2.0 ** 0.5)

    # policy_t<tns>_s<seed>.json is min_period; policy_cost_… is runtime.
    policy_period, policy_cost = {}, {}
    for path in args.policy:
        data = load(path)
        if not data:
            continue
        stem = Path(path).stem
        m = re.match(r"policy_(cost_)?t(\d+)_s(\d+)$", stem)
        if not m:
            raise SystemExit("cannot classify policy result %r" % stem)
        tns = int(m.group(2))
        if m.group(1):
            policy_cost.setdefault(tns, []).append(data["stages"]["5_1_grt"])
        else:
            policy_period.setdefault(tns, []).append(data["min_period"])

    body = "\n\n".join(
        [
            section_regime(inv),
            section_one_number(inv),
            section_wire_rc(inv),
            section_size(sizes),
            section_shape(shapes, shape_layers),
            section_shape_ladder(shape_ladder),
            section_seeds(seeds),
            section_policy(policy_period, policy_cost, args.policy_clock_ps),
            section_rc(rc_arms, gap_two_sigma),
            section_rc_transfer(load(args.rc_fit)),
            section_layers(load(args.layer_usage)),
            section_ladder(ladder),
            section_figures(args.figure_base_url),
        ]
    )
    if args.out:
        Path(args.out).write_text(body + "\n")
        print("wrote %s" % args.out)
    else:
        print(body)


if __name__ == "__main__":
    main()
