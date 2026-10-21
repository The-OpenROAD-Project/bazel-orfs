"""Summarize the sweep's results.txt per design: each arm's mean over its
seeds, the noise band (the spread of the first arm's seeds) and every other
arm's change against the first, reg2reg only.

    python3 tools/headroom/sweep/report.py tmp/sweep/results.txt [design ...]

Prints a markdown table per design, for a design whose arms all have their
seeds in; a FAILED arm is listed as such.
"""

import collections
import re
import sys

LINE = re.compile(
    r"^(\S+) (\S+) seed(\d+) \((\d+)s\) period ([0-9.-]+) r2r_violating (\d+) "
    r"r2r_tns ([0-9.-]+) buffers (\d+) area ([0-9.]+) \| One-flop-loop floor: "
    r"([0-9.]+) at \S+ \((\d+) stages, (\d+) buffers"
)


def parse(path):
    runs = collections.defaultdict(lambda: collections.defaultdict(list))
    failed = collections.defaultdict(list)
    for line in open(path):
        m = LINE.match(line)
        if m:
            d, arm = m.group(1), m.group(2)
            runs[d][arm].append(
                dict(
                    secs=int(m.group(4)),
                    period=float(m.group(5)),
                    viol=int(m.group(6)),
                    tns=float(m.group(7)),
                    bufs=int(m.group(8)),
                    area=float(m.group(9)),
                    floor=float(m.group(10)),
                    loopbufs=int(m.group(12)),
                )
            )
        elif "FAILED" in line:
            parts = line.split()
            failed[parts[0]].append(" ".join(parts[1:]))
    return runs, failed


def mean(xs):
    return sum(xs) / len(xs)


def table(design, arms, failed):
    order = list(arms)
    first = order[0]
    base = arms[first]
    noise = max(r["period"] for r in base) - min(r["period"] for r in base)
    out = [
        "**%s** (noise band: %s seeds differ by %.1f in period)"
        % (design, first, noise),
        "",
        "| arm | seeds | reg2reg period | vs %s | r2r violating | r2r TNS | floor | loop buffers | buffers | area |"
        % first,
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    bp = mean([r["period"] for r in base])
    for arm in order:
        rs = arms[arm]
        p = mean([r["period"] for r in rs])
        delta = (
            ""
            if arm == first
            else "%+.1f%s" % (p - bp, " (noise)" if abs(p - bp) <= noise else "")
        )
        out.append(
            "| %s | %d | %.1f | %s | %.0f | %.1f | %.1f | %.1f | %.0f | %.1f |"
            % (
                arm,
                len(rs),
                p,
                delta,
                mean([r["viol"] for r in rs]),
                mean([r["tns"] for r in rs]),
                mean([r["floor"] for r in rs]),
                mean([r["loopbufs"] for r in rs]),
                mean([r["bufs"] for r in rs]),
                mean([r["area"] for r in rs]),
            )
        )
    for f in failed:
        out.append("| %s | | FAILED | | | | | | | |" % f)
    return "\n".join(out)


def main():
    runs, failed = parse(sys.argv[1])
    want = sys.argv[2:] or list(runs)
    print("\n\n".join(table(d, runs[d], failed.get(d, [])) for d in want if d in runs))


if __name__ == "__main__":
    main()
