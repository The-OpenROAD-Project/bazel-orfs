"""Is RTL-MP's scoring function any good?  The audit's driver.

stage_variance located the noise: downstream of a fixed macro placement
the flow is quiet, while the macro placer's response to its input swings
the achieved period ~25%.  Choosing a macro placement is therefore
choosing a downstream outcome, and RTL-MP chooses with an internal
annealing cost nobody has checked against the flow.  This campaign
builds a population of candidate placements spanning the full quality
range and asks how well the placer's own objective predicts the flow's
KPI menu at grt.

The population (multiplier_top's 16 macros are identical instances, so
any assignment of instances to a fixed set of non-overlapping slots is
legal by construction):

  W  winners       RTL-MP's own outputs: the base run plus runs on
                   CORE_AREA site-nudged floorplans -- the established
                   generator of genuinely different winners.
  T  tradeoff      RTL-MP on the base floorplan with one objective
     optima        weight distorted per candidate: optimal for the
                   wrong objective, mid-range under the default one.
  D  fenced        RTL-MP confined by an adversarial RTLMP_FENCE_* box
                   (a corner, a strip): its best-within-fence output,
                   significantly worse BY ITS OWN ACCOUNTING -- the
                   scored end of the degraded range.
  D  injected      permutations of the base winner's assignment (pair
                   swaps, shuffles, orientation flips, one clumped
                   packing): evaluated on the flow side only, because
                   RTL-MP cannot be made to score them (below).

Scoring: a finding before the first result -- RTL-MP cannot be made to
score an arbitrary external placement.  It has no evaluate-only entry
point; the Total Cost it prints is normalized per run, so its own
totals are not comparable across runs; and forcing the annealer onto a
target via per-macro guidance regions fails structurally, because the
SA explores sequence-pair packings and an arbitrary geometry is not in
that space (measured: 80-247um of non-compliance, including against
the placer's own winner).  Every score in the audit therefore comes
from a placement RTL-MP itself produced: the raw component values are
parsed from its debug penalty table (placement properties, comparable
across runs) and recombined into the default objective under one fixed
normalization (the base winner's values).  The injected-permutation
stratum is evaluated on the flow side only and reported as unscored.

The math (ties below delta_tie = z*sigma*sqrt(2), sigma from the
stage_variance campaign, so noise-chasing is never rewarded; bootstrap
CIs on everything; per KPI candidate, since a score may track the mean
and miss the max):

  P_pick   pairwise pick accuracy, (Kendall tau_b + 1)/2 -- the
           probability the objective picks the better of two
           placements.  0.5 is a coin flip.
  AUC      Mann-Whitney separation of W from D, for the score and for
           the flow side by side.  A flow that separates them while the
           score cannot is the "way off" verdict; a flow that cannot
           separate them at all means selection is moot on this design.
  regret   y(argmin s) - min y: what the objective's pick costs against
           the best candidate on the table, plus both cross-ranks.
  tau_W    pick accuracy restricted to winners -- the decision RTL-MP
           actually makes in production.
"""

import argparse
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import tempfile

from stage_variance import ensemble_stats, kpi_candidates, percentile

Z = 1.96
BASE_CORE = "4 4 396 396"
SITE_NM = 54  # asap7 site width, measured by :site_probe
W_NUDGES = [-5, -4, -3, -2, -1, 1, 2, 3, 4]
# One distortion per candidate; defaults are area 0.1, wirelength 100,
# outline 100, boundary 50, notch 50, halo "10 10".
T_SPECS = {
    "t_wl1": {"RTLMP_WIRELENGTH_WT": "1"},
    "t_wl10": {"RTLMP_WIRELENGTH_WT": "10"},
    "t_bound500": {"RTLMP_BOUNDARY_WT": "500"},
    "t_notch500": {"RTLMP_NOTCH_WT": "500"},
    "t_area10": {"RTLMP_AREA_WT": "10"},
    "t_halo0": {"MACRO_PLACE_HALO": "0 0"},
    "t_halo20": {"MACRO_PLACE_HALO": "20 20"},
    "t_level1": {"RTLMP_MAX_LEVEL": "1"},
}
# The default objective's weights, for the recomputed score.
DEFAULT_WEIGHTS = {
    "Area": 0.1,
    "Outline": 100.0,
    "Wire Length": 100.0,
    "Guidance": 0.0,  # audit artifact, not part of the audited objective
    "Fence": 10.0,
    "Boundary": 50.0,
    "Soft Blockage": 10.0,
    "Notch": 50.0,
}
KPIS = ["achieved", "top10_mean", "p95", "mean", "area"]
# Adversarial fences, in microns on the 4..396 core.  The 16 macros are
# ~40x40um with a 10um halo (~60um pitch), so a 4x4 grid needs ~240um of
# fence: the tight corner barely fits, the strips force degenerate rows.
# An infeasible fence fails its member (MPL-10) and the audit proceeds
# on the survivors -- a failure is data about the fence, not a bug.
D_FENCES = {
    "d_fence_corner": ("4.0", "4.0", "260.0", "260.0"),
    "d_fence_tight": ("4.0", "4.0", "246.0", "246.0"),
    "d_fence_strip": ("4.0", "4.0", "396.0", "196.0"),
    "d_fence_column": ("4.0", "4.0", "196.0", "396.0"),
}


def fence_cfg(box):
    lx, ly, ux, uy = box
    return {
        "RTLMP_FENCE_LX": lx,
        "RTLMP_FENCE_LY": ly,
        "RTLMP_FENCE_UX": ux,
        "RTLMP_FENCE_UY": uy,
    }


PLACE_RE = re.compile(
    r"place_macro\s+-macro_name\s+\{(.*)\}\s+-location\s+"
    r"\{([-0-9.eE]+)\s+([-0-9.eE]+)\}\s+-orientation\s+(\S+)"
)


def nudged_core(eps):
    """396.000um +/- eps sites on the upper-right x, exact integer nm."""
    nm = 396000 + eps * SITE_NM
    return "4 4 %d.%s 396" % (nm // 1000, str(1000 + nm % 1000)[1:])


def parse_place_file(path):
    with open(path) as f:
        text = f.read()
    out = [
        (m.group(1), float(m.group(2)), float(m.group(3)), m.group(4))
        for m in PLACE_RE.finditer(text)
    ]
    if not out:
        raise ValueError(f"no place_macro lines in {path}")
    return out


def write_place_file(path, placements):
    with open(path, "w") as f:
        for name, x, y, orient in placements:
            f.write(
                "place_macro -macro_name {%s} -location {%.4f %.4f} "
                "-orientation %s\n" % (name, x, y, orient)
            )


# ---------------------------------------------------------------------
# Degraded-candidate synthesis: permute the base winner's instance->slot
# assignment.  Slots are the winner's own (location, orientation)
# tuples, so every candidate occupies exactly the same set of legal,
# non-overlapping footprints -- generation is permutation, never
# legalization.


def permute_assignment(placements, rng, num_swaps=None):
    names = [p[0] for p in placements]
    slots = [(p[1], p[2], p[3]) for p in placements]
    order = list(range(len(slots)))
    if num_swaps is None:
        rng.shuffle(order)
    else:
        for _ in range(num_swaps):
            i, j = rng.sample(range(len(order)), 2)
            order[i], order[j] = order[j], order[i]
    return [(names[k], *slots[order[k]]) for k in range(len(names))]


def flip_orientations(placements, rng, count):
    flip = {"R0": "MY", "MY": "R0", "MX": "R180", "R180": "MX"}
    chosen = set(rng.sample(range(len(placements)), count))
    return [
        (n, x, y, flip.get(o, o) if i in chosen else o)
        for i, (n, x, y, o) in enumerate(placements)
    ]


def clumped(placements, sizes, core=(4.0, 4.0, 396.0, 396.0), gap=1.0):
    """Pack all macros in a grid from the core's lower-left corner --
    legal (in-core, non-overlapping; no halo is enforced in the DB) and
    deliberately terrible."""
    lx, ly, ux, uy = core
    w = max(sizes[n]["w"] for n, *_ in placements)
    h = max(sizes[n]["h"] for n, *_ in placements)
    cols = max(1, int((ux - lx - gap) // (w + gap)))
    out = []
    for i, (name, _, _, _) in enumerate(placements):
        r, c = divmod(i, cols)
        x = lx + gap + c * (w + gap)
        y = ly + gap + r * (h + gap)
        if x + w > ux or y + h > uy:
            raise ValueError("clumped packing does not fit the core")
        out.append((name, x, y, "R0"))
    return out


def synthesize_degraded(base_placements, sizes, seed=2026):
    rng = random.Random(seed)
    out = {}
    for k in (2, 4, 8):
        for v in (1, 2):
            out[f"d_swap{k}_{v}"] = (
                permute_assignment(base_placements, rng, num_swaps=k),
                f"swap{k}",
            )
    for v in (1, 2, 3):
        out[f"d_shuffle_{v}"] = (
            permute_assignment(base_placements, rng),
            "shuffle",
        )
    for count in (8, 16):
        out[f"d_flip{count}"] = (
            flip_orientations(base_placements, rng, count),
            f"flip{count}",
        )
    out["d_clump"] = (clumped(base_placements, sizes), "clump")
    return out


# ---------------------------------------------------------------------
# The penalty-table parser.  Score/generate children run sequentially
# and bracket their output with MS_TABLE_BEGIN/END <tag>, so the shared
# run log stays attributable.  Within a section the annealer prints one
# or more summaries:
#
#   <Cluster|Macro> Placement Summary
#     ...
#     Penalty Type  |  Weight  |  Value  |  Norm. Factor  |  Cost
#     Area          |  0.1     |  ...    |  ...           |  ...
#     ...
#     Total Cost                                     1.2345

ROW_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z ]*?)\s*\|\s*([-\d.eE+]+)\s*\|"
    r"\s*([-\d.eE+]+)\s*\|\s*([-\d.eE+]+)"
)
SUMMARY_RE = re.compile(r"(Cluster|Macro) Placement Summary")


def parse_log_tables(log_text):
    """{tag: {"tables": [{kind, rows{name: {weight, value, norm}}}],
    "compliance_um": float or None}}"""
    out = {}
    tag = None
    tables = None
    current = None
    for line in log_text.splitlines():
        m = re.match(r"MS_TABLE_BEGIN (\S+)", line)
        if m:
            tag = m.group(1)
            tables = []
            current = None
            continue
        m = re.match(r"MS_TABLE_END (\S+)", line)
        if m:
            out.setdefault(m.group(1), {})["tables"] = tables or []
            tag = None
            continue
        m = re.match(r"MS_COMPLIANCE (\S+) ([-\d.eE+]+)", line)
        if m:
            out.setdefault(m.group(1), {})["compliance_um"] = float(m.group(2))
            continue
        if tag is None:
            continue
        m = SUMMARY_RE.search(line)
        if m:
            current = {"kind": m.group(1), "rows": {}}
            tables.append(current)
            continue
        if current is not None:
            m = ROW_RE.match(line)
            if m and m.group(1).strip() != "Penalty Type":
                current["rows"][m.group(1).strip()] = {
                    "weight": float(m.group(2)),
                    "value": float(m.group(3)),
                    "norm": float(m.group(4)),
                }
    return out


def raw_components(tables):
    """Sum each penalty's raw value across the run's printed summaries.

    A run prints one summary per simulated-annealing scope (cluster
    level, then macro level per cluster); the raw values are placement
    properties, so summing across scopes gives one number per component
    for the whole placement.  Kept alongside the per-table data in the
    output JSON so this aggregation choice can be revisited without
    re-running anything.
    """
    total = {}
    for t in tables:
        for name, row in t["rows"].items():
            total[name] = total.get(name, 0.0) + row["value"]
    return total


def default_cost(components, norms):
    """The default objective recomputed with one fixed normalization.

    RTL-MP normalizes per run, so its own totals cannot be compared
    across runs; this recomputation uses the base winner's component
    values as the normalization for everyone, which preserves the
    default weighting and makes the scale shared.

    A component that is ZERO in the normalization base (Soft Blockage on
    a design without blockages, Outline when everything fits) cannot be
    normalized and is skipped rather than divided by a fallback: the
    first campaign showed a raw Soft Blockage value of 1e8 pinned two
    candidates to the worst ranks through nothing but the fallback
    scale.  Skipped components stay visible in each candidate's raw
    component record.
    """
    cost = 0.0
    for name, w in DEFAULT_WEIGHTS.items():
        if name not in components or w == 0.0:
            continue
        norm = norms.get(name)
        if not norm:
            continue
        cost += w * components[name] / norm
    return cost


# ---------------------------------------------------------------------
# The audit math.


def kendall_pick(pairs_s, pairs_y, y_tie):
    """Concordant/discordant count over candidate pairs; a pair whose
    flow outcomes differ by less than y_tie is a tie and scores neither.
    Returns (P_pick, n_effective_pairs) or (None, 0)."""
    conc = disc = 0
    n = len(pairs_s)
    for i in range(n):
        for j in range(i + 1, n):
            dy = pairs_y[i] - pairs_y[j]
            ds = pairs_s[i] - pairs_s[j]
            if abs(dy) < y_tie or ds == 0:
                continue
            if (ds > 0) == (dy > 0):
                conc += 1
            else:
                disc += 1
    total = conc + disc
    return (conc / total if total else None), total


def auc(scores_bad, scores_good):
    """Mann-Whitney AUC: probability a degraded candidate scores worse
    (higher) than a winner. 0.5 = cannot tell."""
    wins = ties = 0
    for b in scores_bad:
        for g in scores_good:
            if b > g:
                wins += 1
            elif b == g:
                ties += 1
    total = len(scores_bad) * len(scores_good)
    return (wins + 0.5 * ties) / total if total else None


def bootstrap_ci(values_s, values_y, stat_fn, resamples=2000, seed=0):
    rng = random.Random(seed)
    n = len(values_s)
    boots = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat_fn([values_s[i] for i in idx], [values_y[i] for i in idx])
        if v is not None:
            boots.append(v)
    if not boots:
        return [None, None]
    boots.sort()
    return [percentile(boots, 0.025), percentile(boots, 0.975)]


def audit(candidates, spine_kpis, delta_tie):
    """candidates: {tag: {stratum, score, kpis{...}}} -> audit document
    per KPI."""
    tags = sorted(candidates)
    strata = {t: candidates[t]["stratum"] for t in tags}
    s = [candidates[t]["score"] for t in tags]
    out = {}
    for kpi in KPIS:
        y = [candidates[t]["kpis"][kpi] for t in tags]
        tie = delta_tie.get(kpi, 0.0)

        p_pick, n_pairs = kendall_pick(s, y, tie)
        pick_ci = bootstrap_ci(s, y, lambda a, b: kendall_pick(a, b, tie)[0])
        # Injection is deterministic (two injections of one candidate
        # agree bit-for-bit -- the null), so every pair is measurable:
        # the raw variant asks "literally better", the tied variant
        # "better by more than the flow's own noise floor".
        p_pick_raw, n_pairs_raw = kendall_pick(s, y, 0.0)

        w_idx = [i for i, t in enumerate(tags) if strata[t] == "W"]
        d_idx = [i for i, t in enumerate(tags) if strata[t].startswith("D")]
        auc_s = auc([s[i] for i in d_idx], [s[i] for i in w_idx])
        auc_y = auc([y[i] for i in d_idx], [y[i] for i in w_idx])

        best_by_s = min(range(len(tags)), key=lambda i: s[i])
        best_by_y = min(range(len(tags)), key=lambda i: y[i])
        y_sorted = sorted(range(len(tags)), key=lambda i: y[i])
        s_sorted = sorted(range(len(tags)), key=lambda i: s[i])
        regret = y[best_by_s] - y[best_by_y]

        pick_w, _ = kendall_pick([s[i] for i in w_idx], [y[i] for i in w_idx], tie)

        stratum_median = {}
        for label in sorted(set(strata.values())):
            vals = [y[i] for i, t in enumerate(tags) if strata[t] == label]
            stratum_median[label] = statistics.median(vals) if vals else None

        out[kpi] = {
            "delta_tie": tie,
            "p_pick": p_pick,
            "p_pick_ci": pick_ci,
            "effective_pairs": n_pairs,
            "p_pick_raw": p_pick_raw,
            "raw_pairs": n_pairs_raw,
            "auc_score_W_vs_D": auc_s,
            "auc_flow_W_vs_D": auc_y,
            "regret": regret,
            "regret_pct": (
                100.0 * regret / abs(spine_kpis[kpi]) if spine_kpis.get(kpi) else None
            ),
            "flow_rank_of_score_pick": y_sorted.index(best_by_s) + 1,
            "score_rank_of_flow_best": s_sorted.index(best_by_y) + 1,
            "p_pick_within_W": pick_w,
            "stratum_median_y": stratum_median,
        }
    return out


# ---------------------------------------------------------------------
# Orchestration.


def run_mode(exe, mode, manifest_dir, out_dir, work, jobs, timeout):
    log_dir = os.path.join(work, f"log_{mode}")
    cmd = [
        exe,
        f"MS_MODE={mode}",
        f"MS_MANIFEST_DIR={os.path.abspath(manifest_dir)}",
        f"MS_OUT_DIR={os.path.abspath(out_dir)}",
        f"MS_WORK={os.path.abspath(work)}/{mode}",
        f"LOG_DIR={os.path.abspath(log_dir)}",
        "NUM_CORES=1",
        f"ORFS_FORK_JOBS={jobs}",
        f"MS_CHILD_TIMEOUT={timeout}",
    ]
    from optuna_study import scratch_root

    env = os.environ.copy()
    env["TMPDIR"] = scratch_root()
    print(f"macro_score: running mode {mode}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    tail = []
    for line in proc.stdout:
        tail.append(line)
        tail = tail[-200:]
        if line.startswith("macro_score:"):
            print(f"  {line.rstrip()}", flush=True)
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"mode {mode} exited {rc}\n" + "".join(tail))
    with open(os.path.join(log_dir, "run.log")) as f:
        return f.read()


def write_manifest(manifest_dir, entries):
    os.makedirs(manifest_dir, exist_ok=True)
    for tag, cfg in entries.items():
        with open(os.path.join(manifest_dir, f"{tag}.cfg"), "w") as f:
            for k, v in cfg.items():
                f.write(f"{k}={v}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable")
    parser.add_argument("design")
    parser.add_argument(
        "variance_json",
        help="stage_variance_<design>.json, the source of delta_tie",
    )
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 8) // 4))
    parser.add_argument("--child-timeout", type=int, default=10800)
    parser.add_argument("--keep-work", action="store_true")
    parser.add_argument(
        "--reuse", help="re-analyze an existing MS_OUT_DIR (skips all runs)"
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="a five-candidate end-to-end shakedown of all three modes",
    )
    args = parser.parse_args()

    with open(args.variance_json) as f:
        variance = json.load(f)
    delta_tie = {}
    for kpi in KPIS:
        sigma = variance["arms"]["all"]["stats"].get(kpi, {}).get("stdev")
        delta_tie[kpi] = Z * math.sqrt(2.0) * sigma if sigma else 0.0

    if args.reuse:
        out_dir = args.reuse
        work = None
        gen_log = ""
    else:
        from optuna_study import scratch_root

        work = tempfile.mkdtemp(prefix="macro_score_", dir=scratch_root())
        out_dir = os.path.join(work, "out")
        os.makedirs(out_dir)

        w_nudges = [-1] if args.smoke else W_NUDGES
        t_specs = {"t_wl1": T_SPECS["t_wl1"]} if args.smoke else T_SPECS
        fences = (
            {"d_fence_corner": D_FENCES["d_fence_corner"]} if args.smoke else D_FENCES
        )
        gen_entries = {"w_base": {"CORE_AREA": BASE_CORE}}
        for e in w_nudges:
            tag = "w_%s" % ("m%d" % -e if e < 0 else "p%d" % e)
            gen_entries[tag] = {"CORE_AREA": nudged_core(e)}
        for tag, spec in t_specs.items():
            gen_entries[tag] = dict(spec)
        for tag, box in fences.items():
            gen_entries[tag] = fence_cfg(box)
        write_manifest(os.path.join(work, "manifest_gen"), gen_entries)
        gen_log = run_mode(
            args.executable,
            "generate",
            os.path.join(work, "manifest_gen"),
            out_dir,
            work,
            args.jobs,
            args.child_timeout,
        )
        with open(os.path.join(out_dir, "generate.log"), "w") as f:
            f.write(gen_log)

        base_placements = parse_place_file(os.path.join(out_dir, "w_base.place.tcl"))
        with open(os.path.join(out_dir, "w_base.macros.json")) as f:
            sizes = json.load(f)
        degraded = synthesize_degraded(base_placements, sizes)
        if args.smoke:
            degraded = {t: degraded[t] for t in ("d_swap2_1", "d_clump")}
        for tag, (placements, _) in degraded.items():
            write_place_file(os.path.join(out_dir, f"{tag}.place.tcl"), placements)

        all_tags = [
            t
            for t in gen_entries
            if os.path.exists(os.path.join(out_dir, f"{t}.place.tcl"))
        ] + list(degraded)

        def stratum(tag):
            if tag.startswith("w_"):
                return "W"
            if tag.startswith("t_"):
                return "T"
            if tag.startswith("d_fence"):
                return "D_" + tag[2:]
            return "D_" + degraded[tag][1]

        eval_entries = {
            tag: {
                "PLACE_FILE": os.path.abspath(
                    os.path.join(out_dir, f"{tag}.place.tcl")
                ),
                "STRATUM": stratum(tag),
            }
            for tag in all_tags
        }
        # The determinism null: a second injection of the base winner's
        # placement.  It must reproduce the w_base candidate leaf
        # bit-identically (same file, same path through the flow).  It
        # must NOT be expected to reproduce the spine: a full
        # rtl_macro_placer run additionally seeds a temporary std-cell
        # placement (HierRTLMP::run -> generateTemporaryStdCellsPlacement)
        # that the MPL-0013 skip path does not, so production and
        # injection diverge downstream even with bit-identical macro
        # geometry -- measured ~2% on the achieved period here, and
        # reported by the driver as injection_offset.
        eval_entries["null_wbase"] = {
            "PLACE_FILE": os.path.abspath(os.path.join(out_dir, "w_base.place.tcl")),
            "STRATUM": "null",
        }
        write_manifest(os.path.join(work, "manifest_eval"), eval_entries)
        run_mode(
            args.executable,
            "evaluate",
            os.path.join(work, "manifest_eval"),
            out_dir,
            work,
            args.jobs,
            args.child_timeout,
        )

    try:
        result = analyze_out_dir(out_dir, delta_tie, args.design)
        failures = result["guards"]["failures"]
        for line in result["headline"]:
            print(f"  {line}")
        for f_ in failures:
            print(f"  GUARD FAILURE: {f_}")
        ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
        out_json = os.path.join(
            ws, "test", "estimation_ladder", f"macro_score_{args.design}.json"
        )
        with open(out_json, "w") as f:
            json.dump(result, f, indent=1)
        print(f"macro_score: wrote {out_json}")
        if failures:
            raise SystemExit("macro_score: guard failures (see above)")
    finally:
        if work and not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)


def analyze_out_dir(out_dir, delta_tie, design):
    with open(os.path.join(out_dir, "generate.log")) as f:
        score_tables = parse_log_tables(f.read())

    leaves = {}
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith(".json") or name.endswith(
            (".macros.json", ".scored.json")
        ):
            continue
        with open(os.path.join(out_dir, name)) as f:
            doc = json.load(f)
        if "paths" in doc:
            leaves[doc["tag"]] = doc

    spine = leaves.pop("spine", None)
    if spine is None:
        raise RuntimeError("the spine leaf is missing; evaluate did not finish")
    spine_kpis = kpi_candidates(spine)

    # Fixed normalization: the base winner's raw components.
    base_components = raw_components(score_tables.get("w_base", {}).get("tables", []))
    if not base_components:
        raise RuntimeError("no penalty tables parsed for w_base")

    candidates = {}
    unscored = {}
    guards = []
    null_leaf = leaves.pop("null_wbase", None)
    for tag, leaf in leaves.items():
        entry = score_tables.get(tag, {})
        comps = raw_components(entry.get("tables", []))
        record = {
            "stratum": leaf["arm"],
            "components": comps,
            "displacement_um": leaf.get("displacement_um"),
            "kpis": kpi_candidates(leaf),
            "tail_s": leaf["tail_s"],
            "raw": {
                "min_periods": [p["min_period"] for p in leaf["paths"]],
                "macro_flags": [p["macro_path"] for p in leaf["paths"]],
                "area": leaf["area"],
            },
        }
        if not comps:
            # The injected-permutation stratum by design: RTL-MP cannot
            # be made to score external geometry, so these feed only the
            # flow-side separation.
            unscored[tag] = record
            continue
        record["score"] = default_cost(comps, base_components)
        candidates[tag] = record

    # Determinism null: two injections of the same placement file (the
    # w_base candidate and null_wbase) must agree bit-for-bit.  The
    # spine is NOT the reference: a full rtl_macro_placer run seeds a
    # temporary std-cell placement the injection path does not, so the
    # spine-vs-injection difference is a systematic offset of the
    # injection pipeline -- measured and reported, not a failure.
    injection_offset = {}
    if null_leaf is None:
        guards.append("null_wbase leaf missing")
    else:
        nk = kpi_candidates(null_leaf)
        wb = candidates.get("w_base")
        if wb is None:
            guards.append("w_base candidate leaf missing")
        else:
            for kpi in ("achieved", "mean", "area"):
                a, b = wb["kpis"][kpi], nk[kpi]
                if abs(a - b) > 1e-6 * max(abs(a), abs(b), 1e-30):
                    guards.append(
                        f"null vs w_base {kpi}: {b} != {a} -- two "
                        "injections of the same placement disagree; the "
                        "flow is not deterministic under injection"
                    )
        for kpi in KPIS:
            base = spine_kpis.get(kpi)
            if base:
                injection_offset[kpi] = {
                    "delta": nk[kpi] - base,
                    "pct": 100.0 * (nk[kpi] - base) / abs(base),
                }

    audit_doc = audit(candidates, spine_kpis, delta_tie)

    # The flow-side W-vs-D separation over EVERY evaluated candidate,
    # compliant or not: does the flow itself punish degraded placements?
    all_pop = dict(candidates) | unscored
    flow_auc_all = {}
    for kpi in KPIS:
        w_vals = [c["kpis"][kpi] for c in all_pop.values() if c["stratum"] == "W"]
        d_vals = [
            c["kpis"][kpi] for c in all_pop.values() if c["stratum"].startswith("D")
        ]
        flow_auc_all[kpi] = auc(d_vals, w_vals)

    headline = []
    for kpi in ("achieved", "mean"):
        a = audit_doc[kpi]
        headline.append(
            f"{kpi}: P_pick={a['p_pick']:.3f} "
            f"(CI {a['p_pick_ci'][0]:.2f}..{a['p_pick_ci'][1]:.2f}), "
            f"AUC score {a['auc_score_W_vs_D']:.2f} vs flow "
            f"{a['auc_flow_W_vs_D']:.2f}, regret {a['regret_pct']:.2f}%"
            if a["p_pick"] is not None
            else f"{kpi}: inconclusive (no resolvable pairs)"
        )

    return {
        "design": design,
        "spine": {"kpis": spine_kpis},
        "delta_tie": delta_tie,
        "candidates": candidates,
        "audit": audit_doc,
        "injection_offset": injection_offset,
        "unscored": {
            t: {k: v for k, v in c.items() if k != "raw"} for t, c in unscored.items()
        },
        "auc_flow_W_vs_D_all_candidates": flow_auc_all,
        "score_tables": {t: e.get("tables", []) for t, e in score_tables.items()},
        "guards": {"failures": guards},
        "headline": headline,
    }


if __name__ == "__main__":
    main()
