#!/usr/bin/env python3
"""What one CoreMark iteration costs on the external bus.

The study's boundary is the core and its L1 (§3.1 of the paper). For
VeeR that boundary is a module -- swerv_wrapper contains the 16 kB
instruction cache and the 64 kB DCCM -- so the question "is the
benchmark actually inside it?" has an exact answer: how much traffic
leaves the block while the benchmark runs.

The answer is taken the same way the cycle count is, as a difference
between a two-iteration and a three-iteration run. That cancels the
boot, the .data copy from external memory and the cold pass that fills
the cache, and leaves the traffic of one hot iteration -- which is the
window the SAIF is captured over.

A non-zero instruction-bus delta is an instruction-cache miss rate. A
zero one says the hot loop never leaves the hardened block, which is
the condition the energy number needs in order to mean what it claims:
that nothing outside the boundary was exercised while the measurement
was being taken.

The bus is 64 bits wide, so a transfer moves 8 bytes.
"""

import argparse
import json
import sys

BUS_BYTES = 8


def read_probe(path):
    """Parse a `<name> <count>` probe file into a dict of ints."""
    counts = {}
    with open(path) as f:
        for line in f:
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 2:
                raise ValueError("{}: expected '<name> <count>', got {!r}".format(path, line))
            counts[fields[0]] = int(fields[1])
    if not counts:
        raise ValueError("{}: no counters".format(path))
    return counts


def per_iteration(probe_2, probe_3):
    """The traffic one CoreMark iteration adds, counter by counter.

    A negative delta is not a small measurement error: the counters are
    free-running and monotonic, so the three-iteration run cannot do
    less work than the two-iteration one. It means the two probes are
    not what they claim to be.
    """
    if sorted(probe_2) != sorted(probe_3):
        raise ValueError(
            "the two probes carry different counters: {} against {}".format(
                sorted(probe_2), sorted(probe_3)
            )
        )
    out = {}
    for name in sorted(probe_2):
        delta = probe_3[name] - probe_2[name]
        if delta < 0:
            raise ValueError(
                "{} went backwards between the two runs ({} -> {}); the "
                "counters are monotonic, so these are not a matched "
                "pair".format(name, probe_2[name], probe_3[name])
            )
        out[name] = delta
    return out


def summarise(probe_2, probe_3, cycles_per_iteration=None):
    deltas = per_iteration(probe_2, probe_3)
    result = {
        "transfers_per_iteration": deltas,
        "bytes_per_iteration": dict(
            (name, count * BUS_BYTES) for name, count in deltas.items()
        ),
        "boot_transfers": dict(probe_2),
        "resident": all(count == 0 for count in deltas.values()),
    }
    if cycles_per_iteration:
        result["cycles_per_iteration"] = cycles_per_iteration
        result["transfers_per_kilocycle"] = dict(
            (name, 1000.0 * count / cycles_per_iteration)
            for name, count in deltas.items()
        )
    return result


def report(result, out=sys.stdout):
    if result["resident"]:
        out.write(
            "one CoreMark iteration leaves the hardened block entirely "
            "untouched: every external-bus counter is unchanged between "
            "the two- and three-iteration runs.\n"
        )
    for name in sorted(result["transfers_per_iteration"]):
        out.write(
            "  {:<12} {:>8} transfers/iteration  ({} bytes; {} during boot)\n".format(
                name,
                result["transfers_per_iteration"][name],
                result["bytes_per_iteration"][name],
                result["boot_transfers"][name],
            )
        )


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-2", required=True, help="the 2-iteration .busprobe")
    parser.add_argument("--probe-3", required=True, help="the 3-iteration .busprobe")
    parser.add_argument(
        "--per-mhz",
        help="the *_per_mhz.json, to express the traffic per kilocycle",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])

    cycles = None
    if args.per_mhz:
        with open(args.per_mhz) as f:
            cycles = json.load(f)["cycles_per_iteration"]

    result = summarise(read_probe(args.probe_2), read_probe(args.probe_3), cycles)

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
