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
import json
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


def render_table1(document):
    lines = [
        "| core | ISA | CoreMark/MHz | cycles/iter | f (MHz) | P (SAIF) "
        "| CoreMark/Joule | memory inside the boundary |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in ordered(document):
        lines.append(
            "| {name} | {isa} | {cmmhz:.4f} | {cycles:,} | {f:.1f} | "
            "{p:.1f} mW | {cmj:,.0f} | {mem} |".format(
                name=NAMES[p["core"]],
                isa=p["isa"],
                cmmhz=p["coremark_per_mhz"],
                cycles=p["cycles_per_iteration"],
                f=p["frequency_mhz"],
                p=p["power_w"] * 1e3,
                cmj=p["coremark_per_joule"],
                mem=memory_inside(p),
            )
        )
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
