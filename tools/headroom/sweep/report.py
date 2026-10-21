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
    """Each arm against the first, in percent of the first arm's minimum
    reg2reg period (OpenROAD-flow-scripts#4583), with the first arm's seed
    spread as the noise band, and a verdict on the loop defect."""
    order = list(arms)
    first = order[0]
    base = arms[first]
    bp = mean([r["period"] for r in base])
    noise = 100 * (max(r["period"] for r in base) - min(r["period"] for r in base)) / bp
    out = [
        "**%s**: noise band %.2f %% (the %s seeds' spread in reg2reg period)"
        % (design, noise, first),
        "",
        "| arm | seeds | reg2reg period | vs %s | r2r violating | r2r TNS | floor | loop buffers | buffers | area |"
        % first,
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    verdict = ""
    for arm in order:
        rs = arms[arm]
        p = mean([r["period"] for r in rs])
        d = 100 * (p - bp) / bp
        delta = (
            ""
            if arm == first
            else "%+.2f %%%s" % (d, " (noise)" if abs(d) <= noise else "")
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
        if "iso" in arm:
            verdict = judge(base, rs, d, noise)
    for f in failed:
        out.append("| %s | | FAILED | | | | | | | |" % f)
    if failed:
        verdict = "broken: an arm failed"
    if verdict:
        out += ["", "Verdict: " + verdict]
    return "\n".join(out)


def judge(base, iso, d, noise):
    """fixed / fixed, and it matters / not applicable / broken, from the
    loop buffers, the floor, the period change and the area."""
    if len(base) < 2 or len(iso) < 2:
        return "pending: fewer than two seeds in"
    before = mean([r["loopbufs"] for r in base])
    after = mean([r["loopbufs"] for r in iso])
    base_area = mean([r["area"] for r in base])
    area = 100 * (mean([r["area"] for r in iso]) / base_area - 1) if base_area else 0.0
    if d > noise:
        return "broken: reg2reg period %+.2f %%, beyond the noise band" % d
    if area > max(noise, 1.0):
        return "broken: area %+.2f %%" % area
    if before == 0:
        return "not applicable: no buffer on the worst loop"
    if after >= before:
        return "not fixed: %.1f buffers on the worst loop before, %.1f after" % (
            before,
            after,
        )
    floor = mean([r["floor"] for r in iso]) - mean([r["floor"] for r in base])
    what = "fixed: worst loop's buffers %.1f to %.1f, floor %+.1f" % (
        before,
        after,
        floor,
    )
    if d < -noise:
        return (
            what
            + ", and it matters: reg2reg period %+.2f %%, beyond the noise band" % d
        )
    return what + ", reg2reg period within noise"


def main():
    runs, failed = parse(sys.argv[1])
    want = sys.argv[2:] or list(runs)
    print("\n\n".join(table(d, runs[d], failed.get(d, [])) for d in want if d in runs))


if __name__ == "__main__":
    main()
