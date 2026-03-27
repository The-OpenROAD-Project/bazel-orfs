"""Collect logs, reports, and metrics from bazel-bin into the project folder.

Copies all available ORFS outputs (logs, reports, JSON metrics) for how far
a project has been built. Uses bazel-bin paths directly — no cquery needed.

Usage:
    bazelisk run //scripts:collect_stage_outputs -- <project> [<top_module>]

If top_module is omitted, it is inferred from BUILD.bazel.

Output structure:
    <project>/
        logs/       ← .log files from all completed stages
        reports/    ← .rpt and .txt report files
        metrics/    ← .json metric files from each substep
"""
import argparse
import os
import re
import shutil
import sys
from pathlib import Path


# Stage prefixes in order — used to determine how far the build got
STAGE_PREFIXES = [
    ("synth", ["1_1_yosys_canonicalize", "1_2_yosys", "1_2_yosys_metrics"]),
    ("floorplan", ["2_1_floorplan", "2_2_floorplan_macro", "2_3_floorplan_tapcell", "2_4_floorplan_pdn"]),
    ("place", ["3_1_place_gp_skip_io", "3_2_place_iop", "3_3_place_gp", "3_4_place_resized", "3_5_place_dp"]),
    ("cts", ["4_1_cts"]),
    ("grt", ["5_1_grt"]),
    ("route", ["5_2_route", "5_3_fillcell"]),
    ("final", ["6_1_merge", "6_report"]),
]


def find_top_module(project_dir: Path) -> str:
    """Infer top module from BUILD.bazel demo_flow target."""
    build_file = project_dir / "BUILD.bazel"
    if not build_file.exists():
        sys.exit(f"Error: {build_file} not found")
    text = build_file.read_text()
    m = re.search(r'demo_flow\(\s*name\s*=\s*"([^"]+)"', text)
    if not m:
        sys.exit(f"Error: no demo_flow target found in {build_file}")
    return m.group(1)


def collect_files(src_dir: Path, dst_dir: Path, extensions: list[str]) -> list[str]:
    """Copy files with given extensions from src to dst. Returns list of copied filenames."""
    if not src_dir.exists():
        return []
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for ext in extensions:
        for f in sorted(src_dir.glob(f"*{ext}")):
            dst = dst_dir / f.name
            # Make existing file writable before overwriting (bazel copies are read-only)
            if dst.exists():
                dst.chmod(0o644)
            shutil.copy2(f, dst)
            dst.chmod(0o644)
            copied.append(f.name)
    return copied


def determine_completed_stages(logs_dir: Path) -> list[str]:
    """Determine which stages completed based on available log files."""
    completed = []
    for stage_name, substeps in STAGE_PREFIXES:
        # A stage is complete if its last substep has a log file
        last_substep = substeps[-1]
        if (logs_dir / f"{last_substep}.log").exists() or (logs_dir / f"{last_substep}.json").exists():
            completed.append(stage_name)
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="Project directory name (e.g. gemmini)")
    parser.add_argument("top_module", nargs="?", help="Top module name (inferred from BUILD.bazel if omitted)")
    args = parser.parse_args()

    # Find workspace root — BUILD_WORKSPACE_DIRECTORY is set by `bazelisk run`
    workspace_env = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if workspace_env:
        workspace = Path(workspace_env)
    else:
        workspace = Path.cwd()
        while workspace != workspace.parent:
            if (workspace / "MODULE.bazel").exists():
                break
            workspace = workspace.parent
        else:
            sys.exit("Error: could not find workspace root (MODULE.bazel)")

    project_dir = workspace / args.project
    if not project_dir.exists():
        sys.exit(f"Error: project directory {project_dir} not found")

    top_module = args.top_module or find_top_module(project_dir)

    # Source directories in bazel-bin
    base_path = f"{args.project}/{{kind}}/asap7/{top_module}/base"
    logs_src = workspace / "bazel-bin" / base_path.format(kind="logs")
    reports_src = workspace / "bazel-bin" / base_path.format(kind="reports")

    # Destination directories in project folder
    logs_dst = project_dir / "logs"
    reports_dst = project_dir / "reports"
    metrics_dst = project_dir / "metrics"

    # Determine what stages completed
    completed = determine_completed_stages(logs_src)
    if not completed:
        print(f"No completed stages found for {args.project}:{top_module}")
        print(f"  (looked in {logs_src})")
        sys.exit(1)

    print(f"Project: {args.project}, module: {top_module}")
    print(f"Completed stages: {', '.join(completed)}")
    print()

    # Collect logs (.log files)
    log_files = collect_files(logs_src, logs_dst, [".log"])
    if log_files:
        print(f"Logs ({len(log_files)} files) → {logs_dst}/")
        for f in log_files:
            print(f"  {f}")

    # Collect metrics (.json files from logs dir)
    metric_files = collect_files(logs_src, metrics_dst, [".json"])
    if metric_files:
        print(f"\nMetrics ({len(metric_files)} files) → {metrics_dst}/")
        for f in metric_files:
            print(f"  {f}")

    # Collect reports (.rpt and .txt files)
    report_files = collect_files(reports_src, reports_dst, [".rpt", ".txt"])
    if report_files:
        print(f"\nReports ({len(report_files)} files) → {reports_dst}/")
        for f in report_files:
            print(f"  {f}")

    total = len(log_files) + len(metric_files) + len(report_files)
    print(f"\nTotal: {total} files collected through {completed[-1]} stage")


if __name__ == "__main__":
    main()
