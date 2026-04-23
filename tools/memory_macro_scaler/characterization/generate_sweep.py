"""Harvest per-shape ORFS sweep results into asap7_sweep.yaml.

This is the *second* half of the sweep — the first half is an `orfs_flow()`
per SWEEP_SHAPES entry declared in characterization/BUILD. Bazel runs
those flows (slow, tagged manual). When this script is invoked — also
manual — it reads each flow's emitted `.lib`, pulls out area / access
time / setup / hold / WNS, and writes them to asap7_sweep.yaml in the
schema documented at the top of that file.

Why write YAML instead of re-fitting inline?
  The YAML is git-reviewed like any other artifact: a sweep whose numbers
  shift is visible in diff. Re-fitting inline would bake the data into
  the binary and lose that reviewability. memory_macro_scaler.py loads
  the YAML at startup and folds its points into the fit.

Usage (from the bazel-orfs repo root):

    bazel run //tools/memory_macro_scaler/characterization:asap7_sweep -- \\
        --result-files <path>/run_*.lib ... \\
        --output tools/memory_macro_scaler/characterization/asap7_sweep.yaml

In practice the Bazel target `asap7_sweep` wires all the result file
labels as `data` and passes them through `$(locations ...)`.
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    # Re-raise with a helpful message; bazel-orfs keeps PyYAML in its
    # requirements.in, so this should never fire inside the tool's py_binary.
    print("error: PyYAML is required. Add it to the py_binary's deps.",
          file=sys.stderr)
    raise


_CELL_NAME_RE = re.compile(r"^\s*cell\s*\(\s*([^\s)]+)\s*\)", re.MULTILINE)


def _parse_shape(name):
    """Pull (rows, bits, ports_key, write_mask_bits) out of a run name.

    BUILD-time encoding (see characterization/BUILD): each sweep entry is
    named `ff_<rows>x<bits>_<ports_key>_wm<write_mask_bits>`.
    """
    m = re.match(
        r"ff_(\d+)x(\d+)_([0-9]+R[0-9]+W|[0-9]+RW)_wm(\d+)",
        name,
    )
    if not m:
        raise ValueError(f"can't parse shape from run name '{name}'")
    return int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))


def _parse_lib(path):
    """Extract (area_um2, access_ps, setup_ps, hold_ps) from a Liberty file.

    Coarse: uses the first cell's `area`, the max `cell_rise` in any
    `timing_type : rising_edge` arc as access time, and the max
    `rise_constraint` / `fall_constraint` in `timing_type : setup_rising`
    / `hold_rising` arcs as setup / hold. Good enough for the sweep
    harvest — the Liberty parser is not the point.
    """
    text = path.read_text()
    area = None
    m = re.search(r"\barea\s*:\s*([\d.]+)", text)
    if m:
        area = float(m.group(1))

    def _vals(timing_type):
        vals = []
        pat = re.compile(
            rf"timing\s*\(\s*\)\s*\{{[^{{}}]*?timing_type\s*:\s*{timing_type}[^{{}}]*?\}}",
            re.DOTALL,
        )
        for m in pat.finditer(text):
            for v in re.finditer(r'values\s*\(\s*"(-?[\d.]+)"', m.group(0)):
                vals.append(float(v.group(1)))
        return vals

    # ns → ps (Liberty default time unit is ns).
    access = max(_vals("rising_edge"), default=0.0) * 1000.0
    setup = max(_vals("setup_rising"), default=0.0) * 1000.0
    hold = max(_vals("hold_rising"), default=0.0) * 1000.0
    return area, access, setup, hold


def _result_name_from_path(path):
    """The sweep's run name is the .lib's parent-directory basename."""
    return path.parent.name


def harvest(result_paths):
    runs = []
    for p in sorted(result_paths):
        rows, bits, ports_key, wm = _parse_shape(_result_name_from_path(p))
        area, access, setup, hold = _parse_lib(p)
        runs.append(dict(
            tech_nm=7,
            kind="ff",
            rows=rows,
            bits=bits,
            ports_key=ports_key,
            write_mask_bits=wm,
            area_um2=area,
            access_time_ps=access,
            setup_ps=setup,
            hold_ps=hold,
            wns_ps=None,         # filled in by a future reporter
            clk_period_ps=None,
            tool="orfs-sweep",
            notes="",
        ))
    return runs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--result-files", nargs="+", required=True, type=Path,
                   help="List of .lib paths harvested from the sweep.")
    p.add_argument("--output", required=True, type=Path,
                   help="Path to write asap7_sweep.yaml.")
    args = p.parse_args(argv)

    runs = harvest(args.result_files)
    doc = dict(version=1, runs=runs)
    args.output.write_text(yaml.safe_dump(doc, sort_keys=False))
    print(f"generate_sweep: wrote {len(runs)} runs to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
