#!/usr/bin/env python3
"""Monitor bazelisk test runs: show active stages and produce a timing table.

Usage:
    bazelisk run //:monitor-test
    bazelisk run //:monitor-test -- //test/...
    bazelisk run //:monitor-test -- //test/... --test_tag_filters=-manual
"""

import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path


def get_active_stages():
    """Get currently active ORFS stages from tee processes."""
    try:
        result = subprocess.run(
            ["ps", "-Af"], capture_output=True, text=True, timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    stages = []
    for line in result.stdout.splitlines():
        m = re.search(r"tee -a .*/logs/(.+?)\.tmp\.log", line)
        if m:
            stages.append(m.group(1))
    return sorted(set(stages))


def get_stage_timings(log_dir):
    """Extract per-stage timings from ORFS log files."""
    timings = []
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return timings

    for log_file in log_dir.rglob("*.log"):
        if ".tmp." in log_file.name:
            continue
        design = str(log_file.relative_to(log_dir).parent)
        stage = log_file.stem

        took_secs = None
        with open(log_file) as f:
            for line in f:
                m = re.search(r"Took (\d+) seconds:", line)
                if m:
                    took_secs = int(m.group(1))

        if took_secs is not None and took_secs > 0:
            timings.append((took_secs, design, stage))

    timings.sort(reverse=True)
    return timings


def format_duration(seconds):
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def print_active(stages, elapsed):
    """Print current active stages."""
    if not stages:
        return
    # Group by design
    by_design = defaultdict(list)
    for s in stages:
        parts = s.rsplit("/", 1)
        if len(parts) == 2:
            by_design[parts[0]].append(parts[1])
        else:
            by_design["?"].append(s)

    prefix = f"[{format_duration(elapsed):>7s}]"
    lines = []
    for design in sorted(by_design):
        substages = ", ".join(by_design[design])
        lines.append(f"  {design}: {substages}")

    print(f"{prefix} {len(stages)} active stages:")
    for line in lines:
        print(line)
    sys.stdout.flush()


def print_timings(timings, top_n=25):
    """Print timing table."""
    if not timings:
        print("\nNo stage timings found.")
        return

    print(f"\n{'='*70}")
    print(f"{'Elapsed':>8s}  {'Design':<45s}  {'Stage'}")
    print(f"{'-'*8}  {'-'*45}  {'-'*15}")
    for secs, design, stage in timings[:top_n]:
        print(f"{format_duration(secs):>8s}  {design:<45s}  {stage}")
    if len(timings) > top_n:
        print(f"  ... and {len(timings) - top_n} more stages < {timings[top_n][0]}s")
    print(f"{'='*70}")
    sys.stdout.flush()


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ["//test/..."]

    cmd = ["bazelisk", "test"] + args
    print(f"Running: {' '.join(cmd)}")
    print()
    sys.stdout.flush()

    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # Monitor active stages while test runs
    last_stages = []
    try:
        while proc.poll() is None:
            time.sleep(10)
            elapsed = int(time.time() - start)
            stages = get_active_stages()
            if stages != last_stages:
                print_active(stages, elapsed)
                last_stages = stages
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        print("\nInterrupted.")
        return 1

    elapsed = int(time.time() - start)
    exit_code = proc.returncode

    # Print Bazel output summary
    output = proc.stdout.read().decode(errors="replace")
    for line in output.splitlines():
        if any(
            kw in line
            for kw in ["PASSED", "FAILED", "Elapsed time:", "Executed", "tests pass"]
        ):
            print(line)
    print()

    # Find log directory
    log_dirs = [
        "bazel-bin/test/logs",
        "bazel-bin/test/smoketest/logs",
    ]

    all_timings = []
    for d in log_dirs:
        all_timings.extend(get_stage_timings(d))
    all_timings.sort(reverse=True)

    print_timings(all_timings)
    print(f"\nTotal wall time: {format_duration(elapsed)}")
    print(f"Exit code: {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
