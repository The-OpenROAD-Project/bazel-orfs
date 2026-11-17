#!/usr/bin/env python3
"""Which modules to keep: the parallel synthesis report.

Partitioned synthesis takes as long as its longest partition. This report
reads what a synthesis already wrote and says which partition that is and
which modules inside it, kept, would split it:

- per partition (each kept module and the top): wall time, the pass that
  took most of it, cell count and area, from the partition's
  partition_<name>_stat.txt (synth_partition.sh: the yosys log's timing
  lines and synth.tcl's synth_stat.txt);
- per partition, the modules synthesized into it that are not kept,
  ranked by estimated size: the keep candidates. The size is yosys's
  keep_hierarchy -min_cost estimate, the one SYNTH_MINIMUM_KEEP_SIZE
  compares against: each module's own gates (keep_hierarchy -min_cost 1
  on the coarse design logs one line per module, synth_keep_costs.tcl)
  plus those of the modules under it that are not kept, by instance;
- one line naming the partition that sets the time and the candidates
  that would split it;
- the slow partitions: those over an optional wall-time budget, and those
  where one pass takes most of the wall time, each with a suggestion.
  Report only: times vary by machine, so nothing here fails a build.

  keep_report.py --top TOP --kept kept_modules.json --rtlil CANON.rtlil
      --costs keep_costs.txt --out keep_report.md [--budget SECONDS] STAT...
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rtlil_names import base_name, resolve  # noqa: E402

KEEPING = re.compile(r"Keeping (\S+) \(estimated size above threshold: (\d+) > \d+\)")
SECTION = re.compile(r"^=== partition (\S+)\s*$")
END_OF_SCRIPT = re.compile(r"End of script\..*\btime: ([\d.]+)s")
ELAPSED = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):([\d.]+)")
TIME_SPENT = re.compile(r"Time spent: (\d+)% \d+x (\S+) \((\d+) sec\)")
STAT_HEADER = re.compile(r"^=== (\S+) ===\s*$")
OLD_CELLS = re.compile(r"^\s*Number of cells:\s+(\d+)")
OLD_AREA = re.compile(r"^\s*Chip area for (?:top )?module '\\?(\S+?)':\s+([\d.eE+-]+)")
NEW_CELLS = re.compile(r"^\s*(\d+)\s+(\S+)(?:\s+\d+\s+\S+)?\s+cells\s*$")


def rtlil_name(name):
    """A module's RTLIL name as yosys logs it: without the leading `\\`."""
    return name[1:] if name.startswith("\\") else name


def read_hierarchy(lines):
    """{module: Counter(child module: instances)} of an RTLIL text, and
    the set of modules it declares as black boxes."""
    cells = {}
    blackboxes = set()
    module = None
    attributes = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("attribute ") and module is None:
            attributes.append(stripped)
        elif line.startswith("module "):
            module = rtlil_name(line.split()[1])
            cells[module] = Counter()
            if any(a.split()[1] in ("\\blackbox", "\\whitebox") for a in attributes):
                blackboxes.add(module)
            attributes = []
        elif line.startswith("end") and stripped == "end" and not line[0].isspace():
            module = None
        elif module is not None and stripped.startswith("cell "):
            cells[module][rtlil_name(stripped.split()[1])] += 1
    return (
        {
            m: Counter({c: n for c, n in kids.items() if c in cells})
            for m, kids in cells.items()
        },
        blackboxes,
    )


def read_costs(lines):
    """{module: its own estimated gates} from keep_hierarchy -min_cost 1's log."""
    costs = {}
    for line in lines:
        m = KEEPING.search(line)
        if m:
            costs[m.group(1)] = int(m.group(2))
    return costs


def as_rtlil(module):
    return module if module.startswith("$") else "\\" + module


def kept_set(kept_names, modules):
    """The modules a keep list keeps: every spelling of every name."""
    kept = set()
    for module in modules:
        base = base_name(as_rtlil(module))
        for name in kept_names:
            if module == name or base == name or base.startswith(name + "$"):
                kept.add(module)
    return kept


def keep_names(modules):
    """{module: the name SYNTH_KEEP_MODULES takes for it}: the design's
    name when it resolves to this module (rtlil_names.py), else the name
    slang gave this instance."""
    rtlil = [as_rtlil(m) for m in modules]
    bases = {m: base_name(r) or m for m, r in zip(modules, rtlil)}
    short = {
        m: b.split("$", 1)[0] if b.find("$", 1) > 0 else b for m, b in bases.items()
    }
    found = resolve(sorted(set(short.values())), rtlil)
    return {
        m: short[m] if found.get(short[m]) == as_rtlil(m) else bases[m] for m in modules
    }


class Sizes:
    """keep_hierarchy -min_cost's size: own gates plus the gates of every
    module under it that is not kept, once per instance."""

    def __init__(self, children, costs, kept):
        self.children = children
        self.costs = costs
        self.kept = kept
        self.memo = {}

    def size(self, module):
        if module not in self.memo:
            total = self.costs.get(module, 0)
            for child, n in self.children.get(module, {}).items():
                if child not in self.kept:
                    total += n * self.size(child)
            self.memo[module] = total
        return self.memo[module]

    def candidates(self, partition):
        """{module: instances} synthesized into the partition, kept ones
        and the partition itself excluded."""
        found = Counter()

        def walk(module, times):
            for child, n in self.children.get(module, {}).items():
                if child in self.kept or child == partition:
                    continue
                found[child] += times * n
                walk(child, times * n)

        walk(partition, 1)
        return found


def read_stats(texts):
    """{partition module: {seconds, pass, pass_seconds, cells, area}} from
    the partitions' stat files."""
    out = {}
    for text in texts:
        current = None
        block = None
        for line in text.splitlines():
            s = SECTION.match(line)
            if s:
                current = rtlil_name(s.group(1))
                out[current] = {}
                block = None
                continue
            if current is None:
                continue
            row = out[current]
            m = ELAPSED.search(line)
            if m:
                row["seconds"] = (
                    int(m.group(1) or 0) * 3600
                    + int(m.group(2)) * 60
                    + float(m.group(3))
                )
                continue
            m = END_OF_SCRIPT.search(line)
            if m:
                row.setdefault("seconds", float(m.group(1)))
                continue
            m = TIME_SPENT.search(line)
            if m:
                row["pass"] = m.group(2)
                row["pass_seconds"] = int(m.group(3))
                continue
            m = STAT_HEADER.match(line)
            if m:
                block = rtlil_name(m.group(1).lstrip("\\"))
                continue
            if block != current:
                continue
            m = OLD_CELLS.match(line) or NEW_CELLS.match(line)
            if m and "cells" not in row:
                row["cells"] = int(m.group(1))
                if m.re is NEW_CELLS and m.group(2) != "-":
                    row["area"] = float(m.group(2))
                continue
            m = OLD_AREA.match(line)
            if m:
                row["area"] = float(m.group(2))
    return out


DOMINANT_SHARE = 0.9

REMEDIES = {
    "abc": [
        "try ABC_AREA=1 for this partition (per-partition arguments)",
        "if it's mux trees, pre-map them (muxcover)",
    ],
}


def slow_partitions(rows, budget):
    """The rows over budget (seconds, 0 for none) or with one pass taking
    DOMINANT_SHARE of their wall time, each with why and what to try."""
    out = []
    for r in rows:
        seconds = r["seconds"]
        if not seconds:
            continue
        over = bool(budget) and seconds > budget
        share = (r["pass_seconds"] or 0) / seconds if r["pass"] else 0
        dominant = share >= DOMINANT_SHARE
        if not (over or dominant):
            continue
        why = []
        if over:
            why.append(f"{fmt(seconds, 1)} s, over the {fmt(budget)} s budget")
        if dominant:
            why.append(f"{r['pass']} takes {share:.0%} of its wall time")
            remedies = REMEDIES.get(
                r["pass"],
                [
                    f"the time is in yosys's `{r['pass']}` pass; see what it works on in this partition's log"
                ],
            )
        else:
            remedies = ["split it: see its keep candidates below, if it has any"]
        out.append({"name": r["name"], "why": why, "remedies": remedies})
    return out


def fmt(x, digits=0):
    if x is None:
        return "?"
    return f"{x:,.{digits}f}"


def report(top, kept_names, children, blackboxes, costs, stats, limit=10, budget=0):
    top = rtlil_name(top)
    kept = kept_set(kept_names, children) - {top}
    sizes = Sizes(children, costs, kept | blackboxes)
    names = keep_names(list(children))
    kept_partitions = sorted(m for m in kept if m in stats or m not in blackboxes)
    partitions = [top] + [m for m in kept_partitions if m in children]
    rows = []
    for p in partitions:
        st = stats.get(p, {})
        rows.append(
            {
                "module": p,
                "name": "(top) " + p if p == top else names[p],
                "seconds": st.get("seconds"),
                "pass": st.get("pass"),
                "pass_seconds": st.get("pass_seconds"),
                "cells": st.get("cells"),
                "area": st.get("area"),
                "estimate": sizes.size(p),
                "own": costs.get(p, 0),
            }
        )
    rows.sort(key=lambda r: (-(r["seconds"] or 0), -r["estimate"]))

    out = []
    out.append(f"# Keep report: {top}")
    out.append("")
    critical = rows[0]
    out.append(hint(critical, rows, sizes, names, top))
    out.append("")
    out.append("## Partitions, longest first")
    out.append("")
    out.append(
        "| Partition | Wall (s) | Longest pass | Cells | Area | Est. gates | Own gates |"
    )
    out.append("|---|---:|---|---:|---:|---:|---:|")
    for r in rows:
        longest = f"{r['pass']} {r['pass_seconds']} s" if r["pass"] else ""
        out.append(
            f"| {r['name']} | {fmt(r['seconds'], 1)} | {longest} | {fmt(r['cells'])} "
            f"| {fmt(r['area'], 1)} | {fmt(r['estimate'])} | {fmt(r['own'])} |"
        )
    out.append("")
    out.append(
        "Est. gates: yosys's keep_hierarchy estimate of what the partition "
        "synthesizes, its own gates and those of every module under it that "
        "is not kept. Own gates: the module's logic outside any submodule; "
        "for the top, the logic a keep list cannot move out of it."
    )
    slow = slow_partitions(rows, budget)
    if slow:
        out.append("")
        out.append("## Slow partitions")
        out.append("")
        out.append(
            "Times vary by machine and are indicative; these are suggestions, "
            "nothing fails on them."
        )
        out.append("")
        for s in slow:
            out.append(f"- **{s['name']}**: {'; '.join(s['why'])}.")
            for remedy in s["remedies"]:
                out.append(f"  - {remedy}")
    for r in rows:
        cands = candidate_rows(r["module"], sizes, names, limit)
        if not cands:
            continue
        out.append("")
        out.append(f"## Keep candidates in {r['name']}")
        out.append("")
        out.append("| Module | Instances | Est. gates each | Moved out | Share |")
        out.append("|---|---:|---:|---:|---:|")
        for c in cands:
            out.append(
                f"| {c['name']} | {c['instances']} | {fmt(c['each'])} "
                f"| {fmt(c['moved'])} | {c['share']:.0%} |"
            )
    out.append("")
    return "\n".join(out)


def candidate_rows(partition, sizes, names, limit):
    total = sizes.size(partition)
    rows = []
    for module, n in sizes.candidates(partition).items():
        each = sizes.size(module)
        if each == 0:
            continue
        moved = n * each
        rows.append(
            {
                "module": module,
                "name": names[module],
                "instances": n,
                "each": each,
                "moved": moved,
                "share": moved / total if total else 0,
            }
        )
    rows.sort(key=lambda c: (-c["moved"], c["name"]))
    return rows[:limit]


def hint(critical, rows, sizes, names, top):
    name = critical["name"]
    if critical["seconds"] is None:
        lead = (
            f"**Largest partition: {name}** ({fmt(critical['estimate'])} est. gates)."
        )
    else:
        took = f"{fmt(critical['seconds'], 1)} s"
        if critical["pass"]:
            took += f", {critical['pass']} {critical['pass_seconds']} s"
        lead = f"**Critical path: {name}** ({took})."
    others = [r["seconds"] for r in rows[1:] if r["seconds"] is not None]
    cands = candidate_rows(critical["module"], sizes, names, limit=1000)
    if not cands:
        if critical["module"] == top:
            return (
                lead
                + " The top's own logic is all that is left in it; keeping more modules will not split it."
            )
        return (
            lead
            + " It has no submodules to keep; split it in the RTL, or generate its regular structures."
        )
    total = critical["estimate"] or 1
    target = (
        max(others) / critical["seconds"] if others and critical["seconds"] else 0.5
    )
    picked = []
    left = total
    for c in cands:
        if any(
            c["module"] in sizes.candidates(p["module"])
            or p["module"] in sizes.candidates(c["module"])
            for p in picked
        ):
            continue
        picked.append(c)
        left -= c["moved"]
        if left / total <= target or len(picked) == 3:
            break
    names = ", ".join(c["name"] for c in picked)
    return (
        f"{lead} Keeping {names} would move {1 - left / total:.0%} of its "
        f"estimated gates into partitions of their own."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--top", required=True)
    parser.add_argument("--kept", required=True, help="kept_modules.json")
    parser.add_argument("--rtlil", required=True, help="the canonical RTLIL")
    parser.add_argument("--costs", required=True, help="keep_hierarchy -min_cost 1 log")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--budget",
        type=float,
        default=0,
        help="flag partitions whose wall time exceeds this many seconds; 0 for none",
    )
    parser.add_argument("stats", nargs="*", help="partition_<name>_stat.txt")
    args = parser.parse_args(argv)
    with open(args.kept) as f:
        kept_names = json.load(f)["modules"]
    with open(args.rtlil) as f:
        children, blackboxes = read_hierarchy(f)
    with open(args.costs) as f:
        costs = read_costs(f)
    texts = []
    for path in args.stats:
        with open(path) as f:
            texts.append(f.read())
    text = report(
        args.top,
        kept_names,
        children,
        blackboxes,
        costs,
        read_stats(texts),
        args.limit,
        args.budget,
    )
    with open(args.out, "w") as f:
        f.write(text)


if __name__ == "__main__":
    main(sys.argv[1:])
