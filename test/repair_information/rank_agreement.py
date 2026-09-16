"""How much does one parasitics model disagree with another about *which*
endpoints are critical?

The study's hypothesis is that `repair_timing` at global route does
better than the earlier repairs because it is handed better information.
That hypothesis has a necessary condition which is far cheaper to test
than the conclusion: the information has to be *different*. A repair
handed the same ranking of endpoints spends its budget on the same
endpoints, and then the quality of the numbers behind that ranking
cannot change what it does.

So the primary statistic here is rank agreement against a reference
instrument (the extracted SPEF of the routed design), not error in
picoseconds. A model can be wrong about every slack by a constant and
still rank perfectly, in which case it is a perfectly good repair driver
and a terrible timing signoff -- and the flow only uses it as the former.

Three numbers per comparison, and they answer different questions:

  * `spearman`  -- agreement over the whole endpoint set. Sensitive to
    the bulk, which is mostly slack the repair will never touch.
  * `top_k_overlap` -- of the k endpoints the reference says are worst,
    how many does the candidate also put in its worst k. This is the one
    that matters: repair works on the worst endpoints, so the top of the
    list *is* the information.
  * `missed` -- reference-critical endpoints the candidate ranks outside
    its top k. These are the paths a repair driven by the candidate
    never looks at. If this is zero, better information buys nothing.

Slack error is reported too, but as a diagnostic: it is what a signoff
cares about and it is not what drives a decision.
"""

import argparse
import json
import math
from pathlib import Path


def load_probe(path):
    """One probe's opinion: {endpoint: slack}, plus its metadata."""
    data = json.loads(Path(path).read_text())
    slacks = {row["endpoint"]: float(row["slack"]) for row in data["endpoints"]}
    if not slacks:
        raise SystemExit(f"{path}: no endpoints; the probe measured nothing")
    return data, slacks


def ranks(values):
    """Ascending ranks with ties averaged.

    Ties are not a curiosity here: a design with a wide plateau of
    equal-slack endpoints (common when a clock is loose) would otherwise
    have its agreement decided by the order the search happened to emit
    them in, which is not a property of the parasitics model.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = mean_rank
        i = j + 1
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        # A constant column has no ranking to agree with. Reported as
        # undefined rather than as 0.0, which would read as "disagrees".
        return None
    return sxy / math.sqrt(sxx * syy)


def spearman(a, b, common):
    xs = ranks([a[e] for e in common])
    ys = ranks([b[e] for e in common])
    return pearson(xs, ys)


def worst_k(slacks, common, k):
    return set(sorted(common, key=lambda e: slacks[e])[:k])


def compare(reference, candidate, k_fractions=(0.01, 0.05, 0.10), k_absolute=(10, 50)):
    """Candidate against reference, over the endpoints both report.

    Endpoints are compared on the intersection because the two probes may
    have run on different stages of the same design: buffering changes
    instances and nets, but a register's data pin survives, so the
    intersection is large and the difference is worth reporting rather
    than hiding.
    """
    common = sorted(set(reference) & set(candidate))
    if not common:
        raise SystemExit("no endpoints in common: these probes are not comparable")

    result = {
        "endpoints_reference": len(reference),
        "endpoints_candidate": len(candidate),
        "endpoints_common": len(common),
        "spearman": spearman(reference, candidate, common),
        "top_k": [],
    }

    # Fractional k scales with the design; absolute k keeps the
    # statistic readable on a small one, where "the worst 1%" can be a
    # single endpoint and an overlap of 1/1 says nothing at all.
    ks = [
        ("{:.0%}".format(f), max(1, int(round(f * len(common))))) for f in k_fractions
    ]
    ks += [("top{}".format(k), k) for k in k_absolute if k <= len(common)]

    for label, k in ks:
        ref_worst = worst_k(reference, common, k)
        cand_worst = worst_k(candidate, common, k)
        hit = len(ref_worst & cand_worst)
        result["top_k"].append(
            {
                "label": label,
                "k": k,
                "overlap": hit,
                "overlap_percent": 100.0 * hit / k,
                "missed": sorted(ref_worst - cand_worst)[:20],
                "missed_count": k - hit,
            }
        )

    errs = [candidate[e] - reference[e] for e in common]
    mean = sum(errs) / len(errs)
    var = sum((e - mean) ** 2 for e in errs) / len(errs) if len(errs) > 1 else 0.0
    result["slack_error"] = {
        "mean": mean,
        "two_sigma": 2.0 * math.sqrt(var),
        "max_abs": max(abs(e) for e in errs),
    }
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--reference",
        required=True,
        help="the probe JSON treated as truth, normally the spef one",
    )
    ap.add_argument(
        "--candidate",
        required=True,
        action="append",
        help="a probe JSON to score against the reference; repeatable",
    )
    ap.add_argument("--out", help="write the comparison JSON here")
    args = ap.parse_args()

    ref_meta, ref_slacks = load_probe(args.reference)
    out = {
        "reference": {
            "arm": ref_meta["arm"],
            "stage": ref_meta["stage"],
            "parasitics": ref_meta["parasitics"],
            "min_period": ref_meta["min_period"],
        },
        "candidates": [],
    }

    for path in args.candidate:
        meta, slacks = load_probe(path)
        row = compare(ref_slacks, slacks)
        row.update(
            {
                "arm": meta["arm"],
                "stage": meta["stage"],
                "parasitics": meta["parasitics"],
                "grt_args": meta.get("grt_args", ""),
                "seconds": meta.get("seconds"),
                "nets_with_guides": meta.get("nets_with_guides"),
                "min_period": meta["min_period"],
                "propagated_clock": meta.get("propagated_clock"),
            }
        )
        out["candidates"].append(row)

    text = json.dumps(out, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
