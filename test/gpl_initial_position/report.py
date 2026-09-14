"""Generate the study's tables from whatever `results/` happens to hold.

The report **discovers** samples; no result is a declared input of any
build rule. Two consequences are deliberate:

* With `results/` empty, this fails with "run the campaign first"
  instead of printing an empty study.
* A section with no samples renders **"Not yet measured"** rather than
  being omitted, so a partial campaign can never read as a complete one.

Adding an arm, a design or more seeds changes the tables by being run.
Nothing here is edited by hand, because a table typed by hand rots the
first time the campaign is re-run.

## What is dropped, and why that is printed

A sample is used only when the arm its log attests to matches the arm
the campaign asked for. A mode flag that never reached the command line
produces a clean, fast, entirely normal run whose numbers are identical
to the default's -- which would read as "this distribution does
nothing". Dropped samples are counted in the report, so a silently
ineffective arm shows up as a missing arm rather than as a null result.
"""

import argparse
import collections
import glob
import json
import os
import sys

import campaign
import stats

# The endpoints, in order of how much of the flow stands between the
# change and the measurement. `lower_is_better` drives nothing but the
# wording of a verdict.
ENDPOINTS = [
    ("gp_hpwl_final", "global-place HPWL (um)", True),
    ("gp_iterations", "global-place iterations", True),
    ("min_period_wns", "min_period = clk - WNS", True),
    ("setup_tns", "setup TNS at grt", False),
    ("wirelength", "global-route wirelength", True),
    ("grt_overflow", "global-route overflow", True),
]


def load(results_dir):
    """Every sample JSON under `results_dir`.

    Args:
        results_dir: a directory of per-sample JSON files.

    Returns:
        (samples, dropped) where `dropped` lists the (design, arm, seed,
        witnessed) tuples whose log did not attest to the arm they were
        run as.

    Raises:
        SystemExit: when the directory is absent or empty.
    """
    paths = sorted(glob.glob(os.path.join(results_dir, "*.json")))
    if not paths:
        sys.exit(
            "no samples in %s -- run the campaign first:\n"
            "  bazelisk run //test/gpl_initial_position:campaign -- --help"
            % results_dir
        )
    samples = []
    dropped = []
    for path in paths:
        with open(path) as handle:
            record = json.load(handle)
        expected = record.get("arm")
        witnessed = record.get("arm_witnessed")
        if expected == campaign.BASELINE_ARM:
            agreed = witnessed == "shipped"
        else:
            agreed = witnessed == expected
        if not agreed:
            dropped.append(
                (
                    record.get("design"),
                    expected,
                    record.get("seed"),
                    witnessed,
                )
            )
            continue
        samples.append(record)
    return samples, dropped


def by_design_arm(samples, key):
    """Group one endpoint's values by design and arm.

    Args:
        samples: from load().
        key: the endpoint field.

    Returns:
        {design: {arm: [values]}}, skipping samples where the endpoint
        is None -- a run that did not reach global route contributes to
        the place-stage endpoints and to nothing else.
    """
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for record in samples:
        value = record.get(key)
        if value is None:
            continue
        design = "%s/%s" % (record.get("platform"), record.get("design"))
        out[design][record["arm"]].append(float(value))
    return out


def _fmt(value, places=3):
    if value is None:
        return "-"
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return "-"
        return "%.*f" % (places, value)
    return str(value)


def section_not_measured(title, why):
    """A section with no data, rendered as such.

    Args:
        title: the heading.
        why: what would have to be run.

    Returns:
        The markdown.
    """
    return "## %s\n\n**Not yet measured.** %s\n" % (title, why)


def initial_place_table(samples):
    """Does the conjugate-gradient initial place converge, per design?

    The start position is the initial guess of an iterative solve whose
    matrix is re-linearised from the current positions each outer
    iteration. Where the loop converges the guess washes out; where it
    hits the cap the guess is a free parameter carried into Nesterov.
    Which regime a design is in is a precondition for reading any other
    table here, and it costs nothing.

    Args:
        samples: from load().

    Returns:
        The markdown section.
    """
    rows = collections.defaultdict(list)
    for record in samples:
        conv = record.get("initial_place")
        if conv:
            rows["%s/%s" % (record["platform"], record["design"])].append(conv)
    if not rows:
        return section_not_measured(
            "Does initial place converge?",
            "No sample carried an initial-place trajectory; run any arm.",
        )
    out = [
        "## Does initial place converge?",
        "",
        "`doBicgstabPlace()` breaks when `residual <= 1e-5 && iter >= 5`, "
        "against an `-initial_place_max_iter` cap of 20.",
        "",
        "| design | samples | iterations | final residual | converged | hit the cap |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for design in sorted(rows):
        group = rows[design]
        iters = [row["last_iteration"] for row in group]
        residuals = [
            row["final_residual"] for row in group if row["final_residual"] is not None
        ]
        converged = sum(1 for row in group if row["converged"])
        capped = sum(1 for row in group if row["hit_cap"])
        out.append(
            "| %s | %d | %d-%d | %s | %d | %d |"
            % (
                design,
                len(group),
                min(iters),
                max(iters),
                ("%.2e" % max(residuals)) if residuals else "-",
                converged,
                capped,
            )
        )
    return "\n".join(out) + "\n"


def position_source_table(samples):
    """Where the two global placement calls take their start from.

    ORFS appends `-force_center_initial_place` at `3_3_place_gp` and not
    at `3_1_place_gp_skip_io`, so the counters differ between the two
    calls in a way nobody chose deliberately. This prints both.

    Args:
        samples: from load().

    Returns:
        The markdown section.
    """
    rows = {}
    for record in samples:
        if record.get("arm") != campaign.BASELINE_ARM:
            continue
        design = "%s/%s" % (record["platform"], record["design"])
        if design in rows:
            continue
        rows[design] = (
            record.get("position_sources_skip_io"),
            record.get("position_sources"),
        )
    if not rows:
        return section_not_measured(
            "Where each global placement call starts from",
            "No `%s` sample present; run the baseline arm."
            % campaign.BASELINE_ARM,
        )
    out = [
        "## Where each global placement call starts from",
        "",
        "GPL-0051's own counters, on the baseline arm.",
        "",
        "| design | 3_1 odb | 3_1 core | 3_3 odb | 3_3 core |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for design in sorted(rows):
        skip_io, main = rows[design]
        out.append(
            "| %s | %s | %s | %s | %s |"
            % (
                design,
                _fmt(skip_io and skip_io["odb"]),
                _fmt(skip_io and skip_io["core_center"]),
                _fmt(main and main["odb"]),
                _fmt(main and main["core_center"]),
            )
        )
    return "\n".join(out) + "\n"


def endpoint_section(samples, key, label, lower_is_better):
    """One endpoint: per-design arms, then the pooled verdict per arm.

    Args:
        samples: from load().
        key: the endpoint field.
        label: its human name.
        lower_is_better: wording only.

    Returns:
        The markdown section.
    """
    grouped = by_design_arm(samples, key)
    if not grouped:
        return section_not_measured(
            label, "No sample carries `%s`; run the tier that produces it." % key
        )

    out = ["## %s" % label, ""]
    out.append(
        "Each arm against `%s`, per design. The resolution is twice the "
        "standard error of the difference; inside it the verdict is "
        "**did not resolve**, which is not the same as no effect."
        % campaign.BASELINE_ARM
    )
    out.append("")
    out.append(
        "| design | arm | n | mean | delta vs %s | resolution | verdict |"
        % campaign.BASELINE_ARM
    )
    out.append("| --- | --- | ---: | ---: | ---: | ---: | --- |")

    per_arm = collections.defaultdict(list)
    for design in sorted(grouped):
        arms = grouped[design]
        baseline = arms.get(campaign.BASELINE_ARM)
        if not baseline or len(baseline) < 2:
            continue
        out.append(
            "| %s | %s | %d | %s | - | - | baseline |"
            % (design, campaign.BASELINE_ARM, len(baseline), _fmt(stats.mean(baseline)))
        )
        for arm in sorted(arms):
            if arm == campaign.BASELINE_ARM:
                continue
            row = stats.compare(baseline, arms[arm])
            per_arm[arm].append(row)
            out.append(
                "| %s | %s | %d | %s | %s | %s | %s |"
                % (
                    design,
                    arm,
                    len(arms[arm]),
                    _fmt(row["arm"]["mean"]),
                    _fmt(row["delta"]),
                    _fmt(row["resolution"]),
                    row["verdict"],
                )
            )

    if not per_arm:
        return "\n".join(out) + "\n\n_No design has a baseline ensemble of two or " \
            "more samples, so nothing can be compared yet._\n"

    arms_tested = len(per_arm)
    out += [
        "",
        "### Pooled verdict",
        "",
        "An arm is a finding only when at least `required` designs resolve "
        "in the same direction. The threshold is chosen so the family-wise "
        "false-positive rate over all %d arms stays under 1%%." % arms_tested,
        "",
        "| arm | designs | resolved | same direction | required | verdict | family error |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    direction_word = {"better": "better", "worse": "worse"}
    if not lower_is_better:
        direction_word = {"better": "worse", "worse": "better"}
    for arm in sorted(per_arm):
        out_v = stats.verdict(per_arm[arm], arms=arms_tested)
        label_v = direction_word.get(out_v["label"], out_v["label"])
        out.append(
            "| %s | %d | %d | %d | %d | %s | %.4f |"
            % (
                arm,
                out_v["designs"],
                out_v["resolved"],
                out_v["agree"],
                out_v["required"],
                label_v,
                out_v["family_error"],
            )
        )
    return "\n".join(out) + "\n"


def witness_section(samples, dropped):
    """What was run, and what was thrown away.

    Args:
        samples: the kept samples.
        dropped: from load().

    Returns:
        The markdown section.
    """
    counts = collections.Counter(
        ("%s/%s" % (r["platform"], r["design"]), r["arm"]) for r in samples
    )
    out = [
        "## Samples, and the ones discarded",
        "",
        "A sample counts only when the arm its log attests to matches the "
        "arm it was run as.",
        "",
        "| design | arm | samples |",
        "| --- | --- | ---: |",
    ]
    for (design, arm) in sorted(counts):
        out.append("| %s | %s | %d |" % (design, arm, counts[(design, arm)]))
    out += ["", "Discarded: **%d**." % len(dropped)]
    if dropped:
        out += [
            "",
            "| design | asked for | seed | log attested |",
            "| --- | --- | ---: | --- |",
        ]
        for design, arm, seed, witnessed in sorted(
            dropped, key=lambda row: tuple(str(x) for x in row)
        ):
            out.append("| %s | %s | %s | %s |" % (design, arm, seed, witnessed))
    return "\n".join(out) + "\n"


def noise_floor_table(samples):
    """This campaign's own measured spread, per design and endpoint.

    Quoted rather than inherited: PR #977 measured the seed noise on six
    asap7 designs on this host, and those numbers sized this campaign,
    but an arm's resolution has to come from the ensembles actually run.
    The two are compared in the PR body; only this one is a measurement
    of this campaign.

    Args:
        samples: from load().

    Returns:
        The markdown section.
    """
    rows = []
    for key, label, _ in ENDPOINTS:
        grouped = by_design_arm(samples, key)
        for design in sorted(grouped):
            baseline = grouped[design].get(campaign.BASELINE_ARM, [])
            if len(baseline) < 2:
                continue
            mean = stats.mean(baseline)
            two_sigma = 2 * stats.stdev(baseline)
            rows.append(
                (
                    design,
                    label,
                    len(baseline),
                    mean,
                    two_sigma,
                    (100.0 * two_sigma / mean) if mean else None,
                )
            )
    if not rows:
        return section_not_measured(
            "The noise floor this campaign measured",
            "No baseline ensemble of two or more samples yet.",
        )
    out = [
        "## The noise floor this campaign measured",
        "",
        "The `%s` arm's own spread. Resolution at `k` seeds is "
        "`2sigma * sqrt(2/k)`; every delta above is judged against it."
        % campaign.BASELINE_ARM,
        "",
        "| design | endpoint | n | mean | 2 sigma | 2 sigma as %% of mean |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for design, label, n, mean, two_sigma, pct in rows:
        out.append(
            "| %s | %s | %d | %s | %s | %s |"
            % (design, label, n, _fmt(mean), _fmt(two_sigma), _fmt(pct, 2))
        )
    return "\n".join(out) + "\n"


def summary_table(samples):
    """One row per arm, one column per endpoint: the answer, in brief.

    This is the table the question is actually asking for. Everything
    below it in the report is the working.

    Args:
        samples: from load().

    Returns:
        The markdown section.
    """
    verdicts = {}
    endpoints_present = []
    for key, label, lower in ENDPOINTS:
        grouped = by_design_arm(samples, key)
        per_arm = collections.defaultdict(list)
        for design in sorted(grouped):
            baseline = grouped[design].get(campaign.BASELINE_ARM)
            if not baseline or len(baseline) < 2:
                continue
            for arm, values in grouped[design].items():
                if arm == campaign.BASELINE_ARM:
                    continue
                per_arm[arm].append(stats.compare(baseline, values))
        if not per_arm:
            continue
        endpoints_present.append(label)
        arms_tested = len(per_arm)
        for arm, rows in per_arm.items():
            out = stats.verdict(rows, arms=arms_tested)
            word = out["label"]
            if not lower and word in ("better", "worse"):
                word = "worse" if word == "better" else "better"
            verdicts[(arm, label)] = "%s %d/%d" % (word, out["agree"], out["designs"])
    if not verdicts:
        return section_not_measured(
            "Summary: does the starting distribution matter?",
            "No arm has an ensemble to compare against the baseline yet.",
        )
    arms = sorted({arm for arm, _ in verdicts})
    out = [
        "## Summary: does the starting distribution matter?",
        "",
        "Each cell is the pooled verdict and the number of designs that "
        "resolved in the winning direction. **did not resolve** is not "
        "the same as no effect; **underpowered** means the design count "
        "cannot support any verdict at all.",
        "",
        "| arm | " + " | ".join(endpoints_present) + " |",
        "| --- | " + " | ".join("---" for _ in endpoints_present) + " |",
    ]
    for arm in arms:
        cells = [verdicts.get((arm, label), "-") for label in endpoints_present]
        out.append("| %s | %s |" % (arm, " | ".join(cells)))
    return "\n".join(out) + "\n"


def build(results_dir):
    """The whole report.

    Args:
        results_dir: a directory of per-sample JSON files.

    Returns:
        The markdown.
    """
    samples, dropped = load(results_dir)
    parts = [
        "# Where global placement starts from, and whether it matters",
        "",
        "Generated from %d samples in `%s`. Every number here is "
        "recomputed from the sample JSONs; nothing is typed by hand."
        % (len(samples), os.path.basename(os.path.abspath(results_dir))),
        "",
        summary_table(samples),
        witness_section(samples, dropped),
        initial_place_table(samples),
        position_source_table(samples),
        noise_floor_table(samples),
    ]
    for key, label, lower in ENDPOINTS:
        parts.append(endpoint_section(samples, key, label, lower))
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", default=None, help="default: stdout")
    args = parser.parse_args(argv)
    text = build(args.results)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as handle:
            handle.write(text)
        print("wrote %s" % args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
