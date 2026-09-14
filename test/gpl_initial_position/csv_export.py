"""Flatten the sample JSONs into the CSV the pull request carries.

A study PR ships its raw samples as one fenced ```csv comment, so every
table in the body can be recomputed -- and questions the study did not
think to ask can be answered -- without re-running anything. That is the
difference between a report and a dataset.

Two rules the exporter enforces so the comment is safe to publish:

* **No local paths.** The sample records carry the command each run
  issued, with the deployed tree already replaced by `<tree>`. Nothing
  path-shaped reaches a column here regardless, but `SAFE_COLUMNS` is an
  allowlist rather than a denylist, so a future field cannot leak by
  being added.
* **Every row says what witnessed it.** `arm_witnessed` is a column, not
  a filter applied silently upstream, so a reader can see that the arms
  were what they claim to be rather than taking it on trust.
"""

import argparse
import csv
import io
import os
import sys

import report

# The allowlist. Order is the column order.
SAFE_COLUMNS = [
    "platform",
    "design",
    "arm",
    "arm_witnessed",
    "seed",
    "clk_period",
    "gp_hpwl_final",
    "gp_iterations",
    "gp_segments",
    "diverge_revert",
    "ip_iterations",
    "ip_residual",
    "ip_converged",
    "ip_hit_cap",
    "ip_hpwl_first",
    "ip_hpwl_last",
    "src_odb_3_1",
    "src_core_3_1",
    "src_odb_3_3",
    "src_core_3_3",
    "min_period_wns",
    "setup_ws",
    "setup_tns",
    "hold_ws",
    "wirelength",
    "grt_usage_pct",
    "grt_overflow",
    "grt_max_layer_usage_pct",
    "grt_congested",
    "drc",
    "place_area",
    "place_instances",
    "gp_wall_s",
    "serial",
    "cores",
    "loadavg_at_start",
    "status",
    "place_gp_sha1",
    "skip_io_sha1",
    "grt_sha1",
]


def row(record):
    """One sample as a flat dict of allowlisted columns.

    Args:
        record: a sample JSON.

    Returns:
        The row. Absent nested pieces become empty cells rather than the
        string "None", so a spreadsheet reads them as missing.
    """
    initial = record.get("initial_place") or {}
    sources_io = record.get("position_sources_skip_io") or {}
    sources = record.get("position_sources") or {}
    run = record.get("run") or {}
    witness = record.get("witness") or {}
    flat = {
        "ip_iterations": initial.get("last_iteration"),
        "ip_residual": initial.get("final_residual"),
        "ip_converged": initial.get("converged"),
        "ip_hit_cap": initial.get("hit_cap"),
        "ip_hpwl_first": initial.get("hpwl_first"),
        "ip_hpwl_last": initial.get("hpwl_last"),
        "src_odb_3_1": sources_io.get("odb"),
        "src_core_3_1": sources_io.get("core_center"),
        "src_odb_3_3": sources.get("odb"),
        "src_core_3_3": sources.get("core_center"),
        "serial": run.get("serial"),
        "cores": run.get("cores"),
        "loadavg_at_start": run.get("loadavg_at_start"),
        "status": run.get("status"),
        "place_gp_sha1": witness.get("3_3_place_gp.odb"),
        "skip_io_sha1": witness.get("3_1_place_gp_skip_io.odb"),
        "grt_sha1": witness.get("5_1_grt.odb"),
    }
    for key in SAFE_COLUMNS:
        if key not in flat:
            flat[key] = record.get(key)
    return {key: ("" if flat[key] is None else flat[key]) for key in SAFE_COLUMNS}


def export(samples):
    """The CSV text.

    Args:
        samples: sample records.

    Returns:
        The CSV, header first, sorted by (design, arm, seed) so a diff
        between two campaign runs is readable.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SAFE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in sorted(
        samples,
        key=lambda r: (
            str(r.get("platform")),
            str(r.get("design")),
            str(r.get("arm")),
            int(r.get("seed") or 0),
        ),
    ):
        writer.writerow(row(record))
    return buffer.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", default=None, help="default: stdout")
    parser.add_argument(
        "--include-discarded",
        action="store_true",
        help="also export samples whose log did not attest to their arm, "
        "so the discards can be inspected rather than only counted",
    )
    args = parser.parse_args(argv)

    samples, dropped = report.load(args.results)
    text = export(samples)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as handle:
            handle.write(text)
        print("wrote %s (%d samples, %d discarded)" % (args.out, len(samples), len(dropped)))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
