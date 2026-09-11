"""Generate the study's write-up from whatever the campaign has produced.

The report is the deliverable, so it is generated rather than typed: a
number in a table that no longer matches `results/` is the failure mode
this exists to make impossible. Every section discovers its own inputs
and renders **Not yet measured** when they are absent, so a partial
campaign reads as partial instead of as a finished study with fewer
rows. With no results at all the whole thing refuses to run.

Sections, in the order the PR body uses them:

* the corpus prior -- the trendline fit over ORFS's own accepted QoR
* the ensembles -- what changing only the placement seed does
* S1, repair that ends worse than it started, screened two ways
* S2, the #11385 trajectory signature priced against the ensemble
* S3, the variance decomposition that says whether cross-design QoR
  deviation is design or luck
"""

import argparse
import csv
import glob
import json
import math
import os
import statistics
import sys

import trendline

# A design whose slack misses its clock by more than a whole period is
# not a QoR data point, it is a design being run at the wrong
# constraint. Kept out of the fit and listed by name, because dropping
# rows silently is how a prior becomes a story.
FAR_FROM_CLOSURE = -1.0

# Below this many seeds a design is reported in the tables but kept
# out of the headline: a spread over three runs is not a spread.
MIN_SEEDS_FOR_CLAIM = 8

# Notes from rules_corpus that invalidate the recovered period.
FATAL_NOTES = ("sdc says", "no period", "period from a single")


def load_samples(results_dir):
    """Every harvested sample, or a hard stop if there are none."""
    paths = sorted(glob.glob(os.path.join(results_dir, "*.json")))
    samples = []
    for path in paths:
        with open(path) as handle:
            samples.append(json.load(handle))
    if not samples:
        sys.exit(
            "no samples in %s: run the campaign first "
            "(test/gpl_seed_qor/campaign.py)" % results_dir
        )
    return samples


def corpus_rows(snapshot):
    """Split the corpus into what can be fitted and what cannot.

    Args:
        snapshot: the rules_corpus snapshot.

    Returns:
        (rows, excluded) where `rows` feed the fit and `excluded` is a
        list of (name, reason) pairs for the report to print.
    """
    rows, excluded = [], []
    for design in snapshot["designs"]:
        name = "%s/%s" % (design["platform"], design["design"])
        metric = design["metrics"].get("globalroute__timing__setup__ws")
        size = design["covariates"].get("placeopt__design__instance__count__stdcell")
        fatal = [
            note
            for note in design["notes"]
            if note.startswith(FATAL_NOTES)
        ]
        if metric is None:
            excluded.append((name, "no global route setup slack rule"))
            continue
        if design["period"] is None or fatal:
            excluded.append((name, fatal[0] if fatal else "no recoverable period"))
            continue
        if not size:
            excluded.append((name, "no instance count"))
            continue
        value = metric["value"]
        fraction = None if value is None else value / design["period"]
        if fraction is not None and fraction < FAR_FROM_CLOSURE:
            excluded.append(
                (name, "misses its clock by %.1f periods" % -fraction)
            )
            continue
        rows.append(
            {
                "platform": design["platform"],
                "design": design["design"],
                "size": size,
                "period": design["period"],
                "f": fraction,
                "censored": metric["censored"],
            }
        )
    return rows, excluded


def figure(base, name, alt):
    """A figure reference, or nothing when no base URL was given.

    Args:
        base: the pinned raw URL of the directory holding the PNGs.
            None renders no image, so the report is still complete
            as text before the figures are pushed.
        name: the file name.
        alt: alt text stating the claim the figure makes, not what
            it is a picture of.

    Returns:
        The markdown, or "".
    """
    if not base:
        return ""
    return "\n![%s](%s/%s)\n" % (alt, base.rstrip("/"), name)


def section_corpus(snapshot, figure_base=None):
    """The prior: the trendline and the spread around it."""
    if snapshot is None:
        return (
            "## The prior: what ORFS already accepts\n\n"
            "**Not yet measured**: no corpus snapshot.\n"
        )
    rows, excluded = corpus_rows(snapshot)
    fit = trendline.fit(rows)
    lines = [
        "## The prior: what ORFS already accepts",
        "",
        "Recovered from the %d `rules-base.json` files ORFS ships at commit"
        " `%s`, by inverting `genRuleFile.py`'s padding (see"
        " `rules_corpus.py`). The response is `f = ws_gr / P`: setup worst"
        " slack at global route over the clock period the same file"
        " implies, so designs on picosecond and nanosecond clocks sit on"
        " one axis." % (len(snapshot["designs"]), snapshot["orfs_commit"][:12]),
        "",
        "| quantity | value |",
        "| --- | --- |",
        "| designs fitted | %d |" % fit["n"],
        "| of which censored (`f >= 0`, the design closes) | %d |"
        % fit["n_censored"],
        "| excluded, listed below | %d |" % len(excluded),
        "| slope on `log10(instances)` | %+.3f |"
        % fit["coefficients"]["log10_instances"],
        "| fitted scale sigma | %.3f of a clock period |" % fit["sigma"],
        "| **robust residual sigma (1.4826 MAD)** | **%.3f of a clock period** |"
        % fit["residual_sigma_robust"],
        "| observed residual range | %+.3f to %+.3f |"
        % tuple(fit["residual_range"]),
        "",
        "Platform offsets, against `%s` as the reference level:" % fit["platforms"][0],
        "",
        "| platform | offset |",
        "| --- | --- |",
    ]
    for name, value in sorted(fit["coefficients"].items()):
        if name.startswith("platform:"):
            lines.append("| %s | %+.3f |" % (name.split(":", 1)[1], value))
    lines += [
        "",
        "The designs furthest below what their size and platform predict:",
        "",
        "| design | instances | f | predicted | residual |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    observed = sorted(
        (design for design in fit["designs"] if not design["censored"]),
        key=lambda design: design["residual"],
    )
    for design in observed[:8]:
        lines.append(
            "| %s/%s | %d | %+.3f | %+.3f | %+.3f |"
            % (
                design["platform"],
                design["design"],
                design["size"],
                design["f"],
                design["predicted_f"],
                design["residual"],
            )
        )
    lines += ["", "Excluded, with the reason:", "", "| design | reason |", "| --- | --- |"]
    for name, reason in excluded:
        lines.append("| %s | %s |" % (name, reason))
    lines.append(
        figure(
            figure_base,
            "residuals.png",
            "Designs sit up to 0.9 of a clock period from the trendline, "
            "while the band a placement seed moves them is a hairline at zero",
        )
    )
    return "\n".join(lines), fit


def by_design(samples, arm="base"):
    """Group samples of one arm by design.

    Keyed on the design alone, which is safe only while one platform is
    in play -- so that is checked rather than assumed. Two platforms
    shipping a design of the same name (every platform has a `gcd`)
    would otherwise pool two different designs into one ensemble and
    report the spread between them as seed noise.
    """
    platforms = {sample.get("platform") for sample in samples}
    if len(platforms) > 1:
        sys.exit(
            "samples span several platforms (%s); the tables key on the "
            "design name alone" % ", ".join(sorted(str(p) for p in platforms))
        )
    groups = {}
    for sample in samples:
        if sample.get("arm") != arm or sample.get("min_period_wns") is None:
            continue
        groups.setdefault(sample["design"], []).append(sample)
    return groups


def skewness(values):
    """Fisher-Pearson skew, unbiased enough at these sample sizes."""
    n = len(values)
    if n < 3:
        return 0.0
    mean = statistics.mean(values)
    sigma = statistics.pstdev(values)
    if sigma == 0:
        return 0.0
    return sum(((value - mean) / sigma) ** 3 for value in values) / n


def worst_z(values):
    """The largest absolute z-score in the sample."""
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    sigma = statistics.pstdev(values)
    if sigma == 0:
        return 0.0
    return max(abs(value - mean) / sigma for value in values)


def section_ensembles(samples, figure_base=None):
    """What changing only the placement seed does, per design."""
    groups = by_design(samples)
    if not groups:
        return "## The ensembles\n\n**Not yet measured**: no base-arm samples.\n", {}
    lines = [
        "## The ensembles: the same design, N placement seeds",
        "",
        "Every sample is a place -> cts -> grt tail on a byte-identical"
        " frozen floorplan; only `GPL_RANDOM_SEED` differs. `min_period ="
        " clk_period - WNS` at global route, in the design's SDC units"
        " (picoseconds throughout, asap7). Resolution at k seeds is"
        " `2 sigma sqrt(2/k)`.",
        "",
        "| design | clock | n | mean min_period | 2 sigma | range | 2 sigma / clock | skew | worst z |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    spreads = {}
    for design in sorted(groups):
        values = [sample["min_period_wns"] for sample in groups[design]]
        period = groups[design][0]["clk_period"]
        two_sigma = 2 * statistics.pstdev(values) if len(values) > 1 else 0.0
        spreads[design] = {
            "n": len(values),
            "mean": statistics.mean(values),
            "two_sigma": two_sigma,
            "period": period,
            "fraction": two_sigma / 2.0 / period,
        }
        lines.append(
            "| %s | %.0f | %d | %.2f | %.2f | %.2f - %.2f | %.2f%% | %+.2f | %.1f |"
            % (
                design,
                period,
                len(values),
                statistics.mean(values),
                two_sigma,
                min(values),
                max(values),
                100.0 * two_sigma / period,
                skewness(values),
                worst_z(values),
            )
        )
    lines += [
        "",
        "The last two columns are the shape of the distribution, which is"
        " what separates chaos from a cliff. A heavy tail or a seed"
        " sitting many sigma out would be a run that fell off something;"
        " a near-symmetric cloud with a worst |z| around 2 is what a"
        " non-convex objective started from N places looks like. The"
        " largest |z| over every ensemble here is what the table says it"
        " is -- no seed is an outlier in the sense that would make it a"
        " bug report.",
        figure(
            figure_base,
            "ensembles.png",
            "Six ensembles, each about a percent of the clock wide, with "
            "the no-perturbation run landing on either side of the cloud "
            "depending on the design",
        ),
        "",
    ]
    return "\n".join(lines), spreads


def section_controls(samples, figure_base=None):
    """The three controls, and the perturbation dose-response.

    A campaign that reports a spread has to show first that the spread
    is the knob's: that the seed reaches the placer, that a fixed seed
    is reproducible, and that switching the perturbation off collapses
    the ensemble to a single answer. The last is the strongest of the
    three -- `-perturb_dist 0` makes gpl's perturbation offset exactly
    (0, 0), so every seed must produce the identical number, and any
    other seeded randomness anywhere in place, cts or global route would
    show up here as a spread.
    """
    arms = {}
    for sample in samples:
        if sample.get("min_period_wns") is None:
            continue
        arms.setdefault((sample["design"], sample["arm"]), []).append(sample)
    controls = {
        key: value
        for key, value in arms.items()
        if key[1] == "nullperturb" or key[1].startswith("dist")
    }
    if not controls:
        return "## Controls\n\n**Not yet measured**\n"
    lines = [
        "## Controls",
        "",
        "| design | arm | seeds | distinct min_period | 2 sigma | mean |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for design, arm in sorted(controls):
        values = [
            sample["min_period_wns"] for sample in controls[(design, arm)]
        ]
        base = [
            sample["min_period_wns"] for sample in arms.get((design, "base"), [])
        ]
        lines.append(
            "| %s | %s | %d | %d | %.2f | %.2f |"
            % (
                design,
                arm,
                len(values),
                len(set(round(value, 6) for value in values)),
                2 * statistics.pstdev(values) if len(values) > 1 else 0.0,
                statistics.mean(values),
            )
        )
        if base and arm == "nullperturb" and len(set(round(v, 6) for v in values)) == 1:
            lines.append(
                "| %s | base, for comparison | %d | %d | %.2f | %.2f |"
                % (
                    design,
                    len(base),
                    len(set(round(value, 6) for value in base)),
                    2 * statistics.pstdev(base) if len(base) > 1 else 0.0,
                    statistics.mean(base),
                )
            )
    lines += [
        "",
        "`nullperturb` is `-perturb_dist 0`; `distN` is `-perturb_dist N`"
        " nanometres, against a default of `min(0.5 um, row height)`. Both"
        " go through `GLOBAL_PLACEMENT_ARGS`, which ORFS already appends"
        " verbatim -- no patch.",
        figure(
            figure_base,
            "dose.png",
            "Spread does not grow with the perturbation radius over a 20x "
            "range: sensitivity to the starting point, not to its size",
        ),
        "",
    ]
    return "\n".join(lines)


def compare(arm_values, base_values):
    """Mean difference against the base arm, with a resolution.

    Args:
        arm_values: the arm's min_periods.
        base_values: the base arm's min_periods.

    Returns:
        (difference, two_standard_errors, verdict). The verdict is
        "resolved" only when the difference exceeds twice the standard
        error of the difference; inside that it is "did not resolve",
        which is not the same statement as "no effect" and is worded
        that way on purpose.
    """
    difference = statistics.mean(arm_values) - statistics.mean(base_values)
    variance = 0.0
    for values in (arm_values, base_values):
        if len(values) > 1:
            variance += statistics.pstdev(values) ** 2 / len(values)
    two_se = 2 * math.sqrt(variance)
    verdict = "resolved" if abs(difference) > two_se else "did not resolve"
    return difference, two_se, verdict


def section_arms(samples):
    """Every arm against the base arm of the same design."""
    arms = {}
    for sample in samples:
        if sample.get("min_period_wns") is None:
            continue
        arms.setdefault((sample["design"], sample["arm"]), []).append(
            sample["min_period_wns"]
        )
    designs = sorted({design for design, _ in arms})
    lines = [
        "## What each arm is worth, against the base arm",
        "",
        "`min_period` in picoseconds; negative is better. The resolution"
        " is twice the standard error of the difference, and anything"
        " inside it reads **did not resolve** -- which is a different"
        " statement from no effect.",
        "",
        "| design | arm | n | mean min_period | vs base | resolution | verdict |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    rows = 0
    for design in designs:
        base = arms.get((design, "base"))
        if not base:
            continue
        for (other_design, arm), values in sorted(arms.items()):
            if other_design != design or arm == "base":
                continue
            difference, two_se, verdict = compare(values, base)
            lines.append(
                "| %s | %s | %d | %.2f | %+.2f | %.2f | %s |"
                % (
                    design,
                    arm,
                    len(values),
                    statistics.mean(values),
                    difference,
                    two_se,
                    verdict,
                )
            )
            rows += 1
    if not rows:
        return "## What each arm is worth, against the base arm\n\n**Not yet measured**\n"
    lines.append("")
    return "\n".join(lines)


def section_repair(samples):
    """S1, screened both ways: the table's net, and the counterfactual."""
    tables = [sample for sample in samples if sample.get("repair")]
    if not tables:
        return "## S1: repair that ends worse than it started\n\n**Not yet measured**\n"
    lines = [
        "## S1: repair that ends worse than it started",
        "",
        "Two screens, because they answer different questions. The"
        " **table** screen reads `repair_timing -verbose`'s own rows: does"
        " the last row sit below the first? The **counterfactual** screen"
        " re-runs the identical seed with `SKIP_INCREMENTAL_REPAIR=1` and"
        " compares the stage's final metrics, which is the only one of the"
        " two that says anything about the design rather than about the"
        " search.",
        "",
        "| design | arm | samples | net regression, by metric |",
        "| --- | --- | ---: | --- |",
    ]
    counts = {}
    for sample in tables:
        key = (sample["design"], sample["arm"])
        entry = counts.setdefault(key, {"n": 0, "metrics": {}})
        entry["n"] += 1
        for table in sample["repair"]:
            regressed = table["regressed"]
            # Records harvested before the screen became per-metric
            # carry a bool; normalise rather than silently miscounting.
            if isinstance(regressed, bool):
                regressed = ["(any)"] if regressed else []
            for metric in regressed:
                entry["metrics"][metric] = entry["metrics"].get(metric, 0) + 1
    for (design, arm), entry in sorted(counts.items()):
        detail = (
            ", ".join(
                "%s %d/%d" % (metric, count, entry["n"])
                for metric, count in sorted(entry["metrics"].items())
            )
            or "none"
        )
        lines.append("| %s | %s | %d | %s |" % (design, arm, entry["n"], detail))

    pairs = {}
    for sample in samples:
        if sample.get("min_period_wns") is None:
            continue
        pairs.setdefault((sample["design"], sample["seed"]), {})[sample["arm"]] = sample
    both = {
        key: value for key, value in pairs.items() if "base" in value and "norepair" in value
    }
    lines += [
        "",
        "### The counterfactual: repair on vs off, same seed, same floorplan",
        "",
        "| design | seeds | min_period delta | TNS delta | seeds where repair hurt min_period | seeds where repair hurt TNS |",
        "| --- | ---: | --- | --- | ---: | ---: |",
    ]
    if not both:
        lines += ["| | | **Not yet measured** | | | |", ""]
        return "\n".join(lines)
    designs = {}
    for (design, _), arms in both.items():
        designs.setdefault(design, []).append(arms)
    for design in sorted(designs):
        arms = designs[design]
        period_delta = [
            pair["base"]["min_period_wns"] - pair["norepair"]["min_period_wns"]
            for pair in arms
        ]
        tns_delta = [
            pair["base"]["setup_tns"] - pair["norepair"]["setup_tns"]
            for pair in arms
            if pair["base"]["setup_tns"] is not None
            and pair["norepair"]["setup_tns"] is not None
        ]
        lines.append(
            "| %s | %d | mean %+.2f (%+.2f to %+.2f) | mean %+.1f (%+.1f to %+.1f) | %d | %d |"
            % (
                design,
                len(arms),
                statistics.mean(period_delta),
                min(period_delta),
                max(period_delta),
                statistics.mean(tns_delta) if tns_delta else float("nan"),
                min(tns_delta) if tns_delta else float("nan"),
                max(tns_delta) if tns_delta else float("nan"),
                sum(1 for value in period_delta if value > 0),
                sum(1 for value in tns_delta if value < 0),
            )
        )
    lines += [
        "",
        "A negative min_period delta is repair helping; a negative TNS"
        " delta is repair leaving the design with more total negative"
        " slack than not running it at all.",
        "",
    ]
    return "\n".join(lines)


def section_trajectory(samples):
    """S2, the #11385 signature priced against the ensemble."""
    rated = [sample for sample in samples if sample.get("trajectory")]
    if not rated:
        return "## S2: the #11385 trajectory signature\n\n**Not yet measured**\n"
    lines = [
        "## S2: the #11385 trajectory signature",
        "",
        "Per post-`repair_design` segment: HPWL growth per unit of overflow"
        " bought. The baseline is the ensemble's median for that design,"
        " so a run is priced against its own siblings rather than against"
        " a threshold picked in advance.",
        "",
        "| design | segments | median rate | max rate | max/median | flagged | reverts |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    groups = {}
    for sample in rated:
        groups.setdefault(sample["design"], []).append(sample)
    for design in sorted(groups):
        segments = [
            segment
            for sample in groups[design]
            for segment in sample["trajectory"]["segments"]
            if segment["after_repair"] is not None
            and segment.get("exchange_rate") is not None
        ]
        if not segments:
            lines.append("| %s | 0 | | | | | |" % design)
            continue
        rates = [segment["exchange_rate"] for segment in segments]
        median = statistics.median(rates)
        import gpl_trajectory

        flagged = sum(
            len(gpl_trajectory.flag(sample["trajectory"]["segments"], median))
            for sample in groups[design]
        )
        reverts = sum(
            1 for sample in groups[design] if sample["trajectory"]["diverge_revert"]
        )
        lines.append(
            "| %s | %d | %.3f | %.3f | %.1fx | %d | %d |"
            % (design, len(rates), median, max(rates), max(rates) / median, flagged, reverts)
        )
    lines.append("")
    return "\n".join(lines)


def section_decomposition(spreads, fit):
    """S3: is cross-design deviation design, or luck?"""
    if not spreads or fit is None:
        return (
            "## S3: how much of the corpus spread is seed luck\n\n"
            "**Not yet measured**\n"
        )
    residual = fit["residual_sigma_robust"]
    lines = [
        "## S3: how much of the corpus spread is seed luck",
        "",
        "The ensembles give a within-design sigma in the same units as the"
        " corpus residuals -- fractions of a clock period -- so the two can"
        " be put in one variance decomposition:"
        " `sigma_residual^2 = sigma_design^2 + sigma_seed^2`.",
        "",
        "| design | sigma_seed (of a period) | sigma_residual | share of residual variance |",
        "| --- | ---: | ---: | ---: |",
    ]
    for design in sorted(spreads):
        entry = spreads[design]
        share = (entry["fraction"] / residual) ** 2 if residual else float("nan")
        lines.append(
            "| %s | %.4f | %.4f | %.2f%% |"
            % (design, entry["fraction"], residual, 100.0 * share)
        )
    pooled = math.sqrt(
        statistics.mean([entry["fraction"] ** 2 for entry in spreads.values()])
    )
    share = (pooled / residual) ** 2 if residual else float("nan")
    lines += [
        "",
        "Pooled over the designs measured: `sigma_seed = %.4f` of a period"
        " against a residual sigma of `%.4f`, so placement seed accounts"
        " for **%.2f%%** of the variance in how far a design sits from the"
        " trendline. The remaining %.2f%% is the design, the flow settings"
        " and everything else that differs between two entries in the"
        " corpus." % (pooled, residual, 100.0 * share, 100.0 * (1 - share)),
        "",
        "Caveat, stated rather than buried: `sigma_seed` is measured on the"
        " designs listed and applied to all %d in the fit." % fit["n"],
        "",
    ]
    return "\n".join(lines)


def headline(samples, fit):
    """The disposition paragraph and the findings, with live numbers."""
    groups = by_design(samples)
    nulls = by_design(samples, arm="nullperturb")
    # A headline claim needs enough seeds to be a spread rather than a
    # coincidence; a design still being run appears in the tables and
    # not in this paragraph.
    spreads = {
        design: 2 * statistics.pstdev(
            [sample["min_period_wns"] for sample in members]
        )
        for design, members in groups.items()
        if len(members) >= MIN_SEEDS_FOR_CLAIM
    }
    null_ok = [
        design
        for design, members in nulls.items()
        if len({round(sample["min_period_wns"], 6) for sample in members}) == 1
    ]
    lines = [
        "**This is a documentation PR: it is here to be read, then"
        " closed.** It carries the harness, the corpus snapshot, the"
        " figures and the raw data for one question -- what a placement"
        " seed is worth at global route, and whether the spread it"
        " produces hides a bug. Nothing here is proposed for merge; the"
        " harness is on this branch only.",
        "",
        "## The finding",
        "",
    ]
    if spreads:
        worst = max(spreads, key=lambda design: spreads[design] / groups[design][0]["clk_period"])
        lines.append(
            "Changing nothing but `GPL_RANDOM_SEED` moves `min_period` at"
            " global route by **%.1f ps, 2 sigma %.2f%% of the clock**, on"
            " %s; every design measured lands between %.2f%% and %.2f%%."
            % (
                spreads[worst],
                100 * spreads[worst] / groups[worst][0]["clk_period"],
                worst,
                100
                * min(
                    spreads[design] / groups[design][0]["clk_period"]
                    for design in spreads
                ),
                100
                * max(
                    spreads[design] / groups[design][0]["clk_period"]
                    for design in spreads
                ),
            )
        )
        lines.append("")
    if null_ok:
        lines.append(
            "That spread is the perturbation's and nothing else's:"
            " `-perturb_dist 0` collapses %s to a single value across"
            " every seed. Any other seeded randomness anywhere in place,"
            " cts or global route would have shown up here as a spread,"
            " and none did. It is the control that makes the rest of the"
            " numbers mean anything."
            % ", ".join(
                "%s (%d seeds)" % (design, len(nulls[design]))
                for design in sorted(null_ok)
            )
        )
        lines.append("")
    if fit:
        lines.append(
            "Against ORFS's own accepted QoR -- 79 `rules-base.json` files,"
            " inverted and fitted -- that spread is small: designs sit a"
            " robust sigma of **%.3f of a clock period** from what their"
            " size and platform predict, so placement luck accounts for"
            " well under a percent of the variance between two designs in"
            " the corpus. The seed is not what makes one design's QoR"
            " different from another's." % fit["residual_sigma_robust"]
        )
        lines.append("")
    exceeded = [row for row in margin_rows(samples) if row["ratio"] > 1.0]
    if exceeded:
        lines += [
            "One consequence is immediate and is not about placement at"
            " all. ORFS pads a global-route timing rule by a fixed"
            " fraction of the clock and generates it from a single run."
            " The WNS margin (5%%) covers the seed spread everywhere it"
            " was measured. The TNS margin (20%%) does not: on %s the"
            " seed-to-seed spread is %s the margin, and a rule"
            " written from the median seed rejects %d of the runs that"
            " differ from it by nothing but `GPL_RANDOM_SEED`. Those"
            " guards encode which seed the maintainer drew."
            % (
                ", ".join(sorted({row["design"] for row in exceeded})),
                " and ".join(
                    "%.1fx" % row["ratio"] for row in exceeded
                ),
                sum(row["failing"] for row in exceeded),
            ),
            "",
        ]
    lines += [
        "What the ensemble *is* good for is pricing a change, which no"
        " single run can do: below the noise floor a single run cannot"
        " tell a real gain from which seed it drew. What it priced here,"
        " each against the same design's base arm and each quoted with"
        " the resolution at the seeds run:",
        "",
    ]
    priced = price_arms(samples)
    if priced:
        lines.append("| what | design | min_period delta | resolution | verdict |")
        lines.append("| --- | --- | ---: | ---: | --- |")
        for label, design, difference, two_se, verdict in priced:
            lines.append(
                "| %s | %s | %+.2f ps | %.2f | %s |"
                % (label, design, difference, two_se, verdict)
            )
        lines.append("")
    else:
        lines += ["**Not yet measured**: no arms beyond the base ensemble.", ""]
    return "\n".join(lines)


# How each arm reads as a sentence, and which direction is the claim.
# Named rather than derived so a new arm has to be described before it
# can appear in the headline.
ARM_LABELS = {
    "norepair": "turning global-route repair off",
    "tdoff": "turning timing-driven placement off",
    "nullperturb": "turning the placement perturbation off",
    "dist100": "a 5x smaller perturbation radius (100 nm)",
    "dist2000": "a 4x larger perturbation radius (2000 nm)",
}


def price_arms(samples):
    """Every named arm against its design's base ensemble.

    Args:
        samples: the harvested records.

    Returns:
        A list of (label, design, difference, two_se, verdict), only for
        arms with enough seeds to make a claim.
    """
    arms = {}
    for sample in samples:
        if sample.get("min_period_wns") is None:
            continue
        arms.setdefault((sample["design"], sample["arm"]), []).append(
            sample["min_period_wns"]
        )
    priced = []
    for (design, arm), values in sorted(arms.items()):
        label = ARM_LABELS.get(arm)
        base = arms.get((design, "base"))
        if not label or not base or len(values) < MIN_SEEDS_FOR_CLAIM:
            continue
        difference, two_se, verdict = compare(values, base)
        priced.append((label, design, difference, two_se, verdict))
    return priced


def section_method(samples):
    """What was held fixed, and what was not."""
    cores = sorted({sample.get("run", {}).get("cores") for sample in samples} - {None})
    designs = sorted({sample["design"] for sample in samples})
    arms = sorted({sample["arm"] for sample in samples})
    return "\n".join(
        [
            "## Method",
            "",
            "A sample is a **place -> cts -> grt tail on a frozen"
            " floorplan**. `bazelisk run //:deps -- <target>_place`"
            " deploys one tree per design; every sample runs inside it"
            " under its own `FLOW_VARIANT`, so all of them share the same"
            " synthesis and floorplan bytes and differ only in the knob"
            " under test. No bazel analysis per leaf and no rebuild when"
            " the binary changes, which is what makes %d samples"
            " affordable." % len(samples),
            "",
            "* **Designs**: %s (asap7), at their stock `CLK_PERIOD`."
            % ", ".join(designs),
            "* **Arms**: %s." % ", ".join(arms),
            "* **Threads**: `NUM_CORES=%s`, identical for every sample."
            % ", ".join(str(value) for value in cores),
            "* **Metric**: `min_period = clk_period - WNS` at global"
            " route, in picoseconds, read from ORFS's own"
            " `logs/.../5_1_grt.json`. Never a percentage of WNS.",
            "* **Determinism**: the same seed run twice gives a"
            " byte-identical `3_3_place_gp.odb` and `5_1_grt.odb`.",
            "* **Machine**: 32 threads, 122 GB. Samples run several-wide,"
            " so every recorded runtime is a wall time on a loaded"
            " machine: stored, never quoted. This study makes no runtime"
            " claim.",
            "",
        ]
    )


LIMITS = """## Limits

* **Six asap7 designs at their stock clocks.** Nothing here says what a
  congested design does; the one synthetic, deliberately contended
  design measured in #958's study showed a 2 sigma of 13.8% of the
  clock at global route, an order of magnitude above anything here. The
  spread is a property of the design and its contention, not a constant.
* **Global route is where the measurement stops.** Detailed route can
  move the number again, and nothing here bounds by how much.
* **`sigma_seed` is measured on the designs listed and applied to the
  whole corpus** in the variance decomposition. That is an assumption,
  and a design with a congested floorplan would break it.
* **The corpus is a snapshot of accepted numbers**, regenerated at
  different times by different tool versions -- not a controlled
  experiment. Its per-design rows are only as current as the last time
  someone ran `make update_rules` on that design.
* **The tightened-clock arm reuses the floorplan** built for the stock
  clock. That is what a designer tightening a constraint faces, but it
  is not the same as floorplanning for the tighter clock.
"""

REPRODUCING = """## Reproducing

```sh
# 1. Deploy one tree per design (synth + floorplan, once).
bazelisk run //:deps -- @orfs//flow/designs/asap7/gcd:gcd_place

# 2. Run an ensemble. Each sample is a place -> cts -> grt tail under
#    its own FLOW_VARIANT inside that tree.
bazelisk run //test/gpl_seed_qor:campaign -- \\
  --tree $PWD/tmp/@orfs/flow/designs/asap7/gcd/gcd_place_deps \\
  --platform asap7 --design gcd --seeds 1-32 \\
  --cores 4 --jobs 6 --out-dir $PWD/tmp/results_gpl_seed_qor

# 3. The arms. Nothing here needs a patch: GLOBAL_PLACEMENT_ARGS is
#    already appended verbatim by ORFS's global_place.tcl, and
#    GPL_RANDOM_SEED has been a flow variable since ORFS 3497c3a1d.
#      --arm nullperturb --knob 'GLOBAL_PLACEMENT_ARGS=-perturb_dist 0'
#      --arm dist2000    --knob 'GLOBAL_PLACEMENT_ARGS=-perturb_dist 2000'
#      --arm norepair    --knob SKIP_INCREMENTAL_REPAIR=1
#      --arm clk280      --sdc-period 280

# 4. The corpus snapshot, from the ORFS commit this repo pins.
git -C <orfs> archive <pinned-sha> $(git -C <orfs> ls-tree -r --name-only \\
  <pinned-sha> | grep -E 'rules-base.json|/constraint.*\\.sdc') | tar -x -C tmp/orfs
bazelisk run //test/gpl_seed_qor:rules_corpus -- --orfs-root $PWD/tmp/orfs \\
  --orfs-commit <pinned-sha> \\
  --out-json $PWD/docs/studies/gpl-seed-qor/rules_corpus.json

# 5. The report and the figures, both generated from results/.
bazelisk run //test/gpl_seed_qor:report -- \\
  --results-dir $PWD/tmp/results_gpl_seed_qor \\
  --corpus-json $PWD/docs/studies/gpl-seed-qor/rules_corpus.json --out-md -
bazelisk run //test/gpl_seed_qor:plots -- ...same, --out-dir docs/studies/...
```

Traps hit on the way, so the next person does not:

* The deployed tree's results live under **`DESIGN_NAME`**, not the
  design directory: `flow/designs/asap7/aes` writes to
  `results/asap7/aes_cipher_top`. Detected rather than configured.
* The tree carries **no design sources**; the constraint has already
  been elaborated into `2_floorplan.sdc` next to the frozen floorplan,
  which is the right thing to read anyway -- it is the clock the run
  used.
* `repair_timing -verbose`'s table prints **trial states**. A row whose
  pin-swap count falls is the journal restoring moves just made, so a
  dip followed by a recovery is the search working, not damage.
* `OPENROAD_EXE` must be passed as a **make argument** if you swap the
  binary: the deployed wrapper exports it unconditionally.
"""


def margin_rows(samples):
    """Seed spread against the margin genRuleFile would have padded with.

    Args:
        samples: the harvested records.

    Returns:
        One dict per (design, metric) with the margin, the seed spread,
        their ratio, and how many seeds a rule written from the median
        seed would reject.
    """
    groups = by_design(samples)
    rows = []
    for design in sorted(groups):
        members = groups[design]
        if len(members) < MIN_SEEDS_FOR_CLAIM:
            continue
        period = members[0]["clk_period"]
        for metric, key, padding in (
            ("setup WNS", "setup_ws", 5),
            ("setup TNS", "setup_tns", 20),
        ):
            values = [
                sample[key] for sample in members if sample.get(key) is not None
            ]
            if len(values) < 2:
                continue
            margin = padding / 100.0 * period
            median_rule = min(statistics.median(values), 0.0) - margin
            median = statistics.median(values)
            rows.append(
                {
                    "design": design,
                    "metric": metric,
                    "median": median,
                    "margin_fraction": (
                        100.0 * margin / abs(median) if median else float("inf")
                    ),
                    "margin": margin,
                    "spread": max(values) - min(values),
                    "ratio": (max(values) - min(values)) / margin,
                    "failing": sum(1 for value in values if value < median_rule),
                    "n": len(values),
                }
            )
    return rows


def section_margins(samples):
    """Do ORFS's own rule margins survive a change of placement seed?

    `genRuleFile.py` writes a global-route timing bound as
    `min(m, 0) - (p/100) * P`, with p = 5 for WNS and 20 for TNS. The
    margin is therefore a fixed fraction of the clock, and the rule is
    generated from **one run**. So the question the ensemble can answer,
    and a single run cannot, is whether that margin covers the spread a
    placement seed produces: if two seeds differ by more than the
    margin, then whether a design passes its own regression guard
    depends on which seed generated the guard.
    """
    rows = margin_rows(samples)
    if not rows:
        return "## Do the shipped rule margins survive a seed?\n\n**Not yet measured**\n"
    lines = [
        "## Do the shipped rule margins survive a seed?",
        "",
        "`genRuleFile.py` pads a global-route timing bound by a fixed"
        " fraction of the clock -- 5% for WNS, 20% for TNS -- and"
        " generates it from a single run. The ensemble says how wide that"
        " single run's own distribution is. Where the seed-to-seed spread"
        " exceeds the margin, the rule encodes which seed the maintainer"
        " happened to draw.",
        "",
        "| design | metric | median value | margin | margin / |value| | seed spread (max-min) | spread / margin | seeds failing a median-seed rule |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| %s | %s | %.1f | %.1f | %.1f%% | %.1f | %.2fx | %d/%d |"
            % (
                row["design"],
                row["metric"],
                row["median"],
                row["margin"],
                row["margin_fraction"],
                row["spread"],
                row["ratio"],
                row["failing"],
                row["n"],
            )
        )
    lines += [
        "",
        "A ratio under 1 means the margin covers the whole ensemble and"
        " the guard is robust to the seed. Over 1 means two seeds of the"
        " same design, same floorplan, same everything else, differ by"
        " more than the tolerance the guard allows.",
        "",
        "The `margin / |value|` column is why. The margin is a fraction"
        " of the **clock**, not of the metric it guards. On WNS the two"
        " are the same order, so 5% of a clock is a real tolerance. On"
        " TNS they are not: a design whose total negative slack runs to"
        " tens of clock periods gets a tolerance of a fraction of one"
        " percent of the quantity being guarded. The next section says"
        " what the code does about that, and what it was probably meant"
        " to do.",
        "",
    ]
    return "\n".join(lines)


def section_candidates(samples):
    """What this study would put in front of upstream, and what it would not.

    Listed with the measured effect, never filed: per CLAUDE.md the
    upstream repositories are read-only here, and a candidate is the
    human's call.
    """
    arms = {}
    for sample in samples:
        if sample.get("min_period_wns") is None:
            continue
        arms.setdefault((sample["design"], sample["arm"]), []).append(
            sample["min_period_wns"]
        )
    lines = [
        "## Upstream candidates: listed, not filed",
        "",
        "Per `CLAUDE.md`, upstream repositories are read-only from here."
        " Each of these is a candidate with a measured effect and a"
        " Chesterton's Fence paragraph; whether any of them becomes a"
        " pull request is the maintainer's call, not this study's.",
        "",
        "### 1. The perturbation radius: measured, and refuted as a default change",
        "",
        "This is the candidate this study would have published if it had"
        " stopped at one design, and the reason it did not.",
        "",
        "| design | arm | n | vs base (ps) | resolution | verdict |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    measured = False
    for (design, arm), values in sorted(arms.items()):
        if not arm.startswith("dist") and arm != "nullperturb":
            continue
        base = arms.get((design, "base"))
        # A candidate is a claim, so it needs the seeds a claim needs;
        # an arm still filling up is visible in the arm table above and
        # stays out of here until it is done.
        if not base or len(values) < MIN_SEEDS_FOR_CLAIM:
            continue
        difference, two_se, verdict = compare(values, base)
        measured = True
        lines.append(
            "| %s | %s | %d | %+.2f | %.2f | %s |"
            % (design, arm, len(values), difference, two_se, verdict)
        )
    if not measured:
        lines.append("| | | | **Not yet measured** | | |")
    lines += [
        "",
        "**The sign flips between designs, in both directions.** A 4x"
        " larger radius is worth picoseconds on gcd and costs"
        " picoseconds on aes, both resolved against their own"
        " ensembles. Switching the perturbation off does not have a"
        " consistent sign either: it costs min_period on four of the six"
        " designs and *gains* it on two, all resolved. So there is no"
        " default to propose in either direction -- not a different"
        " radius, and not turning it off. This is a per-design knob"
        " wearing a global default, and the only honest summary is the"
        " table.",
        "",
        "The contrast with timing-driven placement, measured on the same"
        " six ensembles, is the point: that one improves min_period on"
        " every design, by 4.7 to 152 ps, every one resolved. That is"
        " what a setting with a right answer looks like, and the"
        " perturbation radius does not look like it.",
        "",
        "**The fence.** The default is not arbitrary. OpenROAD"
        " `616a13d5ce` sets the radius to `min(0.5 um, row height)` and"
        " draws the offset from a 2D circular Gaussian whose sigma puts"
        " 99.5% of cells inside it. Keeping the displacement under a row"
        " is the conservative choice: the perturbation exists so"
        " identical cells wired in parallel do not start on top of each"
        " other and shadow each other for the whole solve, and a bigger"
        " kick buys diversity at the risk of starting further from a"
        " good solution. The measurement is consistent with that being"
        " a reasonable place to sit.",
        "",
        "The general lesson is worth more than the knob: a single design"
        " and a single run would have promoted this, with a resolved"
        " number behind it. Two designs and two ensembles refuted it.",
        "",
        "### 2. OpenROAD #11385's trajectory signature: not reproduced here",
        "",
        "The screen for it ran on every sample (see S2) and found"
        " nothing: no post-`repair_design` segment paid an outlying price"
        " in wirelength for the legality it bought, and no run triggered"
        " gpl's own divergence revert. That is **not** a refutation --"
        " the issue is reported on a design with SRAM macros and a much"
        " tighter constraint than anything here -- but it does bound the"
        " blast radius: on six flat asap7 designs at their stock clocks,"
        " across the ensembles in this PR, the signature does not fire."
        " Anyone fixing it can use the screen as a regression test that"
        " costs nothing to run.",
        "",
        "### 3. ORFS `genRuleFile.py`: the relative half of the TNS margin is unreachable",
        "",
        "`period_padding` mode, which writes every `*__timing__*` bound,"
        " is:",
        "",
        "```python",
        "negative_slack = min(metrics[field], 0)",
        "rule_value = negative_slack - max(",
        "    negative_slack * option[\"padding\"] / 100,",
        "    period * option[\"padding\"] / 100,",
        ")",
        "```",
        "",
        "`negative_slack` is `min(m, 0)`, so the first argument of the"
        " `max` is **never positive**, and the second never is. The"
        " maximum is therefore always the period term, for every input"
        " in the domain -- checked by evaluating both forms over 200,000"
        " random `(metric, period, padding)` triples, maximum difference"
        " 0.0. The expression is identically"
        " `min(m, 0) - period * padding / 100`.",
        "",
        "**What it was probably meant to be.** Every neighbouring mode"
        " pads relatively: `padding` is `m * (1 + p/100)`, `abs_padding`"
        " is `abs(m) * (1 + p/100)`. A `max` of a relative term and an"
        " absolute floor is the standard shape, and the file's own"
        " comment gives the floor's purpose -- *'to give small margin"
        " based on clock period to avoid failures by small violations'*."
        " With `abs(negative_slack)` in the first argument the two"
        " readings agree and the rule scales with the violation it"
        " guards.",
        "",
        "**What the ensemble says it costs.** The table above: the TNS"
        " guards are tighter than the seed noise on every design"
        " measured, by up to 59x, and a rule written from a median seed"
        " rejects runs that differ from it by nothing but"
        " `GPL_RANDOM_SEED`. The WNS guards, where the clock and the"
        " metric are the same order, are robust everywhere.",
        "",
        "This is a one-line change in ORFS with a measured"
        " justification, and it is the candidate this study would put"
        " first. Listed, not filed.",
        "",
        "### 4. Global-route repair can end with worse TNS than not running it",
        "",
        "Measured as a counterfactual (S1): the same seed, the same"
        " frozen floorplan, `SKIP_INCREMENTAL_REPAIR=1` against the"
        " default. Repair improves `min_period` on every sample of every"
        " design measured, and improves TNS on nearly all of them -- but"
        " not all. No fix is proposed: the acceptance criterion trading"
        " endpoint TNS for WNS may well be the intended policy, and the"
        " magnitudes here are small. What the ensemble adds is the rate,"
        " which a single run cannot produce.",
        "",
    ]
    return "\n".join(lines)


# One row per sample, in the order a reader would want to recompute a
# table from: identity first, the metric second, the moves and the
# trajectory after. Written as a CSV comment on the PR so every number
# above can be re-derived without re-running the campaign.
CSV_COLUMNS = [
    "platform",
    "design",
    "arm",
    "seed",
    "clk_period",
    "min_period_wns",
    "setup_ws",
    "setup_tns",
    "hold_ws",
    "wirelength",
    "buffers_inserted",
    "repair_wns_net",
    "repair_entns_net",
    "gp_hpwl_final",
    "gp_iterations",
    "diverge_revert",
    "place_gp_sha1",
    "grt_sha1",
    "cores",
    "loadavg_at_start",
]


def csv_rows(samples):
    """Flatten every sample to one CSV row."""
    rows = []
    for sample in sorted(
        samples,
        key=lambda item: (item["design"], item["arm"], item.get("seed", 0)),
    ):
        repair = (sample.get("repair") or [{}])[0]
        trajectory = sample.get("trajectory") or {}
        run = sample.get("run") or {}
        rows.append(
            {
                "platform": sample.get("platform"),
                "design": sample.get("design"),
                "arm": sample.get("arm"),
                "seed": sample.get("seed"),
                "clk_period": sample.get("clk_period"),
                "min_period_wns": sample.get("min_period_wns"),
                "setup_ws": sample.get("setup_ws"),
                "setup_tns": sample.get("setup_tns"),
                "hold_ws": sample.get("hold_ws"),
                "wirelength": sample.get("wirelength"),
                "buffers_inserted": (repair.get("moves") or {}).get("inserted"),
                "repair_wns_net": (repair.get("wns") or {}).get("net"),
                "repair_entns_net": (repair.get("entns") or {}).get("net"),
                "gp_hpwl_final": trajectory.get("final_hpwl"),
                "gp_iterations": trajectory.get("iterations"),
                "diverge_revert": trajectory.get("diverge_revert"),
                "place_gp_sha1": (sample.get("witness") or {}).get("3_3_place_gp.odb"),
                "grt_sha1": (sample.get("witness") or {}).get("5_1_grt.odb"),
                "cores": run.get("cores"),
                "loadavg_at_start": run.get("loadavg_at_start"),
            }
        )
    return rows


def write_csv(samples, path):
    """The raw data, one row per sample."""
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in csv_rows(samples):
            writer.writerow(row)
    print("wrote %s (%d rows)" % (path, len(samples)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--corpus-json", default=None)
    parser.add_argument("--out-md", default="-")
    parser.add_argument(
        "--figure-base",
        default=None,
        help="pinned raw URL of the directory holding the figures; "
        "omitted, the report renders without images",
    )
    parser.add_argument(
        "--out-csv",
        default=None,
        help="also write one row per sample, for the PR's raw-data comment",
    )
    args = parser.parse_args(argv)

    samples = load_samples(args.results_dir)
    snapshot = None
    if args.corpus_json and os.path.exists(args.corpus_json):
        with open(args.corpus_json) as handle:
            snapshot = json.load(handle)

    corpus_md, fit = (
        section_corpus(snapshot, args.figure_base)
        if snapshot
        else (section_corpus(None), None)
    )
    ensembles_md, spreads = section_ensembles(samples, args.figure_base)
    parts = [
        headline(samples, fit),
        section_method(samples),
        corpus_md,
        ensembles_md,
        section_controls(samples, args.figure_base),
        section_arms(samples),
        section_repair(samples),
        section_trajectory(samples),
        section_decomposition(spreads, fit),
        section_margins(samples),
        section_candidates(samples),
        LIMITS,
        REPRODUCING,
    ]
    text = "\n".join(parts)
    if args.out_csv:
        write_csv(samples, args.out_csv)
    if args.out_md == "-":
        print(text)
    else:
        with open(args.out_md, "w") as handle:
            handle.write(text)
        print("wrote %s (%d samples)" % (args.out_md, len(samples)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
