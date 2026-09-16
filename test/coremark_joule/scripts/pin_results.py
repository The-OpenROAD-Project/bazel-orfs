#!/usr/bin/env python3
"""Write every measured point into results.json, in the source tree.

The measurements are expensive -- a gate-level CoreMark run is minutes
per core -- and the presentation is not. Iterating on a plot should not
re-run a flow, so the numbers are pinned into a committed file and the
plot reads only that. Same split as the floorplan derivation: bazel
caches the deriving, a `run` target writes the result where a human can
read it in a diff, and nothing downstream needs the flow at all.

It also makes the data reviewable. A number that changes shows up as a
line in a pull request, next to the commit that changed it, rather than
living in an output directory nobody keeps.

Usage (via the generated target):
    bazelisk run //test/coremark_joule:pin
    bazelisk run //test/coremark_joule:pin -- --table   # the §4.9 table, no write

The literature rows live here too (LITERATURE), one schema for every
paper, checked by check_literature and pin_results_test.
"""

import argparse
import json
import re
import math
import os
import sys

# Where the pinned file lives, relative to the workspace root. bazel run
# sets BUILD_WORKSPACE_DIRECTORY to the source tree, which is the only
# place writing is meaningful -- the runfiles copy is read-only and
# discarded.
RESULTS = "test/coremark_joule/results.json"

# A second series from the literature: cores implemented in
# GlobalFoundries 22 FDX, drawn as its own series because it is not
# like-for-like with the asap7 points -- different process, different
# tools, different stage, different corner, and a boundary the source
# does not state.
#
# CoreMark/Joule is *derived* from the paper's own figures:
#   score = CoreMark/MHz * f,  CoreMark/Joule = score / power
# with power taken near each core's maximum frequency (Figure 7) and
# CoreMark/MHz from its Table. Nothing is scaled between nodes.
#
# Two things the derivation carries that are worth stating where the
# numbers live rather than only in the paper:
#
# - The boundary is not stated by the source. The cores are configured
#   with 64 KB two-way L1 I and D caches, but Figure 7's breakdown names
#   Fetch, Decode, Issue, Integer Execution, Load/Store Unit, Floating
#   Point and Control Flow, and no cache term appears in it. Whether the
#   reported core power includes the L1s cannot be determined from the
#   paper, so it is recorded here as unstated rather than assumed.
# - The power is measured on matmult-int, not on CoreMark. The paper
#   states its power numbers for that benchmark. So a derived
#   CoreMark/Joule combines a CoreMark performance number with a
#   matmult-int power number, and is an estimate of the paper's energy
#   efficiency rather than a figure the paper reports.
_CF25 = "Ramping Up Open-Source RISC-V Cores, ACM CF'25 (arXiv:2505.24363)"

# What every entry in LITERATURE shares, so a reader of results.json
# does not have to find the paper to know what the number is.
_CF25_PROVENANCE = {
    "process": "GF 22 FDX",
    "boundary": "not stated by the source; 64 KB two-way L1 I/D configured, "
    "but Figure 7's breakdown names only pipeline units",
    "power_benchmark": "matmult-int (not CoreMark)",
    "corner": "0.8 V, TT, 25 C, RC typical",
    "tool": "Synopsys PrimeTime 2022.03, post-layout netlist simulation",
    "derivation": "CoreMark/Joule = CoreMark/MHz * f / power, computed here",
    "source": _CF25,
    "locator": "Table 2 (CoreMark/MHz), Figure 4 (fmax, TT 0.8 V), "
    "Figure 6 (kGE), Figure 7 (power)",
    # Figure 6 gives a total kGE and the two L1 bars; the core figure is
    # the total with both caches taken out, so the kGE compares with a
    # core-only count and not with anything carrying an SRAM.
    "kge_boundary": "core without L1s: Figure 6 total minus its Icache "
    "and Dcache bars",
    "fmax_kind": "signoff",
    "confidence": "derived",
}

# The literature rows are one schema, whatever the paper. A field a
# source does not give is None, never a guess, and `confidence` says
# what kind of number the row is:
#   stated     the source prints the number
#   derived    arithmetic on the source's own figures, done here
#   estimated  the source itself calls it an estimate or a target
# `fmax_kind` says what a frequency is a frequency *of*: silicon,
# a signoff at a stated corner, a synthesis-only number, or a target the
# author announced. Those are four different quantities and the table
# is only honest if it says which one each cell is.
LITERATURE_FIELDS = (
    "name",
    "source",
    "cite",
    "locator",
    "process",
    "boundary",
    "confidence",
    "coremark_per_mhz",
    "kge",
    "fmax_mhz",
    "fmax_kind",
    "power_w",
    "coremark_per_joule",
)
CONFIDENCE = ("stated", "derived", "estimated")
FMAX_KINDS = ("silicon", "signoff", "synthesis", "target", None)


def _row(base, **fields):
    row = dict(base)
    row.update(fields)
    for k in LITERATURE_FIELDS:
        row.setdefault(k, None)
    return row


_NONE = {"process": None, "boundary": None, "fmax_kind": None}

LITERATURE = [
    _row(
        _CF25_PROVENANCE,
        name="CVA6",
        cite="[5]",
        coremark_per_mhz=2.19,
        frequency_mhz=900.0,
        power_w=0.06988,
        coremark_per_joule=2.19 * 900.0 / 0.06988,
        kge=2282 - 804 - 748,
        fmax_mhz=1083.0,
    ),
    _row(
        _CF25_PROVENANCE,
        name="CVA6S+",
        cite="[5]",
        coremark_per_mhz=2.84,
        frequency_mhz=900.0,
        power_w=0.09429,
        coremark_per_joule=2.84 * 900.0 / 0.09429,
        kge=2408 - 805 - 752,
        fmax_mhz=1081.0,
    ),
    _row(
        _CF25_PROVENANCE,
        name="XuanTie C910",
        cite="[5]",
        coremark_per_mhz=4.86,
        frequency_mhz=1300.0,
        power_w=0.21481,
        coremark_per_joule=4.86 * 1300.0 / 0.21481,
        kge=3992 - 692 - 626,
        fmax_mhz=1543.0,
        # Two published CoreMark/MHz for the same core, 1.5x apart. The
        # SonicBOOM paper's Figure 7 is a compilation of vendor numbers;
        # CF'25 ran the benchmark. The gap is the size of the compiler
        # and flag freedom CoreMark leaves open.
        also_reported={
            "coremark_per_mhz": 7.1,
            "source": "SonicBOOM, CARRV 2020, Figure 7 (vendor-reported)",
        },
    ),
    _row(
        _NONE,
        name="Ariane (CVA6 ancestor)",
        cite="[6]",
        source="The Cost of Application-Class Processing, IEEE TVLSI 2019 "
        "(arXiv:1904.05442)",
        locator="Figure 5 (kGE at 1.5 ns), Figure 4 (silicon fmax vs "
        "supply), Section IV-A (signoff), Table III (energy per op)",
        process="GF 22 FDX",
        boundary="core without caches for the kGE; 16 KB 4-way I$ and "
        "32 KB 8-way D$ on the die",
        confidence="stated",
        kge=210,
        fmax_mhz=1700.0,
        fmax_kind="silicon",
        fmax_note="1.7 GHz measured at 1.15 V; sign-off 902 MHz at 0.72 V, "
        "125 C, SSG",
        dmips_per_mhz=1.65,
        energy_per_op_pj=(21.6, 51.8),
    ),
    _row(
        _NONE,
        name="XiangShan Kunminghu V2",
        cite="[14]",
        source="XiangShan KMH: An Open Source RISC-V Core with >15/GHz for "
        "SPECCPU2006, Y. Bao, 14 May 2025 (project slides)",
        locator="slide 10 (tape-out status: 7 nm, area, power, max core "
        "frequency), slide 9 (SPEC CPU2006 per GHz), slide 7 (uarch)",
        process="7 nm (foundry not named on the slide)",
        boundary="core + 1 MB L2 for area and power; the benchmark the "
        "power was taken on is not stated",
        confidence="stated",
        fmax_mhz=3000.0,
        fmax_kind="signoff",
        fmax_note="'Max core Freq 3.0 GHz', design 'ready to tape-out'",
        area_mm2=(1.8, 2.1),
        power_w=(1.6, 1.9),
        spec2006_per_ghz=14.7,
        # 6-wide rename, 13-stage, ROB 160 x 6, 64 KB 4-way I$, 64 KB
        # 8-way D$ (slide 7). The core measured in this study is
        # Kunminghu V3, which the same deck puts ~30 % above V2 on SPEC
        # CPU2006 (slide 11); no V3 area or power is published.
        note="V2 figures; this study builds V3",
    ),
    _row(
        _NONE,
        name="XiangShan Nanhu V2",
        cite="[14]",
        source="XiangShan KMH slides, Y. Bao, 14 May 2025",
        locator="slide 10 (NHv2 taped out: 2.5 GHz, SPEC CPU2006 ~10/GHz), "
        "slide 6 (14 nm)",
        process="14 nm",
        boundary="not stated",
        confidence="stated",
        fmax_mhz=2500.0,
        fmax_kind="silicon",
        spec2006_per_ghz=10.0,
    ),
    _row(
        _NONE,
        name="SonicBOOM",
        cite="[15]",
        source="SonicBOOM: The 3rd Generation Berkeley Out-of-Order Machine, "
        "CARRV 2020",
        locator="Section 5 (CoreMark/MHz, synthesis at 1 GHz), Figure 7 "
        "(comparison chart)",
        process="commercial FinFET, node not named",
        boundary="core; 32 KB L1s configured; no area or power reported",
        confidence="stated",
        coremark_per_mhz=6.2,
        fmax_mhz=1000.0,
        fmax_kind="synthesis",
        dmips_per_mhz=3.93,
    ),
    _row(
        _NONE,
        name="ibex (small)",
        cite="[16]",
        source="lowRISC ibex README, performance/area table",
        locator="README table, row 'small' (RV32IMC, 3-cycle multiplier)",
        process="yosys basic synthesis flow, latch-based register file; "
        "the README's 'Yosys kGE' column",
        boundary="core only, no memories",
        confidence="stated",
        coremark_per_mhz=2.47,
        kge=26.60,
        # This study builds ibex with RegFileFF (flops), the README's
        # kGE is with the latch-based file; the two are not the same
        # netlist and the flop file is the larger.
        note="kGE is for the latch register file; this study hardens RegFileFF",
    ),
    _row(
        _NONE,
        name="SERV",
        cite="[17]",
        source="olofk/serv README",
        locator="README 'Size' table, 'typical CMOS process' row",
        process="not named ('a typical CMOS process')",
        boundary="core only, most minimal configuration",
        confidence="stated",
        kge=2.1,
        note="no CoreMark/MHz is published; the README gives LUT and FF counts",
    ),
    _row(
        _NONE,
        name="picorv32",
        cite="[18]",
        source="YosysHQ/picorv32 README",
        locator="README 'Performance' and 'Size' sections",
        process="Xilinx 7-series LUTs only; no ASIC area published",
        boundary="core only",
        confidence="stated",
        dmips_per_mhz=0.516,
        note="no CoreMark/MHz and no gate count are published; 0.516 "
        "DMIPS/MHz with ENABLE_FAST_MUL, ENABLE_DIV and BARREL_SHIFTER",
    ),
    _row(
        _NONE,
        name="VeeR EH1",
        cite="[11], [19]",
        source="Western Digital SweRV Core EH1 announcement, December 2018; "
        "CoreMark Benchmarking for SweRV, 20 November 2019 [11]",
        locator="announcement (4.9 CoreMark/MHz, up to 1.8 GHz on 28 nm); "
        "[11] Table 1 (4.94 CoreMark/MHz)",
        process="28 nm CMOS (announcement)",
        boundary="core; no area published",
        confidence="estimated",
        coremark_per_mhz=4.94,
        fmax_mhz=1800.0,
        fmax_kind="target",
    ),
    _row(
        _NONE,
        name="VeeR EL2",
        cite="[20]",
        source="CHIPS Alliance / Western Digital SweRV Core EL2 announcement",
        locator="announcement: 3.6 CoreMark/MHz simulated, 0.023 mm2 in "
        "16 nm, up to 600 MHz",
        process="TSMC 16 nm",
        boundary="core",
        confidence="estimated",
        coremark_per_mhz=3.6,
        fmax_mhz=600.0,
        fmax_kind="target",
        area_mm2=0.023,
        note="not a core in this study; the small-core neighbour of VeeR EH1",
    ),
]

# The claim on the README's title page, and what it was checked against.
# Update `as_of` when the check is redone; §4.5 of the README is the
# human-readable form.
UNIQUENESS = {
    "as_of": "2026-09",
    "as_of_text": "September 2026",
    "claim": "the only comparison of CoreMark/Joule across more than one hardened core, with activity from CoreMark itself, from an open and re-runnable flow",
    "qualifiers": [
        "more than one core, each hardened to a netlist",
        "switching activity from CoreMark itself, not an estimator",
        "every input open and pinned; re-runnable with one command",
    ],
    "near_misses": [
        "Schiavone et al., PATMOS 2017: 3 cores, CoreMark energy, PrimeTime, UMC 65 nm -- not re-runnable",
        "Gallmann et al., CARRV 2021: ibex and CV32E40P, CoreMark energy, PrimeTime, TSMC 65 nm -- not re-runnable",
        "Djupdal et al., arXiv 2502.06588: 7 cores, MachSuite not CoreMark, commercial 130 nm -- wrong workload, not re-runnable",
        "Fu et al., CF'25: 3 cores, power on matmult-int not CoreMark, GF 22 FDX -- wrong workload, not re-runnable",
        "Elsadek and Tawfik, IEEE 2021: 7 cores on an FPGA -- not hardened",
        "EEMBC ULPMark-CM: one silicon MCU per score -- not a comparison on one flow",
    ],
}

# Published performance per clock with no energy figure at a stated
# boundary, so x-axis orientation only.
REFERENCES = [
    {
        "name": "SonicBOOM",
        "coremark_per_mhz": 6.2,
        "source": "SonicBOOM: The 3rd Generation Berkeley Out-of-Order Machine, CARRV 2020",
    },
]


def check_literature(rows):
    """Every row has the schema, and every derived number is its formula.

    Returns the list of problems; empty means the table is consistent.
    """
    problems = []
    names = set()
    for row in rows:
        name = row.get("name", "<unnamed>")
        if name in names:
            problems.append("{}: duplicate row".format(name))
        names.add(name)
        for k in LITERATURE_FIELDS:
            if k not in row:
                problems.append("{}: missing {}".format(name, k))
        if not (row.get("source") and row.get("locator") and row.get("cite")):
            problems.append(
                "{}: a row needs a source, a README citation and a locator".format(name)
            )
        if row.get("confidence") not in CONFIDENCE:
            problems.append("{}: confidence {!r}".format(name, row.get("confidence")))
        if row.get("fmax_kind") not in FMAX_KINDS:
            problems.append("{}: fmax_kind {!r}".format(name, row.get("fmax_kind")))
        if (row.get("fmax_mhz") is None) != (row.get("fmax_kind") is None):
            problems.append("{}: fmax_mhz and fmax_kind travel together".format(name))
        if row.get("kge") is not None and not row.get(
            "kge_boundary", row.get("boundary")
        ):
            problems.append("{}: a kGE needs a boundary".format(name))
        cmj = row.get("coremark_per_joule")
        if cmj is not None:
            f = row.get("frequency_mhz")
            p = row.get("power_w")
            cm = row.get("coremark_per_mhz")
            if None in (f, p, cm):
                problems.append(
                    "{}: CoreMark/Joule without the three numbers it is made of".format(
                        name
                    )
                )
            elif abs(cmj - cm * f / p) > 1e-6 * cmj:
                problems.append(
                    "{}: CoreMark/Joule is not CoreMark/MHz * f / P".format(name)
                )
    return problems


def load_physical(entries):
    """CORE:PATH pairs to {core: {key: value}} from physical_probe.tcl output.

    The probe writes `key value` lines; numbers become numbers, the rest
    stays text, and the per-macro lines are collected under `macros`.
    """
    physical = {}
    for entry in entries:
        core, path = entry.split(":", 1)
        d = {"macros": []}
        with open(path) as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == "macro":
                    d["macros"].append(
                        {
                            "master": parts[1],
                            "count": int(parts[2]),
                            "um2": float(parts[3]),
                        }
                    )
                    continue
                key, value = parts[0], " ".join(parts[1:])
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                d[key] = value
        physical[core] = d
    return physical


def _cell(value, fmt="{:g}"):
    if value is None:
        return "--"
    if isinstance(value, (tuple, list)):
        return "--".join(fmt.format(v) for v in value)
    return fmt.format(value)


def literature_table(points, literature):
    """The §4.9 table as markdown: measured rows first, then the literature.

    Rendered from the pinned document so the README's table and the
    file cannot disagree without a diff showing it.
    """
    lines = [
        "| core | source | node | kGE | f (MHz) | CoreMark/MHz | CoreMark/Joule |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in points:
        phys = p.get("physical") or {}
        kge = phys.get("kge")
        f = p.get("frequency_mhz")
        lines.append(
            "| {} ({}) | this study, grt | asap7 | {} | {} (SDC) | {} | {} |".format(
                p["core"],
                p["isa"],
                _cell(kge, "{:.1f}"),
                _cell(f, "{:.0f}"),
                _cell(p.get("coremark_per_mhz"), "{:.2f}"),
                _cell(p.get("coremark_per_joule"), "{:.0f}"),
            )
        )
    for r in literature:
        f = r.get("fmax_mhz")
        fcell = "--" if f is None else "{:.0f} ({})".format(f, r["fmax_kind"])
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                r["name"],
                r["cite"],
                r["process"] or "--",
                _cell(r.get("kge"), "{:.1f}"),
                fcell,
                _cell(r.get("coremark_per_mhz"), "{:.2f}"),
                _cell(r.get("coremark_per_joule"), "{:.0f}"),
            )
        )
    return "\n".join(lines) + "\n"


def load_points(paths):
    points = []
    for path in paths:
        with open(path) as f:
            points.append(json.load(f))
    return sorted(points, key=lambda p: (p["core"], p["isa"]))


def two_sigma(values):
    """Twice the sample standard deviation; zero for a single value.

    §5.13: the spread is reported as 2σ, and the resolvable difference at
    k runs per arm is 2σ·sqrt(2/k). A single run's 2σ is zero, which is
    honest -- it says nothing has been measured about the spread.
    """
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return 2.0 * math.sqrt(var)


def seed_label(path):
    """The seed a sample file was run at, from its `_seedN` name; else its stem."""
    m = re.search(r"_seed(\d+)", os.path.basename(path))
    return m.group(1) if m else os.path.splitext(os.path.basename(path))[0]


def attach_samples(points, sample_paths):
    """Fold placement-seed samples into the point they belong to.

    Each sample is a point JSON from a seed variant of the same core
    (§5.13). The pinned point stays the design's own draw -- seed 1, the
    one every audit and sweep in the paper was run on -- and carries the
    ensemble beside it: every sample's power and CoreMark/Joule, the
    seed count, and 2σ of each, so a difference between two points can be
    read against the spread that would swallow it.
    """
    by_core = {(p["core"], p["isa"]): p for p in points}
    for path in sample_paths:
        with open(path) as f:
            sample = json.load(f)
        key = (sample["core"], sample["isa"])
        if key not in by_core:
            raise SystemExit(
                "pin_results: sample {} names a core with no point".format(path)
            )
        by_core[key].setdefault("seed_samples", []).append(
            {
                "seed": seed_label(path),
                "power_w": sample["power_w"],
                "coremark_per_joule": sample["coremark_per_joule"],
                "dynamic_power_w": sample.get("dynamic_power_w"),
                "leakage_power_w": sample.get("leakage_power_w"),
            }
        )
    for p in points:
        samples = [
            {
                "seed": "own",
                "power_w": p["power_w"],
                "coremark_per_joule": p["coremark_per_joule"],
                "dynamic_power_w": p.get("dynamic_power_w"),
                "leakage_power_w": p.get("leakage_power_w"),
            }
        ] + p.pop("seed_samples", [])
        if len(samples) > 1:
            p["seeds"] = len(samples)
            p["seed_samples"] = samples
            p["power_2sigma_w"] = two_sigma([x["power_w"] for x in samples])
            p["coremark_per_joule_2sigma"] = two_sigma(
                [x["coremark_per_joule"] for x in samples]
            )
    return points


def load_pending(paths):
    """Configurations with an x-coordinate but no y, and why.

    A core whose CoreMark/MHz is measured but whose energy is not is not
    absent from the study -- it is half-done. Dropping it from the pinned
    file would leave the plot quietly showing fewer cores than the study
    has, which is the failure the report format exists to avoid.
    """
    pending = []
    for entry in paths:
        path, core, isa, reason = entry.split(":", 3)
        with open(path) as f:
            perf = json.load(f)
        pending.append(
            {
                "core": core,
                "isa": isa,
                "coremark_per_mhz": perf["coremark_per_mhz"],
                "cycles_per_iteration": perf["cycles_per_iteration"],
                "coremark_per_joule": None,
                "blocked_on": reason,
            }
        )
    return sorted(pending, key=lambda p: (p["core"], p["isa"]))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("points", nargs="+", help="per-point JSON files")
    parser.add_argument(
        "--sample",
        action="append",
        default=[],
        metavar="JSON",
        help="a seed variant's point JSON, folded into the matching core's "
        "point as one sample of its placement-seed ensemble (§5.13)",
    )
    parser.add_argument(
        "--pending",
        action="append",
        default=[],
        metavar="JSON:CORE:ISA:REASON",
        help="a measured CoreMark/MHz whose energy is not measured yet, "
        "with what it is waiting on",
    )
    parser.add_argument(
        "--physical",
        action="append",
        default=[],
        metavar="CORE:TXT",
        help="a physical_probe.tcl report to attach to that core's point",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="print the literature table (§4.9) and write nothing",
    )
    args = parser.parse_args(argv[1:])

    problems = check_literature(LITERATURE)
    if problems:
        for p in problems:
            print("pin_results: literature: " + p, file=sys.stderr)
        return 1

    if args.table:
        points = load_points(args.points)
        physical = load_physical(args.physical)
        for p in points:
            if p["core"] in physical:
                p["physical"] = physical[p["core"]]
        sys.stdout.write(literature_table(points, LITERATURE))
        return 0

    root = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not root:
        print(
            "pin_results: no BUILD_WORKSPACE_DIRECTORY; run this through "
            "`bazelisk run`, which is what points it at the source tree",
            file=sys.stderr,
        )
        return 1

    points = attach_samples(load_points(args.points), args.sample)
    physical = load_physical(args.physical)
    for p in points:
        if p["core"] in physical:
            # The same ODB the power came from: the gate count and the
            # energy describe one netlist.
            p["physical"] = physical[p["core"]]
    pending = load_pending(args.pending)
    out = os.path.join(root, RESULTS)

    previous = None
    if os.path.exists(out):
        with open(out) as f:
            previous = json.load(f)

    document = {
        # Stated rather than implied: every number here is comparable to
        # the others only because these are the same for all of them.
        "provenance": {
            "platform": "asap7",
            "stage": "grt",
            "corner": "BC: RVT, FF, 0.77 V, 25 C, NLDM -- asap7's ORFS "
            "default, which is the best case rather than the typical one",
            "parasitics": "estimate_parasitics -global_routing; no " "extracted SPEF",
            "activity": "saif, one hot CoreMark iteration",
            "activity_annotation": "100% of pins annotated from the SAIF "
            "on every point; see the *_activity_audit.json and "
            "*_activity_sweep_check.json targets",
            "simulation": "Verilator, two-state and zero-delay: carries no "
            "glitch power",
            # Short on purpose: it is rendered as a caption line under
            # the figure. What each point actually hardened is no longer
            # the same answer for all of them, so it travels per point
            # in that point's own `boundary` field.
            "boundary": "core + L1, or the small SRAM standing in for "
            "one -- stated per point",
            "frequency": "the SDC period the SAIF was timed against, "
            "not an achieved maximum",
            "note": "Not reportable CoreMark scores: a three-iteration run "
            "does not satisfy CoreMark's run rules.",
            # The title page's claim is about the literature on a day.
            # The date lives here so the README's first line is rendered
            # and checked against it (readme_numbers_test), and so a
            # re-pin cannot silently outlive the search that justifies it.
            "uniqueness": UNIQUENESS,
        },
        "points": points,
        # Published performance-per-clock for cores not measured here.
        # x-axis orientation only; see REFERENCES for why there is no y.
        "references": REFERENCES,
        "literature": LITERATURE,
        # Half-done configurations, carried so the plot cannot show
        # fewer cores than the study has without saying so.
        "pending": pending,
    }

    with open(out, "w") as f:
        json.dump(document, f, indent=2, sort_keys=True)
        f.write("\n")

    if previous == document:
        print("pin_results: {} unchanged".format(RESULTS))
    else:
        print("pin_results: wrote {} point(s) to {}".format(len(points), RESULTS))
        for p in points:
            print(
                "  {:9s} {:8s} {:9.4f} CoreMark/MHz  {:7.2f} mW  "
                "{:>9,.0f} CoreMark/J{}".format(
                    p["core"],
                    p["isa"],
                    p["coremark_per_mhz"],
                    p["power_w"] * 1e3,
                    p["coremark_per_joule"],
                    (
                        "  ±{:,.0f} (2σ, {} seeds)".format(
                            p["coremark_per_joule_2sigma"], p["seeds"]
                        )
                        if "seeds" in p
                        else ""
                    ),
                )
            )
        for p in pending:
            print(
                "  {:9s} {:8s} {:9.4f} CoreMark/MHz   energy not yet "
                "measured: {}".format(
                    p["core"], p["isa"], p["coremark_per_mhz"], p["blocked_on"]
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
