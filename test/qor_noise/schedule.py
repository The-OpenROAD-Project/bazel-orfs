#!/usr/bin/env python3

"""Turn a design set into a PR-CI wall time on a machine of a given shape.

The earlier parts of this study answer "which designs, and how many". They
answer it in instance counts, which is a proxy for cost and not a cost. What
a maintainer actually has is a machine -- so many vCPUs, so much RAM -- and
a patience budget measured in minutes. This module is the bridge.

Three parameters decide the answer, and none of them is a property of the
design set:

  * **cores**, and how many of them each design is given. A design handed
    more threads finishes sooner, but sub-linearly: much of the RTL-to-GDS
    flow is serial (synthesis, detailed placement, large parts of timing
    repair), so the speedup is Amdahl-limited by `serial_fraction`. Giving
    every design 8 threads on a 64-core machine runs 8 designs at once;
    giving each 2 threads runs 32 at once, each more slowly. The optimum is
    not at either end and is found by sweeping.

  * **memory**, which caps concurrency independently of cores. A machine
    with plenty of vCPUs and not enough RAM runs fewer designs at once than
    its core count suggests, and the schedule has to respect that or the
    predicted wall time is fiction.

  * the **design set**, which fixes both the work and the longest pole.

Wall time is then a makespan, not a sum and not a maximum. With more designs
than slots the jobs queue, so the answer is a scheduling problem; longest-
processing-time-first list scheduling is used, which is within 4/3 - 1/(3m)
of optimal and is what any sensible CI runner approximates anyway.

Every model constant here is an ASSUMPTION with one measured anchor behind
it, declared in `Model` and overridable from the command line. They are the
weakest part of this study and are kept in one place so a reader can replace
them with measurements and re-run rather than having to believe them.
"""

import argparse
import dataclasses
import json
import sys


@dataclasses.dataclass
class Model:
    """Runtime and memory as functions of design size.

    `anchor_instances` / `anchor_minutes` / `anchor_threads` are one real
    measurement: an ORFS design of that size took that long with roughly
    that many cores busy. Everything else is scaled from it.
    """

    anchor_instances: float = 18383.0
    anchor_minutes: float = 20.0
    anchor_threads: float = 10.0
    # Runtime grows faster than instance count: detailed routing and timing
    # repair are both superlinear.
    size_exponent: float = 1.2
    # Fraction of the flow that does not speed up with more threads.
    serial_fraction: float = 0.5
    # Fixed cost no design escapes: process start, reading the PDK, writing
    # results. A 155-instance design is not 100x faster than a 15,500 one.
    floor_minutes: float = 1.0
    # Memory: a base footprint plus a per-instance term.
    base_gb: float = 0.7
    gb_per_instance: float = 40e-6

    def single_thread_minutes(self, instances):
        """Runtime at one thread, before any parallel speedup."""
        scaled = self.anchor_minutes * (instances / self.anchor_instances) ** self.size_exponent
        # Undo the anchor's own parallel speedup to recover a 1-thread cost.
        # The anchor ran WITH that speedup, so a single thread is slower by
        # exactly that factor -- multiply. Dividing here makes every
        # predicted wall time about three times too optimistic, which is
        # what schedule_test.test_anchor_reproduces_itself exists to catch.
        return scaled * self.speedup(self.anchor_threads)

    def speedup(self, threads):
        s = self.serial_fraction
        return 1.0 / (s + (1.0 - s) / max(threads, 1.0))

    def minutes(self, instances, threads):
        t = self.single_thread_minutes(instances) / self.speedup(threads)
        return max(t, self.floor_minutes)

    def memory_gb(self, instances):
        return self.base_gb + self.gb_per_instance * instances


def makespan(jobs, slots):
    """Longest-processing-time-first list scheduling.

    `jobs` is a list of minutes. Returns the wall time on `slots` identical
    workers. With slots >= len(jobs) this degenerates to max(jobs), which is
    the "wide machine" case the design-set discussion assumes.
    """
    if slots < 1:
        raise ValueError("need at least one slot")
    finish = [0.0] * slots
    for t in sorted(jobs, reverse=True):
        i = min(range(slots), key=lambda k: finish[k])
        finish[i] += t
    return max(finish)


def schedule(designs, sizes, model, vcpus, memory_gb, threads_per_design, smt=2.0):
    """Wall time and resource use for one (design set, machine, threads) point.

    vCPUs are hyperthreads; `smt` converts them to the cores the runtime
    model is calibrated in. Concurrency is limited by whichever of cores or
    memory runs out first.
    """
    cores = vcpus / smt
    by_cores = int(cores // max(threads_per_design, 1))
    peak_each = [model.memory_gb(sizes[d]) for d in designs]
    worst_gb = max(peak_each) if peak_each else 0.0
    by_memory = int(memory_gb // worst_gb) if worst_gb > 0 else len(designs)
    slots = max(min(by_cores, by_memory), 1)
    jobs = [model.minutes(sizes[d], threads_per_design) for d in designs]
    wall = makespan(jobs, slots)
    return {
        "designs": len(designs),
        "threads_per_design": threads_per_design,
        "slots": slots,
        "limited_by": "memory" if by_memory < by_cores else "cores",
        "wall_minutes": wall,
        "core_hours": sum(jobs) * threads_per_design / 60.0,
        "peak_memory_gb": min(slots, len(designs)) * worst_gb,
        "largest_design_gb": worst_gb,
    }


def best_threading(designs, sizes, model, vcpus, memory_gb, smt=2.0, choices=(1, 2, 4, 8, 16, 32)):
    """Sweep threads-per-design and keep the schedule with the least wall time.

    This is the parameter people get wrong in both directions: one thread per
    design wastes the machine on a serial tail, and all cores to one design
    wastes them on Amdahl's law.
    """
    best = None
    for threads in choices:
        if threads > vcpus / smt:
            continue
        got = schedule(designs, sizes, model, vcpus, memory_gb, threads, smt)
        if best is None or got["wall_minutes"] < best["wall_minutes"]:
            best = got
    return best


# Publicly documented Google Cloud shapes, as (vCPUs, GB).
MACHINES = {
    "n2-standard-16": (16, 64),
    "n2-standard-32": (32, 128),
    "n2-standard-64": (64, 256),
    "n2-standard-128": (128, 512),
    "n2-highmem-64": (64, 512),
    "c3-standard-176": (176, 704),
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--transitions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--serial-fraction", type=float, default=0.5)
    ap.add_argument("--gb-per-instance", type=float, default=40e-6)
    args = ap.parse_args(argv)

    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from select_designs import detected, load_events

    with open(args.analysis) as fh:
        a = json.load(fh)
    sizes = {d["design"]: d["instances"] for d in a["designs"] if d["instances"]}
    events = sorted(load_events(args.transitions), key=lambda e: e["when"])
    test = events[len(events) // 2 :]

    open_platforms = {
        "asap7",
        "gf180",
        "ihp-sg13g2",
        "nangate45",
        "sky130hd",
        "sky130hs",
    }
    candidates = [
        d
        for d in set().union(*[e["moved"] for e in test])
        if d in sizes and d.split("/")[0] in open_platforms
    ]

    model = Model(
        serial_fraction=args.serial_fraction, gb_per_instance=args.gb_per_instance
    )

    caps = sorted(set(int(sizes[d]) for d in candidates))
    points = []
    for cap in caps:
        chosen = [d for d in candidates if sizes[d] <= cap]
        if len(chosen) < 4:
            continue
        coverage = len(detected(test, set(chosen), 2)) / len(test)
        row = {
            "cap": cap,
            "coverage": coverage,
            "n_designs": len(chosen),
            "platforms": len(set(d.split("/")[0] for d in chosen)),
            "designs": sorted(chosen),
            "machines": {},
        }
        for name, (vcpus, gb) in MACHINES.items():
            row["machines"][name] = best_threading(chosen, sizes, model, vcpus, gb)
        points.append(row)

    # Pareto front on (wall time, coverage) per machine: a point survives
    # only if nothing cheaper detects at least as much.
    fronts = {}
    for name in MACHINES:
        ordered = sorted(points, key=lambda p: p["machines"][name]["wall_minutes"])
        front, best = [], -1.0
        for p in ordered:
            if p["coverage"] > best:
                front.append(p)
                best = p["coverage"]
        fronts[name] = [p["cap"] for p in front]

    out = {
        "model": dataclasses.asdict(model),
        "machines": {k: {"vcpus": v[0], "memory_gb": v[1]} for k, v in MACHINES.items()},
        "points": points,
        "pareto_caps": fronts,
        "test_events": len(test),
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {args.out}: {len(points)} points", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
