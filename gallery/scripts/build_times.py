"""Extract per-stage build times from ORFS logs and write build_times.yaml.

Uses the same elapsed-time parsing as ORFS's genElapsedTime.py.

Usage:
    build_times.py <project> [--output build_times.yaml]

Example:
    bazelisk run //scripts:build_times -- serv
    bazelisk run //scripts:build_times -- vlsiffra
    bazelisk run //scripts:build_times -- gemmini
"""
import argparse
import re
import sys
from pathlib import Path

# Try to import yaml; fall back to simple emitter if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


DEFAULT_PDK = "asap7"


def parse_elapsed_time(log_file: Path) -> tuple:
    """Parse elapsed time (seconds) and peak memory (MB) from a log file.

    Matches the format used by ORFS: 'Elapsed time: [h:]m:s[.frac]...'
    """
    text = log_file.read_text(errors="replace")
    elapsed_s = None
    peak_mb = None

    for line in text.splitlines():
        m = re.search(r"Elapsed time:\s+(\d+):(\d+[.\d]*)", line)
        if not m:
            m = re.search(r"Elapsed time:\s+(\d+):(\d+):(\d+[.\d]*)", line)
            if m:
                h, mins, secs = int(m.group(1)), int(m.group(2)), float(m.group(3))
                elapsed_s = h * 3600 + mins * 60 + int(secs)
        if m and elapsed_s is None:
            mins, secs = int(m.group(1)), float(m.group(2))
            elapsed_s = mins * 60 + int(secs)

        # Peak memory in KB (on the same Elapsed time line)
        mem_match = re.search(r"Peak memory:\s*(\d+)KB", line)
        if mem_match:
            peak_mb = int(mem_match.group(1)) // 1024

    return elapsed_s, peak_mb


def collect_stages(logs_dir: Path) -> list:
    """Collect elapsed time for each stage log file."""
    stages = []
    for log_file in sorted(logs_dir.glob("*.log")):
        if "metrics" in log_file.name:
            continue
        elapsed_s, memory_mb = parse_elapsed_time(log_file)
        if elapsed_s is not None:
            stages.append({
                "name": log_file.stem,
                "elapsed_s": elapsed_s,
                "memory_mb": memory_mb,
            })
    return stages


def format_yaml_entry(project: str, module: str, stages: list, note: str = None) -> str:
    """Format a single project entry as YAML."""
    total = sum(s["elapsed_s"] for s in stages)
    memories = [s["memory_mb"] for s in stages if s["memory_mb"] is not None]
    peak = max(memories) if memories else None

    lines = [f"{project}:"]
    lines.append(f"  module: {module}")
    lines.append(f"  total_elapsed_s: {total}")
    if peak is not None:
        lines.append(f"  peak_memory_mb: {peak}")
    if note:
        lines.append(f'  note: "{note}"')
    lines.append("  stages:")
    for s in stages:
        mem_part = f", memory_mb: {s['memory_mb']}" if s["memory_mb"] is not None else ""
        lines.append(f"    {s['name']}: {{elapsed_s: {s['elapsed_s']}{mem_part}}}")
    return "\n".join(lines)


def find_logs_dir(project: str) -> tuple:
    """Find the ORFS logs directory for a project by scanning bazel-bin.

    Auto-discovers the module name from the directory structure:
    bazel-bin/<project>/logs/<pdk>/<module>/base/

    Returns (logs_dir, module_name).
    """
    import os
    workspace = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."))
    pdk_dir = workspace / "bazel-bin" / project / "logs" / DEFAULT_PDK

    if not pdk_dir.exists():
        print(f"No build output found: {pdk_dir}", file=sys.stderr)
        print(f"Run the build first: bazelisk build //{project}:...", file=sys.stderr)
        sys.exit(1)

    # Find module dirs that have a base/ subdirectory with log files
    candidates = [d for d in pdk_dir.iterdir()
                  if d.is_dir() and (d / "base").is_dir()
                  and list((d / "base").glob("*.log"))]

    if not candidates:
        print(f"No log files found under {pdk_dir}/*/base/", file=sys.stderr)
        sys.exit(1)

    if len(candidates) > 1:
        # Multiple modules — pick the one with the most log files (likely the top module)
        candidates.sort(key=lambda d: len(list((d / "base").glob("*.log"))), reverse=True)

    module = candidates[0].name
    return candidates[0] / "base", module


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="Project name (serv, vlsiffra, gemmini)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output YAML file (default: build_times.yaml in workspace root)")
    args = parser.parse_args()

    import os
    workspace = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."))
    output_path = Path(args.output) if args.output else workspace / "build_times.yaml"

    logs_dir, module = find_logs_dir(args.project)
    stages = collect_stages(logs_dir)

    if not stages:
        print(f"No timing data found in {logs_dir}", file=sys.stderr)
        sys.exit(1)

    # Check if GRT was terminated
    note = None
    grt_log = logs_dir / "5_1_grt.log"
    if grt_log.exists():
        text = grt_log.read_text(errors="replace")
        if "Command terminated by signal" in text:
            note = "GRT terminated — flow incomplete"

    # Read existing YAML if present, update the project entry
    header = ("# Build stage elapsed times (seconds) and peak memory (MB)\n"
              "# Generated by: bazelisk run //scripts:build_times -- <project>\n"
              "# Source: ORFS genElapsedTime.py applied to bazel-bin log files\n")

    new_entry = format_yaml_entry(args.project, module, stages, note)

    if output_path.exists():
        content = output_path.read_text()
        # Remove header for processing
        body = content
        for h_line in header.splitlines():
            body = body.replace(h_line + "\n", "")

        # Replace existing project block or append
        pattern = rf"^{re.escape(args.project)}:.*?(?=^\w|\Z)"
        match = re.search(pattern, body, re.MULTILINE | re.DOTALL)
        if match:
            body = body[:match.start()] + new_entry + "\n" + body[match.end():]
        else:
            body = body.rstrip() + "\n\n" + new_entry + "\n"

        content = header + "\n" + body.strip() + "\n"
    else:
        content = header + "\n" + new_entry + "\n"

    output_path.write_text(content)
    print(f"Updated {args.project} in {output_path}", file=sys.stderr)
    print(f"  {len(stages)} stages, total {sum(s['elapsed_s'] for s in stages)}s", file=sys.stderr)


if __name__ == "__main__":
    main()
