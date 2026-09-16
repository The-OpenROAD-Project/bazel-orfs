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
CORE_ONLY_COREMARK_PER_JOULE = {
    "serv": 5190.0,
    "picorv32": 86024.0,
    "ibex": 277510.0,
}

COMMODITY_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "results",
    "commodity_coremark.csv",
)


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
    lines = [head, "|---" * (10 if split else 8) + "|"]
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
        lines.append(row)
    return "\n".join(lines)


def _ratio(a, b, digits):
    return "{:.{d}f}x".format(a / b, d=digits)


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
    for key, value in facts(document).items():
        print("{:36s} {}".format(key, value))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
