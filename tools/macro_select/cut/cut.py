"""The module-cut search: which modules synthesis keeps (SYNTH_KEEP_MODULES).

An arm is a set of kept RTL module types; the top is always kept. Each
arm is synthesised and floorplanned, and the keep census
(keep_census.tcl) on its floorplan says where its cones were cut. Arms
are scored lexicographically: the worst reg2reg period, then the area,
then the synthesis time. The census predicts which arm to try next; the
measurement decides.

Nothing here runs a tool: parsing, scoring and planning only, so it is
unit-tested on census rows written by hand (cut_test.py).
"""

import itertools
import re

# Up to this many arms, every keep set is tried: the answer, and the truth
# the census's predictions are checked against. Past it, a greedy walk
# from the best arm, one module flipped per step.
MAX_EXHAUSTIVE = 16


def parse_census(lines):
    """The rows of a census TSV, by kind."""
    c = {
        "module": [],
        "cross": [],
        "inside": [],
        "edge": [],
        "macro": [],
        "period": None,
        "paths": None,
    }
    for line in lines:
        f = line.rstrip("\n").split("\t")
        if not f or not f[0]:
            continue
        k = f[0]
        if k == "module":
            c[k].append(
                {"inst": f[1], "master": f[2], "cells": int(f[3]), "area": float(f[4])}
            )
        elif k == "inside":
            c[k].append(
                {"inst": f[1], "master": f[2], "paths": int(f[3]), "sum": float(f[4])}
            )
        elif k in ("cross", "macro"):
            c[k].append(
                {
                    "inst": f[1],
                    "master": f[2],
                    "paths": int(f[3]),
                    "sum": float(f[4]),
                    "worst": float(f[5]),
                }
            )
        elif k == "edge":
            c[k].append(
                {
                    "a": f[1],
                    "b": f[2],
                    "paths": int(f[3]),
                    "excess": float(f[4]),
                    "worst": float(f[5]),
                }
            )
        elif k == "period":
            c[k] = {"worst": float(f[1]), "clock": float(f[2])}
        elif k == "paths":
            c[k] = {
                "count": int(f[1]),
                "target": float(f[2]),
                "worst": float(f[3]),
                "seconds": float(f[4]),
            }
        else:
            raise ValueError("census: unknown row kind %r in %r" % (k, line))
    if c["period"] is None or c["paths"] is None:
        raise ValueError("census: no period or paths row; did keep_census finish?")
    return c


_MODULE = re.compile(r"^\s*module\s+\\?(\S+)")
_CELL = re.compile(r"^\s*cell\s+\\?(\S+)\s+\\?(\S+)")


def rtlil_hierarchy(lines):
    """{module: [modules it instantiates]} from an RTLIL file. A blackbox
    (a macro's liberty stub) is not a module synthesis can keep or
    flatten, and is left out."""
    hier = {}
    blackbox = set()
    cur = None
    cells = []
    attrs = []
    for line in lines:
        if line.startswith("attribute "):
            attrs.append(line.split()[1])
            continue
        m = _MODULE.match(line)
        if m:
            cur = m.group(1)
            cells = []
            hier[cur] = cells
            if "\\blackbox" in attrs:
                blackbox.add(cur)
            attrs = []
            continue
        attrs = []
        if line.strip() == "end" and cur is not None and line.startswith("end"):
            cur = None
            continue
        if cur is not None:
            m = _CELL.match(line)
            if m:
                cells.append(m.group(1))
    return {
        k: [t for t in v if t in hier and t not in blackbox]
        for k, v in hier.items()
        if k not in blackbox
    }


def types_under(hier, top):
    """The module types instantiated under top, top excluded, sorted."""
    if top not in hier:
        raise ValueError("%s is not a module of the RTLIL" % top)
    seen = set()
    todo = [top]
    while todo:
        for t in hier[todo.pop()]:
            if t not in seen:
                seen.add(t)
                todo.append(t)
    seen.discard(top)
    return sorted(seen)


def module_groups(modules):
    """{RTL module type: [module names]}: slang's canonicalisation gives
    every instance a module of its own, <module>$<instance path>, and the
    search keeps or flattens a type with all its instances."""
    groups = {}
    for m in modules:
        groups.setdefault(m.split("$", 1)[0], []).append(m)
    return {k: sorted(v) for k, v in groups.items()}


def rtl_type(master, types):
    """The RTL module type of a synthesised master: hierarchical synthesis
    uniquifies a kept module per instance (aes_sbox_us10); the longest
    type that is the master or a prefix of it followed by '_' or '$'."""
    if master in types:
        return master
    best = None
    for t in types:
        if master.startswith(t) and master[len(t)] in "_$":
            if best is None or len(t) > len(best):
                best = t
    return best


def arm_key(keep):
    return tuple(sorted(keep))


def score(result):
    """The lexicographic score of a measured arm: smaller is better."""
    return (result["P"], result["area"], result["t_syn"])


def crossing_excess(census, types):
    """{module type: (paths, ps over target summed, worst ps over target)}
    of the cross rows: the cones a kept boundary of that type cut."""
    out = {}
    for r in census["cross"]:
        t = rtl_type(r["master"], types)
        if t is None:
            continue
        n, s, w = out.get(t, (0, 0.0, 0.0))
        out[t] = (n + r["paths"], s + r["sum"], max(w, r["worst"]))
    return out


def predict(census, types, keep, cand):
    """(pred, sum, why) for the arm cand measured against keep, from
    keep's census.

    The cost is time: the worst period first. pred is, in ps over the
    census target, the worst path a dropped keep's boundary cut: a cut on
    the worst path (pred = worst period - target) is the only kind that
    can move the period; one far below it cannot, however many paths it
    cuts. sum, every cut path's excess summed, breaks ties. Both rank the
    candidates and are checked against what the arm measures."""
    dropped = sorted(set(keep) - set(cand))
    added = sorted(set(cand) - set(keep))
    if census is None:
        return None, None, "no census yet"
    ex = crossing_excess(census, types)
    worst = 0.0
    total = 0.0
    why = []
    for t in dropped:
        n, s, w = ex.get(t, (0, 0.0, 0.0))
        worst = max(worst, w)
        total += s
        why.append("drop %s: cuts %d paths, the worst %.0f ps over target" % (t, n, w))
    for t in added:
        why.append("keep %s: unmeasured, no boundary to count yet" % t)
    return worst, total, "; ".join(why) if why else "same keep set"


def plan(types, results, best_key, census_of):
    """The arms still to try, best first: [{"keep": [...], "pred", "why"}].

    results: {arm key: result or None while running}; census_of(key) is
    an arm's census, or None. Exhaustive when the space is small, else
    the best arm's neighbours, one type flipped."""
    n = len(types)
    if 2**n <= MAX_EXHAUSTIVE:
        cands = [
            arm_key(c)
            for r in range(n, -1, -1)
            for c in itertools.combinations(types, r)
        ]
        mode = "exhaustive, %d arms" % 2**n
    else:
        if best_key is None:
            cands = [arm_key(types), arm_key([])]
        else:
            b = set(best_key)
            cands = [arm_key(b ^ {t}) for t in types]
        mode = "greedy from the best arm"
    base = best_key if best_key is not None else arm_key(types)
    census = census_of(base) if base in results else None
    queue = []
    for k in cands:
        if k in results:
            continue
        pred, total, why = predict(census, types, base, k)
        queue.append(
            {
                "keep": list(k),
                "pred": pred,
                "pred_sum": total,
                "why": "%s; %s" % (mode, why),
            }
        )
    # keep-all first: its census sees every boundary; then by prediction
    unknown = float("-inf")
    queue.sort(
        key=lambda q: (
            arm_key(q["keep"]) != arm_key(types),
            -(q["pred"] if q["pred"] is not None else unknown),
            -(q["pred_sum"] if q["pred_sum"] is not None else unknown),
            len(q["keep"]),
        )
    )
    return queue


def best(results):
    """The key of the best finished arm, or None."""
    done = [(score(r), k) for k, r in results.items() if r and r.get("P") is not None]
    return min(done)[1] if done else None
