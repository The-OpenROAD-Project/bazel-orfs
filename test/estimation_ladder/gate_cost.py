"""What does one gate ensemble member actually cost?

Every runtime this study has published so far is wrong in the same two
ways, and both understate the estimator.

The accuracy sweeps run under `fork -parallel`, so members contend; and
`fork` quiesces the host to a single thread before forking, so each
member is single-threaded regardless of the machine. A number measured
that way is neither a clean serial time nor a clean parallel one, and
`measure_runtime.py` exists in this study precisely because "eight
concurrent runs measure contention between siblings as much as the
settings under test".

A gate's cost is a different question from a sweep's, so it gets its own
measurement: one member, alone on the machine, with all the threads it
would really have. That is the number a CI budget is built from.
"""

import argparse
import json
import os
import statistics
import time

from optuna_study import run_estimator, scratch_root

# Measured on multiplier_top: 470s at one thread against 86.6s at
# sixteen. Sublinear, as tool threading always is, so these are the
# factors used to translate between thread counts rather than assuming
# linear scaling.
SUBLINEAR_SPEEDUP = {1: 1.0, 2: 1.7, 4: 2.7, 8: 3.9, 16: 5.4, 32: 6.5, 64: 7.0}

RUNG = {
    "RUN_PLACE": "1",
    "RUN_MACRO_PLACE": "1",
    "PLACE_IOS": "0",
    "GPL_TIMING_DRIVEN": "0",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_VIRTUAL_CTS": "0",
    "CLOCK_MODE": "none",
    "RUN_REPAIR_DESIGN": "0",
    "RUN_GRT": "0",
    "RUN_REPAIR_TIMING": "0",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("estimator_exe")
    ap.add_argument("truth_json")
    ap.add_argument("design_name")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 8)
    args = ap.parse_args()

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    times = []
    for i in range(args.repeats):
        out = os.path.join(scratch_root(), f"gate_cost_{i}.json")
        t0 = time.time()
        run_estimator(
            args.estimator_exe,
            dict(RUNG, NUM_CORES=str(args.threads), CORE_AREA_EPS_SITES=str(i + 1)),
            args.truth_json,
            out_json=out,
        )
        dt = time.time() - t0
        times.append(dt)
        print(f"  member {i + 1}/{args.repeats}: {dt:.1f}s")

    med = statistics.median(times)
    print(
        f"\n{args.design_name}: one member = {med:.1f}s at {args.threads}"
        " threads, alone on the machine"
    )

    # Two regimes, because the right arrangement flips at k = cores and a
    # single table would misrepresent one of them.
    #
    # jobs * threads is the machine, so a member's threads are cores/k
    # when k < cores, and 1 when k >= cores. Thread scaling is sublinear:
    # measured on multiplier_top, one thread takes ~470s against 86.6s at
    # sixteen, a speedup of 5.4x for 16x the CPU. So more members at fewer
    # threads is the throughput choice, and fewer members at more threads
    # is the latency choice.
    t1 = med * SUBLINEAR_SPEEDUP.get(args.threads, args.threads)
    print(f"  implied single-threaded member: ~{t1:.0f}s")
    print(
        f"\n  {'k':>4s} {'cores':>6s} {'arrangement':>22s} {'one arm':>9s}"
        f" {'both arms':>10s}"
    )
    for cores in (16, 64, 256):
        for k in (8, 16, 40):
            if k >= cores:
                # Saturated: one thread each is the fastest arrangement.
                arrangement = f"{cores} x 1 thread"
                wall = (k / float(cores)) * t1
            else:
                # Spare cores: spend them on threads within each member.
                threads = max(1, cores // k)
                sp = SUBLINEAR_SPEEDUP.get(threads, threads)
                arrangement = f"{k} x {threads} threads"
                wall = t1 / sp
            print(
                f"  {k:>4d} {cores:>6d} {arrangement:>22s}"
                f" {wall / 60.0:>8.1f}m {2 * wall / 60.0:>9.1f}m"
            )
    print(
        "\n  Both arms only on a cold merge-base; a cached base ensemble" " halves it."
    )

    path = os.path.join(
        ws, "test/estimation_ladder", f"gate_cost_{args.design_name}.json"
    )
    with open(path, "w") as f:
        json.dump(
            {
                "design": args.design_name,
                "threads": args.threads,
                "times_s": times,
                "median_s": med,
                "rung": RUNG,
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
