"""Extract key metrics from ORFS build output.

Parses JSON metrics files and log files to produce a structured JSON summary.

Usage:
    extract_metrics.py <logs_dir> <reports_dir> [--output metrics.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path


def parse_json_metrics(logs_dir: Path) -> dict:
    """Extract metrics from ORFS JSON files."""
    result = {}
    report_json = logs_dir / "6_report.json"
    if report_json.exists():
        data = json.loads(report_json.read_text())
        result["cells"] = data.get("finish__design__instance__count")
        result["area_um2"] = data.get("finish__design__instance__area")
    return result


def parse_timing_from_logs(logs_dir: Path) -> dict:
    """Extract timing info from GRT log (last stage with timing summary)."""
    result = {}
    # Try GRT log first, then CTS
    for log_name in ["5_1_grt.log", "4_1_cts.log"]:
        log_file = logs_dir / log_name
        if not log_file.exists():
            continue
        text = log_file.read_text()
        # FLW-0007: target clock period
        m = re.search(r"\[INFO FLW-0007\] clock \S+ period ([\d.]+)", text)
        if m:
            result["clock_period_ps"] = float(m.group(1))
        # FLW-0009: slack (WNS)
        m = re.search(r"\[INFO FLW-0009\] Clock \S+ slack ([-\d.]+)", text)
        if m:
            result["wns_ps"] = float(m.group(1))
        if result:
            break
    # Compute frequency
    if "clock_period_ps" in result:
        period = result["clock_period_ps"]
        wns = result.get("wns_ps", 0)
        if wns < 0:
            actual_period = period - wns  # WNS is negative
        else:
            actual_period = period
        result["frequency_ghz"] = round(1000 / actual_period, 2)
        result["target_frequency_ghz"] = round(1000 / period, 2)
    return result


def parse_power_from_logs(logs_dir: Path) -> dict:
    """Extract power from final report log."""
    result = {}
    log_file = logs_dir / "6_report.log"
    if not log_file.exists():
        return result
    text = log_file.read_text()
    # First "Total power" line (VDD net)
    m = re.search(r"Total power\s*:\s*([\d.eE+-]+)\s*W", text)
    if m:
        result["power_w"] = float(m.group(1))
        result["power_mw"] = round(float(m.group(1)) * 1000, 1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs_dir", help="Path to ORFS logs directory")
    parser.add_argument("reports_dir", help="Path to ORFS reports directory")
    parser.add_argument("--output", "-o", default="-", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir)
    metrics = {}
    metrics.update(parse_json_metrics(logs_dir))
    metrics.update(parse_timing_from_logs(logs_dir))
    metrics.update(parse_power_from_logs(logs_dir))

    output = json.dumps(metrics, indent=2)
    if args.output == "-":
        print(output)
    else:
        Path(args.output).write_text(output + "\n")
        print(f"Wrote metrics to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
