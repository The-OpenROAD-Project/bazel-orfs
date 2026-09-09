#!/usr/bin/env python3
"""Reduce one profiled run to a JSON the figures are drawn from.

Reads the directory profile.sh wrote and emits:

  wall_s, cpu_pct, peak_mb        from ORFS's closing "Elapsed time:" line
  counters                        from perf stat
  phases                          the stamped log's progress markers, so a
                                  figure can shade initial place, Nesterov
                                  and place_pins
  busy_threads[]                  per-second count of distinct threads that
                                  took at least one sample
  working_threads[]               the same, counting only samples outside
                                  the OpenMP runtime's wait loops
  effective_threads[]             working samples per second over the
                                  sampling rate: thread-equivalents doing
                                  work, the shape of the serial fraction
  phase_share                     samples per phase, split working / spinning
  categories[]                    self-time share per code category
  symbols[]                       self-time share per function, top N
  dsos[]                          self-time share per shared object

Sample lines are perf script's default format:

  openroad 79765 28484.329895: 21216994 cpu/cycles/P: 5a5638 sym+0x1 (dso)
"""

import argparse
import collections
import json
import re
from pathlib import Path

SAMPLE = re.compile(
    r"^\s*(?P<comm>\S+)\s+(?P<tid>\d+)\s+(?P<time>\d+\.\d+):\s+\d+\s+\S+:\s+"
    r"(?P<ip>[0-9a-f]+)\s+(?P<sym>.+?)\s+\((?P<dso>[^)]*)\)\s*$"
)
# With --call-graph the header carries no symbol; the leaf is the first
# indented frame line that follows it.
CG_HEADER = re.compile(
    r"^\s*(?P<comm>\S+)\s+(?P<tid>\d+)\s+(?P<time>\d+\.\d+):\s+\d+\s+\S+:\s*$"
)
CG_FRAME = re.compile(
    r"^\s+(?P<ip>[0-9a-f]+)\s+(?P<sym>.+?)(?:\+0x[0-9a-f]+)?\s+\((?P<dso>[^)]*)\)\s*$"
)


def iter_samples(f):
    """Yield (comm, tid, time, sym, dso) from flat or call-graph perf script output."""
    pending = None
    for line in f:
        if pending is not None:
            m = CG_FRAME.match(line)
            if m:
                yield pending + (m.group("sym"), m.group("dso"))
                pending = None
                continue
            if not line.strip():
                pending = None
        m = SAMPLE.match(line)
        if m:
            yield m.group("comm"), m.group("tid"), float(m.group("time")), m.group(
                "sym"
            ), m.group("dso")
            continue
        m = CG_HEADER.match(line)
        if m:
            pending = (m.group("comm"), m.group("tid"), float(m.group("time")))


ELAPSED = re.compile(
    r"Elapsed time: (?:(\d+):)?(\d+):([\d.]+)\[h:\]min:sec\. "
    r"CPU time: user ([\d.]+) sys ([\d.]+) \((\d+)%\)\. Peak memory: (\d+)KB"
)
STAMP = re.compile(r"^\[\s*([\d.]+)\] (.*)$")
# The log lines that mark a phase boundary, in the order they appear.
MARKERS = [
    ("gpl_setup", re.compile(r"^global_placement ")),
    ("initial_place", re.compile(r"Execute Conjugate Gradient Initial Placement")),
    (
        "nesterov",
        re.compile(r"^\[NesterovSolve\]|Iteration\s+\|\s+Overflow|^\s*\d+ \|"),
    ),
    ("place_pins", re.compile(r"^place_pins ")),
    ("write_db", re.compile(r"^write_db ")),
]


def parse_elapsed(text):
    m = ELAPSED.search(text)
    if not m:
        return {}
    h, mnt, sec, user, sys_, pct, kb = m.groups()
    wall = (int(h or 0) * 60 + int(mnt)) * 60 + float(sec)
    return {
        "wall_s": wall,
        "user_s": float(user),
        "sys_s": float(sys_),
        "cpu_pct": int(pct),
        "peak_mb": int(kb) / 1024,
    }


def parse_stat(text):
    counters = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([\d.,]+)\s+(\S+)", line)
        if m:
            counters[m.group(2)] = float(m.group(1).replace(",", "").replace(".", "."))
    return counters


def parse_phases(log_text):
    """First stamp at which each marker fires; missing markers are absent."""
    phases = {}
    for line in log_text.splitlines():
        m = STAMP.match(line)
        if not m:
            continue
        t, body = float(m.group(1)), m.group(2)
        # Everything before the global_placement command is load_design:
        # liberty, ODB, SDC. It starts at the first stamped line.
        phases.setdefault("load", t)
        for name, rx in MARKERS:
            if name not in phases and rx.search(body):
                phases[name] = t
    return phases


SPIN = re.compile(
    r"^(kmp_flag|__kmp_|kmp_|__kmpc_|__sched_yield|sched_yield|__GI___sched_yield)"
)

# Coarse buckets for the "what takes time" figure. Order matters: first
# match wins.
CATEGORIES = [
    ("OpenMP wait", SPIN),
    ("kernel / unknown", re.compile(r"^\[unknown\]|^0x[0-9a-f]+$")),
    ("initial place (Eigen)", re.compile(r"Eigen::|InitialPlace")),
    (
        "wirelength gradient",
        re.compile(r"WireLength|updateBox|getGCell\(|GNet::|GPin::|updateWireLength"),
    ),
    ("density (bins, FFT)", re.compile(r"Density|BinGrid|FFT|fft|scatter|Bin\b")),
    ("hpwl", re.compile(r"Hpwl|HPWL")),
    (
        "Nesterov update",
        re.compile(
            r"nesterovUpdate|updateNextIter|updateGradients|SLP|Coordi|Snapshot"
        ),
    ),
    ("db / sta load", re.compile(r"odb::|sta::|dbSta|Liberty|read_")),
    ("place_pins (ppl)", re.compile(r"ppl::")),
    (
        "libc / alloc",
        re.compile(
            r"malloc|free|memcpy|memset|memmove|operator new|operator delete|std::__1::__hash|std::__1::vector"
        ),
    ),
]


def category(sym):
    for name, rx in CATEGORIES:
        if rx.search(sym):
            return name
    return "other gpl / openroad"


def phase_at(phases, t):
    """Name of the phase whose stamp is the latest one at or before t."""
    best = None
    for name, start in phases.items():
        if start <= t and (best is None or start >= phases[best]):
            best = name
    return best or "pre"


def parse_samples(path, comm_filter, phases, log_t0, freq):
    per_second = collections.defaultdict(set)
    working_per_second = collections.defaultdict(set)
    working_samples = collections.Counter()
    symbols = collections.Counter()
    dsos = collections.Counter()
    categories = collections.Counter()
    phase_share = collections.defaultdict(lambda: {"working": 0, "spinning": 0})
    total = 0
    t0 = None
    with open(path, errors="replace") as f:
        for comm, tid, t, sym, dso in iter_samples(f):
            if comm_filter and not comm.startswith(comm_filter):
                continue
            if t0 is None:
                t0 = t
            total += 1
            rel = t - t0
            sec = int(rel)
            sym = sym.split("+0x")[0]
            spinning = bool(SPIN.match(sym))
            per_second[sec].add(tid)
            if not spinning:
                working_per_second[sec].add(tid)
                working_samples[sec] += 1
            symbols[sym] += 1
            dsos[Path(dso).name] += 1
            categories[category(sym)] += 1
            # perf's clock starts at the first sample; the log's at process
            # start. The gap is the fraction of a second before openroad
            # got its first sample, small against the phases.
            ph = phase_at(phases, rel + log_t0)
            phase_share[ph]["spinning" if spinning else "working"] += 1
    n = max(per_second, default=-1) + 1
    busy = [len(per_second[s]) for s in range(n)]
    working = [len(working_per_second[s]) for s in range(n)]
    # Thread-equivalents doing work: working samples per second over the
    # sampling rate. 48 threads all working read 48; 48 threads of which
    # 47 spin read 1. Per-second thread counts cannot tell those apart.
    effective = [round(working_samples[s] / freq, 2) for s in range(n)]
    return total, busy, working, effective, symbols, dsos, categories, dict(phase_share)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument(
        "--comm",
        default="openroad",
        help="command name prefix; a BYO binary may be named openroad-<variant>",
    )
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--freq", type=float, default=199.0, help="perf record -F used")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()
    d = Path(args.run_dir)

    logs = sorted(d.glob("*.log"))
    log_text = logs[0].read_text(errors="replace") if logs else ""
    out = {"run": {}}
    for line in (d / "run.txt").read_text().splitlines():
        k, _, v = line.partition("=")
        out["run"][k] = v
    out.update(parse_elapsed(log_text))
    out["counters"] = (
        parse_stat((d / "stat.txt").read_text()) if (d / "stat.txt").exists() else {}
    )
    out["phases"] = parse_phases(log_text)
    # The first stamp in the log is the first line openroad printed, i.e.
    # roughly when the process started taking samples.
    stamps = [float(m.group(1)) for m in map(STAMP.match, log_text.splitlines()) if m]
    log_t0 = stamps[0] if stamps else 0.0
    total, busy, working, effective, symbols, dsos, categories, phase_share = (
        parse_samples(d / "samples.txt", args.comm, out["phases"], log_t0, args.freq)
    )
    out["samples"] = total
    out["busy_threads"] = busy
    out["working_threads"] = working
    out["effective_threads"] = effective
    out["categories"] = [
        {"category": c, "share": n / total} for c, n in categories.most_common()
    ]
    out["phase_share"] = {
        k: {kk: vv / total for kk, vv in v.items()} for k, v in phase_share.items()
    }
    starts = sorted(out["phases"].items(), key=lambda kv: kv[1])
    end = out.get("wall_s", starts[-1][1] if starts else 0)
    out["phase_seconds"] = {
        name: round((nxt[1] if nxt else end) - t, 3)
        for (name, t), nxt in zip(starts, starts[1:] + [None])
    }
    out["symbols"] = [
        {"symbol": s, "share": n / total} for s, n in symbols.most_common(args.top)
    ]
    out["dsos"] = [{"dso": s, "share": n / total} for s, n in dsos.most_common(20)]
    text = json.dumps(out, indent=1)
    if args.output:
        Path(args.output).write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
