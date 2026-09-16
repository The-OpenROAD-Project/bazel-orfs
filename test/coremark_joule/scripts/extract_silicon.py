"""Extract the wall-plug silicon measurements into the study's JSON shape.

Three shipping parts were measured by sweeping the number of active
cores and reading total system power at the plug, with energy
attributed as

    uJ per iteration per core = (P_load - P_idle) / (cores * iterations/s)

Everything outside the cores is held constant across a sweep, so the
difference brackets core activity without any on-die instrumentation.
CoreMark's working set fits in L1, which is what makes that defensible:
the delta cannot be DRAM or uncore traffic because the benchmark never
generates any. It is also the limit of the method -- nothing measured
this way generalises to a workload that misses L1.

Two estimators, and the difference between them is the point
--------------------------------------------------------------

`delta` is the spreadsheet's own: per-core power from one operating
point, (P_at_n - P_idle) / n. It needs an idle reading, and on a system
whose idle is large compared with one core's contribution it is a small
difference of two large numbers. On the 32-core part the one-core
signal is 3.0 W read as 170.0 W minus 167.0 W -- 1.8 % of the reading,
which a plug meter specified at +/-1-2 % cannot resolve.

`slope` is watts per additional core, fitted over the region where the
part is not throttling. A systematic meter offset cancels in a slope,
and no idle reading is needed at all. It reproduces the spreadsheet's
adjusted numbers to within 2 % on two of the three parts while needing
none of its modelling, and it rescues the third from an implausible
figure that was dominated by platform ramp.

Where they disagree, `slope` is the one to quote, and the JSON carries
both so a reader can see the disagreement rather than take our word for
it.

Confidentiality
---------------

The source sheets name an internal repository path and an internal
build configuration. Neither is reproduced here: the workload is
recorded as a neutral description, and the spreadsheet itself is not
committed. See CLAUDE.md.
"""

import argparse
import json
from pathlib import Path

# Per-part metadata that is not in the numeric rows. Nodes are the core
# die's process, since that is the only part of the package the
# measurement's boundary covers.
PARTS = {
    "AMD Ryzen": {
        "vendor": "AMD",
        "part": "Ryzen Threadripper 3970X",
        "microarchitecture": "Zen 2",
        "cores": 32,
        "threads": 64,
        "smt": True,
        "clock_mhz": 3900,
        "node": "TSMC N7",
        "node_note": "Zen 2 CCDs on TSMC N7; IO die on GF 12/14 nm, outside the measured boundary",
        "tdp_w": 280,
        "workload": "CoreMark, x86 build, -O3",
        # The unthrottled region: per-core throughput is flat to here.
        "fit_range": (1, 35),
        "header_row": 7,
    },
    "Intel Xeon 8558U": {
        "vendor": "Intel",
        "part": "Xeon Platinum 8558U",
        "microarchitecture": "Emerald Rapids (Raptor Cove)",
        "cores": 48,
        "threads": 96,
        "smt": True,
        "clock_mhz": 2900,
        "node": "Intel 7",
        "node_note": "Emerald Rapids on Intel 7",
        "tdp_w": None,
        "workload": "CoreMark, x86 build, -O3",
        # Starts from 5: the 1-4 thread points are dominated by platform
        # and uncore ramp (the first thread alone costs 50 W), which is
        # not core power and would wreck the fit.
        "fit_range": (5, 20),
        "header_row": 9,
    },
    "Qualcomm Snapdragon": {
        "vendor": "Qualcomm",
        "part": "Snapdragon X Elite X1E78100",
        "microarchitecture": "Oryon",
        "cores": 12,
        "threads": 12,
        "smt": False,
        "clock_mhz": 3417,
        "node": "TSMC N4P",
        "node_note": "Oryon on TSMC N4P",
        "tdp_w": None,
        "workload": "CoreMark, Windows build",
        "fit_range": (1, 12),
        "header_row": 6,
    },
}


def read_sheet(workbook, sheet_name, header_row):
    """(idle_watts, [(n, watts, iterations_per_s), ...]) from one sheet.

    The idle row is labelled rather than numbered, and the numeric rows
    run until the sheet's notes begin.
    """
    ws = workbook[sheet_name]
    idle = None
    rows = []
    for row in ws.iter_rows(min_row=header_row, values_only=True):
        if not row or row[0] is None:
            continue
        label = str(row[0]).strip()
        if label == "Idle":
            idle = float(row[1])
            continue
        try:
            n = int(float(label))
        except ValueError:
            continue
        if row[1] is None or row[2] is None:
            continue
        rows.append((n, float(row[1]), float(row[2])))
    if idle is None:
        raise SystemExit(f"{sheet_name}: no Idle row; the sheet layout changed")
    if not rows:
        raise SystemExit(f"{sheet_name}: no numeric rows")
    return idle, rows


def slope_watts_per_core(rows, fit_range):
    """Least-squares watts per additional core over the fit range.

    Two points would be enough for a slope, but a fit over the whole
    unthrottled region averages down the per-reading noise, and the
    residual is worth reporting: a large one means the region chosen is
    not actually linear, which is the assumption the estimator rests on.
    """
    lo, hi = fit_range
    pts = [(n, w) for n, w, _ in rows if lo <= n <= hi]
    if len(pts) < 2:
        raise SystemExit(f"fit range {fit_range} selects fewer than two points")
    n_mean = sum(p[0] for p in pts) / len(pts)
    w_mean = sum(p[1] for p in pts) / len(pts)
    num = sum((n - n_mean) * (w - w_mean) for n, w in pts)
    den = sum((n - n_mean) ** 2 for n, _ in pts)
    if den == 0:
        raise SystemExit("fit range has no spread in core count")
    slope = num / den
    intercept = w_mean - slope * n_mean
    resid = max(abs(w - (slope * n + intercept)) for n, w in pts)
    return slope, intercept, resid


def unthrottled_throughput(rows, fit_range):
    """Iterations/s per core where the part is not yet throttling."""
    lo, hi = fit_range
    vals = [it for n, _, it in rows if lo <= n <= hi]
    return max(vals)


def build_part(meta, idle, rows):
    slope, intercept, resid = slope_watts_per_core(rows, meta["fit_range"])
    it_s = unthrottled_throughput(rows, meta["fit_range"])
    peak = max(it for _, _, it in rows)

    sweep = []
    for n, w, it in rows:
        delta_w = w - idle
        sweep.append(
            {
                "active": n,
                "wall_w": w,
                "iterations_per_s": it,
                "relative_throughput": it / peak,
                "delta_w": delta_w,
                "delta_w_per_core": delta_w / n,
                "uj_per_iteration_delta": 1e6 * delta_w / (n * it),
                "uj_per_iteration_slope": 1e6 * slope / it,
                "coremark_per_mhz": it / meta["clock_mhz"],
            }
        )

    return {
        "vendor": meta["vendor"],
        "part": meta["part"],
        "microarchitecture": meta["microarchitecture"],
        "node": meta["node"],
        "node_note": meta["node_note"],
        "cores": meta["cores"],
        "threads": meta["threads"],
        "smt": meta["smt"],
        "clock_mhz": meta["clock_mhz"],
        "tdp_w": meta["tdp_w"],
        "workload": meta["workload"],
        "idle_w": idle,
        "fit_range": list(meta["fit_range"]),
        "slope_w_per_core": slope,
        "slope_intercept_w": intercept,
        "slope_max_residual_w": resid,
        "unthrottled_iterations_per_s": it_s,
        "coremark_per_mhz": it_s / meta["clock_mhz"],
        "uj_per_iteration_slope": 1e6 * slope / it_s,
        # Iterations per millijoule: the reciprocal of uJ/iteration,
        # times 1000 uJ/mJ.
        "coremark_per_mj_slope": 1e3 / (1e6 * slope / it_s),
        "sweep": sweep,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", required=True, help="the measurement workbook")
    ap.add_argument("--out", required=True, help="where to write silicon.json")
    args = ap.parse_args()

    import openpyxl

    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    parts = []
    for sheet, meta in PARTS.items():
        idle, rows = read_sheet(wb, sheet, meta["header_row"])
        parts.append(build_part(meta, idle, rows))

    document = {
        "provenance": {
            "method": (
                "Total system power read at the mains plug while CoreMark runs "
                "on n active cores. Energy attributed as (P_load - P_idle) / "
                "(cores * iterations/s) for the delta estimator, and as the "
                "fitted watts-per-additional-core for the slope estimator."
            ),
            "boundary": (
                "Core and its private caches, bracketed rather than isolated. "
                "CoreMark's working set fits in L1, so the measured delta "
                "cannot include DRAM or uncore traffic; it does include "
                "whatever power conversion and platform logic scales with "
                "core count, which is why the slope estimator is preferred."
            ),
            "estimators": {
                "delta": "per-core power from one point, needs an idle reading",
                "slope": "watts per additional core over the unthrottled region, "
                "no idle reading needed, cancels systematic meter offset",
            },
            "not_eembc_certified": (
                "These are not EEMBC-certified CoreMark runs and the build "
                "flags are not matched across parts. The CoreMark/MHz values "
                "are therefore not comparable with EEMBC's published database."
            ),
            "single_reading": "Every point is one reading; no repeats, no spread.",
        },
        "parts": parts,
    }

    Path(args.out).write_text(json.dumps(document, indent=2) + "\n")
    for p in parts:
        print(
            "{:<28} slope {:5.2f} W/core  {:6.1f} uJ/iter  "
            "{:5.2f} CoreMark/mJ  {:5.2f} CoreMark/MHz".format(
                p["part"],
                p["slope_w_per_core"],
                p["uj_per_iteration_slope"],
                1e3 / p["uj_per_iteration_slope"],
                p["coremark_per_mhz"],
            )
        )


if __name__ == "__main__":
    main()
