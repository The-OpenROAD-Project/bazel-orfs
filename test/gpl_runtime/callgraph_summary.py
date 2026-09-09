#!/usr/bin/env python3
"""Attribute wall time to code from a call-graph perf recording.

Reads `perf script --no-inline` output with frame-pointer call chains and
answers two questions the flat profile cannot:

1. **Where does the wall go?** The main thread is always on CPU -- working,
   or spinning at a join barrier while it waits for the slowest worker --
   so its samples are wall time. Each main-thread sample is attributed to
   the outermost placer phase on its stack (`InitialPlace`, Nesterov,
   load, `place_pins`) and to the first placer-level function below that,
   which is what a patch would target.

2. **Why are the workers idle?** A worker spinning in `__kmp_fork_barrier`
   is waiting for the *next* parallel region: the master is running
   serial code. One spinning in `__kmp_join_barrier` / `__kmp_barrier`
   finished its share and waits for peers: load imbalance. The two need
   different fixes.

Usage: callgraph_summary.py <run_dir> [-o out.json]
"""

import argparse
import collections
import json
import re
from pathlib import Path

HEADER = re.compile(
    r"^(?P<comm>\S+)\s+(?P<tid>\d+)\s+(?P<time>\d+\.\d+):\s+\d+\s+\S+:\s*$"
)
FRAME = re.compile(r"^\s+[0-9a-f]+\s+(?P<sym>.+?)(?:\+0x[0-9a-f]+)?\s+\(.*\)\s*$")

SPIN = re.compile(r"^(kmp_flag|__kmp_|kmp_|__kmpc_|__sched_yield|sched_yield)")
FORK_BARRIER = re.compile(r"__kmp_fork_barrier|__kmp_launch_thread")
JOIN_BARRIER = re.compile(
    r"__kmp_join_barrier|__kmp_barrier|__kmpc_barrier|__kmp_end_split_barrier"
)

# Outermost phase markers, matched root-to-leaf, first hit wins.
PHASES = [
    ("initial place", re.compile(r"InitialPlace::|Replace::doInitialPlace")),
    (
        "Nesterov",
        re.compile(r"NesterovPlace::doNesterovPlace|Replace::doNesterovPlace"),
    ),
    (
        "gpl setup",
        re.compile(
            r"Replace::(doPlace|initNesterovPlace|initPlacerBase)|PlacerBase(Common)?::init|NesterovBase(Common)?::NesterovBase|NesterovPlace::init|NesterovPlace::NesterovPlace|BinGrid::initBins"
        ),
    ),
    ("place_pins", re.compile(r"ppl::")),
    (
        "load_design",
        re.compile(
            r"read_liberty|readLiberty|LibertyReader|LibertyParser|read_db|dbDatabase::read|dbOStream|dbIStream|sta::Sdc|read_sdc|sta::.*Reader|LibertyScanner"
        ),
    ),
    ("write_db", re.compile(r"dbDatabase::write|write_db|dbOStream")),
    ("buffer_ports / resizer", re.compile(r"rsz::")),
]
GPL_FRAME = re.compile(r"^(gpl::|Eigen::)")
IN_REGION = re.compile(r"__kmpc_fork_call|omp_outlined|__kmp_invoke_microtask")


def clean(sym):
    sym = re.sub(r"\s*\[clone [^\]]*\]", "", sym)
    sym = re.sub(r"\(.*\)( const)?$", "()", sym)
    return sym.replace("std::__1::", "std::")


def samples(path):
    comm = tid = None
    frames = []
    with open(path, errors="replace") as f:
        for line in f:
            m = HEADER.match(line)
            if m:
                if comm is not None:
                    yield comm, tid, frames
                comm, tid, frames = m.group("comm"), int(m.group("tid")), []
                continue
            m = FRAME.match(line)
            if m and comm is not None:
                frames.append(m.group("sym"))
    if comm is not None:
        yield comm, tid, frames


def attribute(frames):
    """(phase, target) for a leaf-first stack."""
    root_first = list(reversed(frames))
    phase = "other"
    pi = None
    for i, fr in enumerate(root_first):
        for name, rx in PHASES:
            if rx.search(fr):
                phase, pi = name, i
                break
        if pi is not None:
            break
    target = None
    if pi is not None:
        rx = dict(PHASES)[phase]
        for fr in root_first[pi + 1 :]:
            # Skip the phase's own wrappers (Replace::doNesterovPlace ->
            # NesterovPlace::doNesterovPlace), OpenMP outlined bodies and
            # Eigen internals: the target is the placer function a patch
            # would name.
            if (
                rx.search(fr)
                or "omp_outlined" in fr
                or fr.startswith("Eigen::internal")
            ):
                continue
            if GPL_FRAME.match(fr):
                target = clean(fr)
                break
        if target is None:
            target = clean(root_first[pi]) + "  [self]"
    if target is None:
        # Fall back to the outermost non-runtime frame under main.
        for fr in root_first:
            if fr.startswith(("gpl::", "ppl::", "sta::", "odb::", "rsz::", "ord::")):
                target = clean(fr)
                break
    return phase, target or clean(frames[0] if frames else "?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument(
        "--comm",
        default="openroad",
        help="command name prefix; a BYO binary may be named openroad-<variant>",
    )
    ap.add_argument("-o", "--output")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()
    d = Path(args.run_dir)

    main_tid = None
    main_total = 0
    worker_root = re.compile(r"start_thread|__GI___clone3|__clone")
    main_phase = collections.Counter()
    main_target = collections.Counter()
    main_wait = collections.Counter()  # phase -> samples where master spins at join
    main_leaf = collections.Counter()  # (phase, leaf symbol) for serial hot spots
    main_state = collections.Counter()  # serial / parallel region / waiting
    target_state = collections.defaultdict(collections.Counter)
    worker_total = 0
    worker_state = collections.Counter()
    worker_idle_phase = (
        collections.Counter()
    )  # what the master was doing is unknown here; keep region parent
    for comm, tid, frames in samples(d / "samples.txt"):
        if not comm.startswith(args.comm) or not frames:
            continue
        # A worker's stack bottoms out in start_thread/clone; the main
        # thread's does not. Deciding by stack rather than by the first tid
        # seen is what survives a worker taking the first sample.
        is_main = not any(worker_root.search(fr) for fr in frames[-3:])
        if is_main and main_tid is None:
            main_tid = tid
        leaf = frames[0]
        spinning = bool(SPIN.match(leaf))
        if is_main:
            main_total += 1
            phase, target = attribute(frames)
            main_phase[phase] += 1
            in_region = any(IN_REGION.search(fr) for fr in frames)
            if spinning:
                state = "waiting at barrier"
                main_wait[phase] += 1
            elif in_region:
                state = "parallel region"
            else:
                state = "serial"
            main_state[state] += 1
            main_target[(phase, target)] += 1
            target_state[(phase, target)][state] += 1
            if not spinning and not in_region:
                main_leaf[(phase, clean(leaf))] += 1
        else:
            worker_total += 1
            stack = " ".join(frames)
            if spinning and FORK_BARRIER.search(stack):
                worker_state[
                    "idle: waiting for next region (master runs serial code)"
                ] += 1
            elif spinning and JOIN_BARRIER.search(stack):
                worker_state["waiting at join barrier (imbalance)"] += 1
            elif spinning:
                worker_state["other OpenMP wait"] += 1
            else:
                worker_state["working"] += 1

    out = {
        "main_tid": main_tid,
        "main_samples": main_total,
        "worker_samples": worker_total,
        "main_phase_share": {k: v / main_total for k, v in main_phase.most_common()},
        "main_master_wait_share": {
            k: v / main_total for k, v in main_wait.most_common()
        },
        "main_state_share": {k: v / main_total for k, v in main_state.most_common()},
        "main_targets": [
            {
                "phase": p,
                "target": t,
                "share": n / main_total,
                "serial": target_state[(p, t)]["serial"] / main_total,
                "parallel": target_state[(p, t)]["parallel region"] / main_total,
                "waiting": target_state[(p, t)]["waiting at barrier"] / main_total,
            }
            for (p, t), n in main_target.most_common(args.top)
        ],
        "main_leaves": [
            {"phase": p, "symbol": t, "share": n / main_total}
            for (p, t), n in main_leaf.most_common(args.top)
        ],
        "worker_state_share": (
            {k: v / worker_total for k, v in worker_state.most_common()}
            if worker_total
            else {}
        ),
    }
    if args.output:
        Path(args.output).write_text(json.dumps(out, indent=1))
    print(f"main thread {main_tid}: {main_total} samples; workers: {worker_total}")
    print("wall by phase (main thread):")
    for k, v in out["main_phase_share"].items():
        w = out["main_master_wait_share"].get(k, 0)
        print(f"  {v:6.1%}  {k}   (of which master waiting at barrier {w:.1%})")
    print("main thread state:")
    for k, v in out["main_state_share"].items():
        print(f"  {v:6.1%}  {k}")
    print("wall by target (main thread): total = serial + parallel + waiting")
    for t in out["main_targets"]:
        print(
            f"  {t['share']:6.1%} = {t['serial']:5.1%} + {t['parallel']:5.1%} + {t['waiting']:5.1%}  {t['phase']:14s} {t['target'][:80]}"
        )
    print("wall by leaf symbol (main thread, serial code only):")
    for t in out["main_leaves"]:
        print(f"  {t['share']:6.1%}  {t['phase']:14s} {t['symbol'][:100]}")
    print("worker threads:")
    for k, v in out["worker_state_share"].items():
        print(f"  {v:6.1%}  {k}")


if __name__ == "__main__":
    main()
